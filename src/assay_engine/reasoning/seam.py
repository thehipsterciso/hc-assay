"""Tiered reasoning seam — the single abstraction over LLM execution by stakes tier.

No engine component talks to an LLM directly; everything routes through :class:`ReasoningSeam`.
Ported and generalized from the prior platform's hardened ``reasoning_client`` (ARCHITECTURE.md
§1, ADR-0003). Two execution tiers:

- ``StakesTier.BULK`` — a local model runtime (loopback-only, e.g. Ollama) for high-volume,
  low-stakes work.
- ``StakesTier.HIGH_STAKES`` — a frontier model via a **fixed-cost subscription** path
  (the ``claude`` CLI / Agent SDK using an OAuth token). No metered API key is ever used:
  every metered Anthropic credential is scrubbed from the subprocess environment first.

Hardened invariants preserved from the prior platform:

- forward-proof credential scrubbing (any ``ANTHROPIC_*KEY``/``*TOKEN`` stripped; the
  subscription ``CLAUDE_CODE_OAUTH_TOKEN`` preserved);
- hard per-call timeouts via a bounded worker pool with a saturation guard;
- independent retry budgets — exponential backoff for transient errors, long backpressure
  for rate limits — and permanent errors never retried;
- robust JSON extraction via a balanced-brace walker (not a greedy regex);
- loopback enforcement on the local backend (ADR-0003).

Heavy backends (``langchain_ollama``, ``claude_agent_sdk``) and tracing (``opentelemetry``)
are imported lazily, so this module imports — and is unit-testable by mocking ``_attempt`` —
with none of them installed. Install the optional ``reasoning`` extra to run real calls.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, cast, runtime_checkable

from assay_engine._frozen import freeze_mapping
from assay_engine._local import require_loopback_url


class StakesTier(Enum):
    BULK = "bulk"          # local model — high volume, low stakes
    HIGH_STAKES = "high"   # frontier model via fixed-cost subscription — gated, traced


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    prompt: str
    tier: StakesTier
    purpose: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", freeze_mapping(self.params))


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------
class ReasoningError(RuntimeError):
    """Transient reasoning failure (eligible for retry)."""


class PermanentReasoningError(ReasoningError):
    """Non-transient failure — never retried (bad model, auth, saturation)."""


class RateLimitError(ReasoningError):
    """Rate-limit / capacity signal — retried with long backpressure, not fast backoff."""


# --------------------------------------------------------------------------------------
# Config (dataset-agnostic env contract, ASSAY_* prefix)
# --------------------------------------------------------------------------------------
def _env(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val is not None and val != "" else default


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


BULK_MODEL = _env("ASSAY_BULK_MODEL", "llama3.1:8b")
BULK_BASE_URL = _env("ASSAY_BULK_BASE_URL", "http://localhost:11434")
HIGH_STAKES_MODEL = os.environ.get("ASSAY_HIGH_STAKES_MODEL") or None

BULK_TIMEOUT = max(1.0, float(_env("ASSAY_BULK_TIMEOUT", "120")))
HIGH_STAKES_TIMEOUT = max(1.0, float(_env("ASSAY_HIGH_STAKES_TIMEOUT", "300")))

MAX_RETRIES = max(0, int(_env("ASSAY_REASONING_RETRIES", "2")))
BACKOFF_BASE = max(0.0, float(_env("ASSAY_REASONING_BACKOFF", "1.5")))
RATE_LIMIT_BACKOFF = max(0.0, float(_env("ASSAY_RATELIMIT_BACKOFF", "30")))
RATE_LIMIT_MAX_RETRIES = max(0, int(_env("ASSAY_RATELIMIT_RETRIES", "5")))

# OAuth subscription token name (external CLI contract — not renamed).
OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"


# --------------------------------------------------------------------------------------
# Credential scrubbing (ADR-0003 / no metered API) — pure, forward-proof
# --------------------------------------------------------------------------------------
def is_metered_anthropic_credential(key: str) -> bool:
    """True for any env var the Anthropic SDK would read as a METERED credential.

    Matches the *shape* — any ``ANTHROPIC_*`` var naming a ``KEY`` or ``TOKEN`` — rather than
    a static list, so a newly-added metered var cannot silently slip through. The subscription
    ``CLAUDE_CODE_OAUTH_TOKEN`` does not start with ``ANTHROPIC_`` and is deliberately kept.
    """
    return key.startswith("ANTHROPIC_") and ("KEY" in key or "TOKEN" in key)


def scrubbed_env() -> dict[str, str]:
    """The process env with every metered Anthropic credential removed.

    Execution must run on the fixed subscription via the CLI's OAuth token; a metered key, if
    present, would silently bill per token — so strip it before the SDK subprocess sees it.
    """
    return {k: v for k, v in os.environ.items() if not is_metered_anthropic_credential(k)}


# --------------------------------------------------------------------------------------
# Bounded timeout pool with saturation guard
# --------------------------------------------------------------------------------------
_POOL_WORKERS = 8
_pool = ThreadPoolExecutor(max_workers=_POOL_WORKERS, thread_name_prefix="reasoning-timeout")
_inflight = 0
_inflight_lock = threading.Lock()


def _release(_future: Any) -> None:
    global _inflight
    with _inflight_lock:
        _inflight -= 1


def _submit_bounded(fn: Callable[[], Any]) -> Any:
    """Submit to the shared pool, refusing if every worker slot is already in flight
    (hung backend calls would otherwise leak all slots)."""
    global _inflight
    with _inflight_lock:
        if _inflight >= _POOL_WORKERS:
            raise PermanentReasoningError(
                f"reasoning timeout pool saturated ({_inflight}/{_POOL_WORKERS} in-flight) — "
                "hung backend call(s) have leaked every worker slot"
            )
        _inflight += 1
    try:
        future = _pool.submit(fn)
    except BaseException:
        with _inflight_lock:
            _inflight -= 1
        raise
    future.add_done_callback(_release)
    return future


def _with_timeout(fn: Callable[[], Any], timeout: float, what: str) -> Any:
    """Run a sync callable with a hard wall-clock timeout via the bounded pool."""
    future = _submit_bounded(fn)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout as exc:
        future.cancel()
        raise ReasoningError(f"{what} timed out after {timeout:.0f}s") from exc


# --------------------------------------------------------------------------------------
# JSON extraction — balanced-brace walker (robust to fences / trailing prose)
# --------------------------------------------------------------------------------------
def _first_balanced_json(text: str) -> str | None:
    """Return the first balanced ``{...}`` or ``[...]`` span, respecting string literals.

    A greedy regex grabs from the first brace to the LAST brace, mangling replies with
    multiple JSON values or braces in trailing prose; this walks the structure honestly.
    """
    start = None
    opener = closer = ""
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start, opener = i, ch
                closer = "}" if ch == "{" else "]"
                depth = 1
            continue
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply (handles code fences and surrounding prose)."""
    span = _first_balanced_json(text)
    if span is None:
        raise ReasoningError("no JSON object/array found in reply")
    try:
        return json.loads(span)
    except json.JSONDecodeError as exc:
        raise ReasoningError(f"reply contained malformed JSON: {exc}") from exc


# --------------------------------------------------------------------------------------
# Tier backends (lazy imports — module loads without them)
# --------------------------------------------------------------------------------------
def _bulk_complete(prompt: str, system: str | None, temperature: float, model: str) -> str:
    """Tier: BULK — local model runtime (loopback-enforced)."""
    require_loopback_url(BULK_BASE_URL, what="bulk-tier model base URL")
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise PermanentReasoningError(
            "bulk tier requires the 'reasoning' extra (langchain-ollama) — not installed"
        ) from exc

    client = ChatOllama(
        model=model, base_url=BULK_BASE_URL, temperature=temperature,
        client_kwargs={"timeout": BULK_TIMEOUT},
    )
    messages: list[tuple[str, str]] = []
    if system:
        messages.append(("system", system))
    messages.append(("human", prompt))
    try:
        reply = client.invoke(messages)
    except Exception as exc:
        msg = str(exc).lower()
        if "not found" in msg or "no such model" in msg or "try pulling" in msg:
            raise PermanentReasoningError(f"bulk model {model!r} not available: {exc}") from exc
        raise ReasoningError(f"bulk tier call failed: {exc}") from exc
    content = getattr(reply, "content", reply)
    if isinstance(content, str):
        return content
    return str(content)


def _high_stakes_complete(prompt: str, system: str | None, model: str | None) -> str:
    """Tier: HIGH_STAKES — frontier model via subscription CLI/Agent SDK (no metered key)."""
    try:
        import anyio
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise PermanentReasoningError(
            "high-stakes tier requires the 'reasoning' extra (claude-agent-sdk) — not installed"
        ) from exc
    if not os.environ.get(OAUTH_TOKEN_ENV):
        raise PermanentReasoningError(
            f"high-stakes tier requires {OAUTH_TOKEN_ENV} (subscription OAuth); none set"
        )

    options = ClaudeAgentOptions(
        system_prompt=system,
        model=model,
        permission_mode="dontAsk",
        setting_sources=[],
        allowed_tools=[],
        env=scrubbed_env(),  # ADR-0003: never pass a metered Anthropic credential
    )

    async def _drain() -> str:
        parts: list[str] = []
        async for message in query(prompt=prompt, options=options):
            text = getattr(message, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    try:
        out = anyio.run(_drain)
        return out if isinstance(out, str) else str(out)
    except Exception as exc:
        status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
        if status in (429, 529):
            raise RateLimitError(f"high-stakes tier rate-limited: {exc}") from exc
        if status in (401, 403):
            raise PermanentReasoningError(f"high-stakes tier auth failed: {exc}") from exc
        raise ReasoningError(f"high-stakes tier call failed: {exc}") from exc


def _attempt(request: ReasoningRequest) -> str:
    """Route one request to its tier backend (no retry here)."""
    if _truthy("ASSAY_DISABLE_REASONING"):
        raise ReasoningError("reasoning is disabled (ASSAY_DISABLE_REASONING)")
    p = request.params
    system = p.get("system")
    temperature = float(p.get("temperature", 0.0))
    model = p.get("model")
    if request.tier is StakesTier.BULK:
        return cast(
            str,
            _with_timeout(
                lambda: _bulk_complete(request.prompt, system, temperature, model or BULK_MODEL),
                BULK_TIMEOUT + 10,
                "bulk tier",
            ),
        )
    if request.tier is StakesTier.HIGH_STAKES:
        return cast(
            str,
            _with_timeout(
                lambda: _high_stakes_complete(request.prompt, system, model or HIGH_STAKES_MODEL),
                HIGH_STAKES_TIMEOUT + 30,
                "high-stakes tier",
            ),
        )
    raise PermanentReasoningError(f"unknown tier: {request.tier!r}")


def _run_with_retries(request: ReasoningRequest) -> str:
    """Execute with independent transient and rate-limit retry budgets."""
    transient = 0
    rate = 0
    while True:
        try:
            return _attempt(request)
        except PermanentReasoningError:
            raise
        except RateLimitError:
            if rate >= RATE_LIMIT_MAX_RETRIES:
                raise
            time.sleep(RATE_LIMIT_BACKOFF * (rate + 1))
            rate += 1
        except ReasoningError:
            if transient >= MAX_RETRIES:
                raise
            time.sleep(BACKOFF_BASE**transient)
            transient += 1


# --------------------------------------------------------------------------------------
# Public seam
# --------------------------------------------------------------------------------------
@runtime_checkable
class ReasoningSeam(Protocol):
    """Route a reasoning request to the appropriate tier with timeouts, retries, tracing."""

    def run(self, request: ReasoningRequest) -> str: ...


class TieredReasoningSeam:
    """Concrete tiered seam. ``run`` returns text; ``run_json`` parses a JSON reply.

    Backends and tracing are resolved lazily, so an instance constructs with no external
    dependencies; calls fail loud (``PermanentReasoningError``) if a tier's backend or its
    subscription token is absent.
    """

    def run(self, request: ReasoningRequest) -> str:
        return _run_with_retries(request)

    def run_json(self, request: ReasoningRequest) -> Any:
        return extract_json(self.run(request))

    @staticmethod
    def is_available(tier: StakesTier) -> bool:
        """Cheap liveness check (spends no LLM turn). Never raises — returns False on error."""
        if _truthy("ASSAY_DISABLE_REASONING"):
            return False
        try:
            if tier is StakesTier.BULK:
                require_loopback_url(BULK_BASE_URL, what="bulk-tier model base URL")
                import urllib.request

                with urllib.request.urlopen(f"{BULK_BASE_URL}/api/tags", timeout=2) as resp:
                    return bool(resp.status == 200)
            if tier is StakesTier.HIGH_STAKES:
                import shutil

                return shutil.which("claude") is not None and bool(
                    os.environ.get(OAUTH_TOKEN_ENV)
                )
        except Exception:
            return False
        return False


class UnconfiguredReasoningSeam:
    """Explicit fail-loud seam for contexts that must not perform reasoning."""

    def run(self, request: ReasoningRequest) -> str:
        raise NotImplementedError(
            "this context uses an UnconfiguredReasoningSeam — supply a TieredReasoningSeam "
            "(or a test double) to perform reasoning"
        )
