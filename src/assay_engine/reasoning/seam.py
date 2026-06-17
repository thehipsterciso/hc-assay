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

import atexit
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol, cast

from assay_engine._frozen import freeze_mapping
from assay_engine._local import require_loopback_url


class StakesTier(Enum):
    BULK = "bulk"  # local model — high volume, low stakes
    HIGH_STAKES = "high"  # frontier model via fixed-cost subscription — gated, traced


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
# Cap BULK generation length. ChatOllama/Ollama default to unbounded (-1); without a cap a
# local model can run away to context exhaustion, and the wall-clock timeout cannot interrupt a
# call already blocked in the backend (a leaked pool slot). Bounding output tokens is the real
# guard (LangChain's own ChatOllama example sets num_predict explicitly).
BULK_NUM_PREDICT = max(1, int(_env("ASSAY_BULK_NUM_PREDICT", "2048")))
HIGH_STAKES_TIMEOUT = max(1.0, float(_env("ASSAY_HIGH_STAKES_TIMEOUT", "300")))

MAX_RETRIES = max(0, int(_env("ASSAY_REASONING_RETRIES", "2")))
BACKOFF_BASE = max(0.0, float(_env("ASSAY_REASONING_BACKOFF", "1.5")))
RATE_LIMIT_BACKOFF = max(0.0, float(_env("ASSAY_RATELIMIT_BACKOFF", "30")))
RATE_LIMIT_MAX_RETRIES = max(0, int(_env("ASSAY_RATELIMIT_RETRIES", "5")))
# run_json re-rolls on a PARSE failure. This is independent of the transient/rate-limit retry
# budget above (which applies per generation) so the two do not multiply into a retry storm; an
# overall wall-clock deadline bounds the total regardless (#102).
JSON_REROLLS = max(0, int(_env("ASSAY_JSON_REROLLS", "2")))
RUN_JSON_DEADLINE = max(1.0, float(_env("ASSAY_RUN_JSON_DEADLINE", "600")))

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

    The match is case-insensitive (pass 3, #F-003): a metered key set under a non-uppercase name
    (``anthropic_api_key``) must scrub too — the AWS_/GOOGLE_ checks already uppercase, so this
    closes the one credential path that did not.
    """
    ku = key.upper()
    return ku.startswith("ANTHROPIC_") and ("KEY" in ku or "TOKEN" in ku)


# Env vars that — beyond metered credentials — would redirect the subprocess OFF-BOX or onto a
# metered provider, defeating ADR-0003 / "no metered API". The claude CLI honours all of these.
_UNSAFE_SUBPROCESS_VARS = frozenset(
    {
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_API_KEY_HELPER",
        "GOOGLE_APPLICATION_CREDENTIALS",
        # TLS-trust / egress-interception knobs the Node-based CLI honours: a custom CA or disabled
        # cert verification enables a transparent off-box MITM proxy (pass 4, #G-018).
        "NODE_EXTRA_CA_CERTS",
        "NODE_TLS_REJECT_UNAUTHORIZED",
    }
)


def is_unsafe_subprocess_var(key: str) -> bool:
    """True for any env var that must not reach the high-stakes subprocess (#101).

    Covers metered credentials, off-box/metered-provider redirects, proxies (which redirect
    egress), cloud-provider credentials (AWS_*/GOOGLE_*), and TLS-trust overrides. The ENTIRE
    ``ANTHROPIC_*`` namespace is scrubbed (#G-018): any such var configures the SDK's endpoint /
    auth / headers and could redirect off-box or onto a metered provider — the subscription token
    is ``CLAUDE_CODE_OAUTH_TOKEN`` (no ``ANTHROPIC_`` prefix) and is deliberately NOT matched.
    """
    ku = key.upper()
    return (
        ku.startswith(
            "ANTHROPIC_"
        )  # whole namespace: endpoint/auth/headers/custom-headers (#G-018)
        or ku in _UNSAFE_SUBPROCESS_VARS
        or ku.endswith("_PROXY")  # HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY (any case)
        or ku.startswith("AWS_")
        or ku.startswith("GOOGLE_")
    )


def scrubbed_env() -> dict[str, str]:
    """The process env hardened for the high-stakes subprocess (ADR-0003 / no metered API).

    Every unsafe var (:func:`is_unsafe_subprocess_var`) is **overwritten to empty**, not merely
    omitted. The claude-agent-sdk builds the child env as ``{**os.environ, **options.env}`` — it
    *merges* over the inherited environment — so a dropped key would silently fall through to its
    inherited value (the metered key / off-box redirect would survive). Setting it to ``""`` in
    the dict we hand over guarantees the merge overwrites the inherited value (#101). The
    subscription OAuth token is preserved so the fixed-cost path still authenticates.
    """
    env = dict(os.environ)
    for k in list(env):
        if is_unsafe_subprocess_var(k):
            env[k] = ""
    return env


# --------------------------------------------------------------------------------------
# Bounded timeout pool with saturation guard
# --------------------------------------------------------------------------------------
_POOL_WORKERS = 8
_pool = ThreadPoolExecutor(max_workers=_POOL_WORKERS, thread_name_prefix="reasoning-timeout")
# Shut the pool down at interpreter exit (#F-043). wait=False avoids blocking exit on in-flight
# backend calls (already bounded by _with_timeout); without this, module globals can be torn down
# while a worker is mid-call, leaving behavior undefined. Mirrors checkpoint.py's atexit cleanup.
atexit.register(_pool.shutdown, wait=False)
_inflight = 0
_inflight_lock = threading.Lock()


def _release(future: Any) -> None:
    # Idempotent per future (#F-032 follow-up): decrement _inflight AT MOST ONCE for a given
    # future. The done-callback path and the interrupt-window fallback in _submit_bounded can BOTH
    # reach _release for the same future when add_done_callback appended the callback and then was
    # interrupted before returning — without this guard that double-decrements and over-releases a
    # slot (the inverse of the leak being fixed). A per-future flag set under the lock makes the
    # "_release runs at most once" claim true rather than aspirational.
    global _inflight
    with _inflight_lock:
        if getattr(future, "_assay_released", False):
            return
        try:
            future._assay_released = True
        except (AttributeError, TypeError):  # pragma: no cover - Future allows attrs; defensive
            pass
        _inflight -= 1


def _submit_bounded(fn: Callable[[], Any]) -> Any:
    """Submit to the shared pool, refusing if every worker slot is already in flight
    (hung backend calls would otherwise leak all slots)."""
    global _inflight
    with _inflight_lock:
        if _inflight >= _POOL_WORKERS:
            # Saturation is a TRANSIENT condition — surface a retryable backpressure signal so
            # _run_with_retries waits and re-tries rather than failing the caller permanently
            # (#104). Concurrent callers thus queue briefly instead of erroring out.
            raise RateLimitError(
                f"reasoning timeout pool saturated ({_inflight}/{_POOL_WORKERS} in-flight) — "
                "backpressure; retry shortly"
            )
        _inflight += 1
    try:
        future = _pool.submit(fn)
    except RuntimeError as exc:  # pool shut down at interpreter exit — normalize, don't leak (#116)
        with _inflight_lock:
            _inflight -= 1
        raise PermanentReasoningError(f"reasoning pool is shut down: {exc}") from exc
    except BaseException:
        with _inflight_lock:
            _inflight -= 1
        raise
    # Register the slot-release callback under its own guard (#F-032): if a BaseException
    # (KeyboardInterrupt/SystemExit) fires while attaching the callback, release the slot
    # explicitly so a permanent leak can't accumulate and brick the pool with spurious
    # RateLimitErrors. If the interrupt landed AFTER add_done_callback already appended the
    # callback (so it will still fire on completion), the explicit _release here and the later
    # callback both target this future — _release is per-future idempotent, so the slot is
    # released exactly once either way.
    try:
        future.add_done_callback(_release)
    except BaseException:
        _release(future)
        raise
    return future


def _with_timeout(fn: Callable[[], Any], timeout: float, what: str) -> Any:
    """Run a sync callable with a hard wall-clock timeout via the bounded pool."""
    future = _submit_bounded(fn)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout as exc:
        # No future.cancel(): a ThreadPoolExecutor cannot interrupt a thread already blocked
        # in a backend call. The worker keeps its slot until the call returns; the bounded
        # pool's saturation guard is the real protection against leaked/hung slots.
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
def _bulk_complete(
    prompt: str,
    system: str | None,
    temperature: float,
    model: str,
    json_mode: bool = False,
    *,
    seed: int | None = None,
    json_schema: dict[str, Any] | None = None,
) -> str:
    """Tier: BULK — local model runtime (loopback-enforced).

    ``num_predict`` is always set (bounded generation). For JSON, a caller-supplied
    ``json_schema`` uses Ollama's schema-constrained decoding (the reliable path); otherwise
    ``json_mode`` falls back to loose ``format="json"``. ``seed`` lets a retry force a different
    deterministic decode without sharpening temperature.
    """
    require_loopback_url(BULK_BASE_URL, what="bulk-tier model base URL")
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise PermanentReasoningError(
            "bulk tier requires the 'reasoning' extra (langchain-ollama) — not installed"
        ) from exc

    # BULK's INNER bound (#G-003): the sync-tier counterpart to HIGH_STAKES's anyio.fail_after.
    # A ThreadPoolExecutor worker blocked in client.invoke() cannot be interrupted by the outer
    # _with_timeout, so the HTTP client timeout is what actually frees the slot on a hung backend.
    # A bare float sets EVERY httpx phase (connect/read/write/pool) to BULK_TIMEOUT, so a slow
    # connect THEN a slow read could total ~2*BULK_TIMEOUT — past the outer BULK_TIMEOUT+10 bound,
    # leaking the slot. Use an explicit Timeout so the TOTAL stays ~BULK_TIMEOUT (+ a small connect)
    # and aligns with the outer headroom. Fall back to the float if httpx is absent.
    try:
        import httpx

        _bulk_timeout: Any = httpx.Timeout(
            BULK_TIMEOUT, connect=min(10.0, BULK_TIMEOUT), pool=min(10.0, BULK_TIMEOUT)
        )
    except ImportError:  # pragma: no cover - httpx ships with the reasoning extra
        _bulk_timeout = BULK_TIMEOUT
    kwargs: dict[str, Any] = dict(
        model=model,
        base_url=BULK_BASE_URL,
        temperature=temperature,
        num_predict=BULK_NUM_PREDICT,  # bound generation length (H1)
        client_kwargs={"timeout": _bulk_timeout},
    )
    if seed is not None:
        kwargs["seed"] = seed
    if json_schema is not None:
        kwargs["format"] = json_schema  # Ollama schema-constrained decoding (reliable JSON)
    elif json_mode:
        kwargs["format"] = "json"  # loose native JSON decoding (syntactic only)
    client = ChatOllama(**kwargs)
    messages: list[tuple[str, str]] = []
    if system:
        messages.append(("system", system))
    messages.append(("human", prompt))
    try:
        reply = client.invoke(messages)
    except Exception as exc:
        # Prefer the typed HTTP status (ollama.ResponseError / httpx carry one): 404 = the model
        # isn't pulled → permanent. Fall back to substring matching only if no status is exposed
        # (robust to upstream message-wording changes — audit M4).
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        msg = str(exc).lower()
        permanent = status == 404 or any(
            s in msg for s in ("not found", "no such model", "try pulling")
        )
        if permanent:
            raise PermanentReasoningError(f"bulk model {model!r} not available: {exc}") from exc
        raise ReasoningError(f"bulk tier call failed: {exc}") from exc
    content = getattr(reply, "content", reply)
    text = content if isinstance(content, str) else str(content)
    text = text.strip()
    if not text:  # an empty reply is not a valid result — retry, don't return "" (issue #5/R5)
        raise ReasoningError("bulk tier returned an empty reply")
    return text


def _high_stakes_auth_present() -> bool:
    """Subscription auth available: an exported OAuth token OR a stored CLI credentials file
    (the normal state after ``claude login`` without exporting a token)."""
    if os.environ.get(OAUTH_TOKEN_ENV):
        return True
    return (Path.home() / ".claude" / ".credentials.json").is_file()


def _high_stakes_complete(prompt: str, system: str | None, model: str | None) -> str:
    """Tier: HIGH_STAKES — frontier model via subscription CLI/Agent SDK (no metered key)."""
    try:
        import anyio
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise PermanentReasoningError(
            "high-stakes tier requires the 'reasoning' extra (claude-agent-sdk) — not installed"
        ) from exc
    if not _high_stakes_auth_present():
        raise PermanentReasoningError(
            f"high-stakes tier requires subscription auth ({OAUTH_TOKEN_ENV} or a stored "
            "~/.claude/.credentials.json); none found"
        )

    options = ClaudeAgentOptions(
        system_prompt=system,
        model=model,
        permission_mode="dontAsk",
        setting_sources=[],
        allowed_tools=[],
        env=scrubbed_env(),  # ADR-0003: never pass a metered Anthropic credential
    )

    parts: list[str] = []
    result_error: dict[str, Any] | None = None

    async def _drain() -> None:
        # The CLI/SDK signals rate windows and API failures by COMPLETING the stream
        # (a RateLimitEvent, or a terminal ResultMessage with is_error) — NOT by raising.
        # We must inspect the stream, not just catch exceptions (issue #R4).
        #
        # Inner cancellation (#127): wrap the stream in anyio.fail_after so a hung subprocess is
        # actually CANCELLED (the cancellation propagates into query() and tears down the child),
        # freeing the bounded-pool worker. The outer _with_timeout only raises in the caller; it
        # cannot cancel this thread, so without this a hung HIGH_STAKES call would leak its slot
        # permanently. Fires before the outer wall-clock (HIGH_STAKES_TIMEOUT + 30).
        nonlocal result_error
        with anyio.fail_after(HIGH_STAKES_TIMEOUT):
            await _drain_stream()

    async def _drain_stream() -> None:
        nonlocal result_error
        async for msg in query(prompt=prompt, options=options):
            if type(msg).__name__ == "RateLimitEvent":
                rl = getattr(getattr(msg, "rate_limit_info", None), "status", None)
                if rl == "rejected":
                    result_error = {"status": 429, "detail": "RateLimitEvent rejected"}
                continue
            if getattr(msg, "status", None) == "rejected":
                result_error = {"status": 429, "detail": "rejected"}
                continue
            if isinstance(msg, AssistantMessage):
                for block in getattr(msg, "content", []) or []:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                # Do not let a trailing ResultMessage clobber an already-captured 429.
                if getattr(msg, "is_error", False) and not (
                    result_error and result_error.get("status") == 429
                ):
                    result_error = {
                        "status": getattr(msg, "api_error_status", None),
                        "detail": getattr(msg, "errors", None) or getattr(msg, "stop_reason", None),
                    }

    try:
        anyio.run(_drain)
    except Exception as exc:
        raise ReasoningError(f"high-stakes tier call failed: {exc}") from exc

    if result_error is not None:
        status = result_error.get("status")
        detail = result_error.get("detail") or status
        if status in (429, 529):
            raise RateLimitError(f"high-stakes tier rate window ({status}): {detail}")
        if status in (401, 403):
            raise PermanentReasoningError(f"high-stakes tier auth failed ({status}): {detail}")
        raise ReasoningError(f"high-stakes tier reported an error (status={status}): {detail}")

    text = "".join(parts).strip()
    if not text:  # empty frontier reply is not a valid result — retry (issue #R5)
        raise ReasoningError("high-stakes tier returned an empty reply")
    return text


def _attempt(request: ReasoningRequest) -> str:
    """Route one request to its tier backend (no retry here)."""
    if _truthy("ASSAY_DISABLE_REASONING"):
        raise ReasoningError("reasoning is disabled (ASSAY_DISABLE_REASONING)")
    p = request.params
    system = p.get("system")
    model = p.get("model")
    json_mode = bool(p.get("_json_mode", False))
    json_schema = p.get("json_schema")  # optional caller schema → constrained JSON decoding
    # Coerce numeric params behind the typed error contract (#H-004): a malformed temperature/seed
    # (e.g. "hot") would otherwise raise a raw ValueError/TypeError that escapes run()/run_json,
    # which document only ReasoningError. A bad param is a caller bug, not transient → permanent.
    try:
        temperature = float(p.get("temperature", 0.0))
        seed_raw = p.get("_seed")
        seed = int(seed_raw) if seed_raw is not None else None
    except (ValueError, TypeError) as exc:
        raise PermanentReasoningError(f"malformed reasoning params: {exc}") from exc
    if request.tier is StakesTier.BULK:
        return cast(
            str,
            _with_timeout(
                lambda: _bulk_complete(
                    request.prompt,
                    system,
                    temperature,
                    model or BULK_MODEL,
                    json_mode,
                    seed=seed,  # already coerced to int|None above (#H-004)
                    json_schema=json_schema,
                ),
                BULK_TIMEOUT + 10,
                "bulk tier",
            ),
        )
    if request.tier is StakesTier.HIGH_STAKES:
        # The high-stakes tier runs the Claude CLI subprocess (not the in-process Anthropic SDK,
        # so no auto-instrumentor covers it) — emit an explicit OpenInference LLM span so Phoenix
        # records the model/provider for this otherwise-untraced tier (#2).
        llm_attrs = {
            "llm.provider": "anthropic",
            "llm.system": "anthropic",
            "llm.model_name": str(model or HIGH_STAKES_MODEL or "subscription-default"),
        }
        with _span("reasoning.high_stakes", llm_attrs, kind="LLM"):
            return cast(
                str,
                _with_timeout(
                    lambda: _high_stakes_complete(
                        request.prompt, system, model or HIGH_STAKES_MODEL
                    ),
                    HIGH_STAKES_TIMEOUT + 30,
                    "high-stakes tier",
                ),
            )
    raise PermanentReasoningError(f"unknown tier: {request.tier!r}")


def _sleep_bounded(secs: float, deadline: float | None) -> None:
    """Sleep ``secs``, but never past ``deadline`` — so backoff can't blow an overall budget.

    If the deadline has already passed, raise instead of sleeping the full interval, so a long
    rate-limit backoff cannot keep a caller blocked well beyond its deadline (#102).
    """
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReasoningError("reasoning deadline exceeded during backoff")
        secs = min(secs, remaining)
    time.sleep(secs)


def _run_with_retries(request: ReasoningRequest, *, deadline: float | None = None) -> str:
    """Execute with independent transient and rate-limit retry budgets.

    ``deadline`` (monotonic seconds) bounds both the cumulative backoff AND entry into each
    retry: once the deadline has passed, no further ``_attempt`` is started (#102, #F-022). It
    does not interrupt an attempt already in flight — that is bounded by the per-call timeout —
    so total wall-clock is at most ``deadline`` plus one in-flight attempt's timeout, not
    ``deadline`` plus the full retry budget of per-call timeouts.
    """
    transient = 0
    rate = 0
    attempted = False
    while True:
        # Gate retry ENTRY on the deadline (#F-022): the first attempt always runs, but a retry is
        # not started once the deadline is past — otherwise the per-attempt timeouts could stack
        # well beyond the overall budget even though the backoff sleeps were bounded.
        if attempted and deadline is not None and time.monotonic() >= deadline:
            raise ReasoningError("reasoning deadline exceeded before retry")
        attempted = True
        try:
            return _attempt(request)
        except PermanentReasoningError:
            raise
        except RateLimitError:
            if rate >= RATE_LIMIT_MAX_RETRIES:
                raise
            _sleep_bounded(RATE_LIMIT_BACKOFF * (rate + 1), deadline)
            rate += 1
        except ReasoningError:
            if transient >= MAX_RETRIES:
                raise
            _sleep_bounded(BACKOFF_BASE**transient, deadline)
            transient += 1


# --------------------------------------------------------------------------------------
# Public seam
# --------------------------------------------------------------------------------------
# Structural Protocol only — adapter/seam validation is behavior-based, not isinstance (#148).
class ReasoningSeam(Protocol):
    """Route a reasoning request to the appropriate tier with timeouts, retries, tracing."""

    def run(self, request: ReasoningRequest) -> str: ...


@contextmanager
def _span(name: str, attributes: Mapping[str, Any], *, kind: str = "AGENT") -> Iterator[None]:
    """Emit an OpenTelemetry span if a provider is registered; a cheap no-op otherwise.

    Stamps the OpenInference ``openinference.span.kind`` (default ``AGENT`` — a reasoning call)
    so Phoenix classifies the span instead of rendering it UNKNOWN. OpenTelemetry is imported
    lazily, so the seam traces when the (self-hosted, on-box) observability stack is wired and is
    a silent no-op in tests / offline (ADR-0003).
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return
    tracer = trace.get_tracer("assay_engine.reasoning")
    # start_as_current_span auto-records exceptions + sets ERROR status by default (#F-005 was a
    # false positive — see assay_engine.observability.tracing for the verification note).
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("openinference.span.kind", kind)
        for k, v in attributes.items():
            span.set_attribute(k, v)
        yield


class TieredReasoningSeam:
    """Concrete tiered seam. ``run`` returns text; ``run_json`` parses a JSON reply.

    Backends and tracing are resolved lazily, so an instance constructs with no external
    dependencies; calls fail loud (``PermanentReasoningError``) if a tier's backend or its
    subscription auth is absent. When the observability stack is present, each call emits an
    OpenTelemetry span; otherwise tracing is a no-op.
    """

    def run(self, request: ReasoningRequest) -> str:
        attrs = {"assay.tier": request.tier.value, "assay.purpose": request.purpose}
        with _span("reasoning.run", attrs):
            return _run_with_retries(request)

    def run_json(self, request: ReasoningRequest) -> Any:
        """Generate and parse JSON, re-rolling on parse failure.

        If the caller supplies ``params["json_schema"]``, the BULK tier uses Ollama's
        schema-constrained decoding (the reliable path). Otherwise it falls back to loose JSON
        mode + prompt instruction. BULK decoding can be deterministic (temp 0), so re-issuing the
        identical prompt would yield a byte-identical bad reply; each retry **varies the seed**
        (forcing a different deterministic decode) and *monotonically* raises temperature toward
        1.0 — never lowering it, so re-rolls never sharpen back toward the same output. ``params``
        is frozen, so each attempt builds a fresh request (issue #R6).
        """
        base_temp = float(request.params.get("temperature", 0.0))
        system = request.params.get("system")
        json_system = (
            f"{system}\n\nRespond with ONLY a single JSON value, no prose."
            if system
            else "Respond with ONLY a single JSON value, no prose."
        )
        last: ReasoningError | None = None
        deadline = time.monotonic() + RUN_JSON_DEADLINE  # overall bound across all re-rolls (#102)
        with _span(
            "reasoning.run_json",
            {"assay.tier": request.tier.value, "assay.purpose": request.purpose},
        ):
            for attempt in range(JSON_REROLLS + 1):
                if attempt > 0 and time.monotonic() >= deadline:
                    raise last or ReasoningError("run_json exceeded its overall deadline")
                temp = min(1.0, base_temp + 0.2 * attempt)  # monotonic, never decreases (M3)
                params = dict(request.params)
                params.update(temperature=temp, system=json_system, _json_mode=True, _seed=attempt)
                attempt_req = ReasoningRequest(
                    prompt=request.prompt,
                    tier=request.tier,
                    purpose=request.purpose,
                    params=params,
                )
                # A transient/rate/permanent error is already handled (and bounded by the shared
                # deadline) inside _run_with_retries — let it PROPAGATE rather than re-rolling, so
                # the budgets do NOT multiply (#102). We re-roll ONLY on a JSON *parse* failure.
                text = _run_with_retries(attempt_req, deadline=deadline)
                try:
                    return extract_json(text)
                except ReasoningError as exc:  # parse failure → re-roll with a new seed
                    last = exc
            raise last if last is not None else ReasoningError("run_json failed")

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

                return shutil.which("claude") is not None and _high_stakes_auth_present()
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
