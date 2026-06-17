"""High-stakes (T3) stream-drain + error classification — exercised via synthetic SDK messages.

The real `_high_stakes_complete._drain` and its 429/auth/error/empty classification is the most
dangerous untested code (it adjudicates high-stakes verdicts and maps subscription rate
windows). Validating it against the real frontier costs a metered call and only runs when
`ASSAY_RUN_HIGH_STAKES_TESTS=1`. Here we drive the REAL drain logic by injecting a fake
`claude_agent_sdk` whose `query` yields synthetic `AssistantMessage`/`RateLimitEvent`/
`ResultMessage` objects — covering the classification branches in CI with no metered call.

Requires anyio (the reasoning extra is async); skips otherwise.
"""

from __future__ import annotations

import sys
import types

import pytest

pytest.importorskip("anyio")

from assay_engine.reasoning import seam as rc  # noqa: E402
from assay_engine.reasoning.seam import (  # noqa: E402
    PermanentReasoningError,
    RateLimitError,
    ReasoningError,
)


class _TextBlock:
    def __init__(self, text):
        self.text = text


class _AssistantMessage:
    def __init__(self, content):
        self.content = content


class _ResultMessage:
    def __init__(self, is_error=False, api_error_status=None, errors=None, stop_reason=None):
        self.is_error = is_error
        self.api_error_status = api_error_status
        self.errors = errors
        self.stop_reason = stop_reason


class RateLimitEvent:  # name matters: the engine matches by type(msg).__name__ (real SDK contract)
    def __init__(self, status):
        self.rate_limit_info = types.SimpleNamespace(status=status)


class _ClaudeAgentOptions:
    def __init__(self, **kw):
        self.__dict__.update(kw)


_HANG = object()  # sentinel: query awaits "forever" to simulate a hung subprocess (#127)


@pytest.fixture
def fake_sdk(monkeypatch):
    """Inject a fake claude_agent_sdk whose `query` yields a scripted message stream.

    Exposes the captured ClaudeAgentOptions via ``scripted.captured_options`` so tests can assert
    the security wiring (env=scrubbed_env, sandbox flags) actually reaches the subprocess.
    """
    import anyio

    class _Scripted(list):
        captured_options = None  # query records the ClaudeAgentOptions it received here

    scripted = _Scripted()

    async def query(prompt, options):  # noqa: ANN001
        scripted.captured_options = options
        for msg in scripted:
            if msg is _HANG:  # simulate a hung subprocess; inner fail_after must cancel us
                await anyio.sleep(3600)
            if isinstance(msg, Exception):  # simulate the SDK/transport raising mid-stream
                raise msg
            yield msg

    mod = types.ModuleType("claude_agent_sdk")
    mod.AssistantMessage = _AssistantMessage
    mod.ResultMessage = _ResultMessage
    mod.TextBlock = _TextBlock
    mod.ClaudeAgentOptions = _ClaudeAgentOptions
    mod.query = query
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", mod)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-subscription-token")
    return scripted


def _run(prompt="hi", system=None, model=None):
    return rc._high_stakes_complete(prompt, system, model)


def test_t3_success_collects_text_blocks(fake_sdk):
    fake_sdk.append(_AssistantMessage([_TextBlock("po"), _TextBlock("ng")]))
    assert _run() == "pong"


def test_t3_wires_scrubbed_env_into_subprocess_options(fake_sdk, monkeypatch):
    # #124: the no-metered-API firewall must be wired end-to-end — env=scrubbed_env() must reach
    # the ClaudeAgentOptions handed to the subprocess (not just be unit-tested in isolation).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-metered-LEAK")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://attacker.example")
    fake_sdk.append(_AssistantMessage([_TextBlock("pong")]))
    _run()
    opts = fake_sdk.captured_options
    assert hasattr(opts, "env"), "env not wired into ClaudeAgentOptions (#124 firewall unguarded)"
    # the merged child env must neutralize the metered key + off-box redirect, keep OAuth
    child = {**__import__("os").environ, **opts.env}
    assert child["ANTHROPIC_API_KEY"] == "" and child["ANTHROPIC_BASE_URL"] == ""
    assert child["CLAUDE_CODE_OAUTH_TOKEN"] == "test-subscription-token"


def test_t3_wires_subprocess_sandbox_settings(fake_sdk):
    # #125: the subprocess sandbox flags must actually reach the options (no tools, no settings
    # sources, non-interactive permission mode).
    fake_sdk.append(_AssistantMessage([_TextBlock("pong")]))
    _run()
    opts = fake_sdk.captured_options
    assert opts.allowed_tools == []  # no tools may run in a reasoning call
    assert opts.setting_sources == []  # do not load ambient project/user settings
    assert opts.permission_mode == "dontAsk"  # non-interactive, deny-by-default


def test_t3_hung_subprocess_is_cancelled_not_leaked(fake_sdk, monkeypatch):
    # #127: a hung stream must be cancelled by the inner timeout (frees the pool slot) and
    # surface a typed ReasoningError — not block forever.
    monkeypatch.setattr(rc, "HIGH_STAKES_TIMEOUT", 0.3)
    fake_sdk.append(_HANG)
    import time as _t

    t0 = _t.monotonic()
    with pytest.raises(ReasoningError):
        _run()
    assert _t.monotonic() - t0 < 5  # cancelled promptly near the 0.3s inner timeout, not hung


def _assert_transient(excinfo):
    # #J-005: RateLimitError and PermanentReasoningError both SUBCLASS ReasoningError, so
    # `pytest.raises(ReasoningError)` does NOT discriminate a transient mapping from a rate-limit
    # or permanent one. Assert the exception is the transient class itself, not a decisive subclass.
    assert not isinstance(excinfo.value, (RateLimitError, PermanentReasoningError)), (
        f"expected a transient ReasoningError, got {type(excinfo.value).__name__}"
    )


def test_t3_empty_reply_raises_transient(fake_sdk):
    fake_sdk.append(_AssistantMessage([]))  # no text blocks -> empty
    with pytest.raises(ReasoningError) as ei:
        _run()
    _assert_transient(ei)


def test_t3_rate_limit_event_rejected_maps_to_ratelimit(fake_sdk):
    fake_sdk.append(RateLimitEvent("rejected"))
    with pytest.raises(RateLimitError):
        _run()


def test_t3_rate_limit_allowed_is_not_an_error(fake_sdk):
    # an informational 'allowed' rate event must NOT trigger backpressure; text still returns
    fake_sdk.append(RateLimitEvent("allowed"))
    fake_sdk.append(_AssistantMessage([_TextBlock("ok")]))
    assert _run() == "ok"


def test_t3_auth_error_maps_to_permanent(fake_sdk):
    fake_sdk.append(_ResultMessage(is_error=True, api_error_status=401, errors=["unauth"]))
    with pytest.raises(PermanentReasoningError):
        _run()


def test_t3_generic_error_maps_to_transient(fake_sdk):
    fake_sdk.append(_ResultMessage(is_error=True, api_error_status=500, errors=["boom"]))
    with pytest.raises(ReasoningError) as ei:
        _run()
    _assert_transient(ei)  # a 500 must be transient, NOT permanent/rate-limit (#J-005)


def test_t3_429_not_clobbered_by_trailing_result_error(fake_sdk):
    # a RateLimitEvent(rejected) must win over a later ResultMessage error (preserve backpressure)
    fake_sdk.append(RateLimitEvent("rejected"))
    fake_sdk.append(_ResultMessage(is_error=True, api_error_status=500))
    with pytest.raises(RateLimitError):
        _run()


def test_t3_overloaded_529_maps_to_ratelimit(fake_sdk):
    fake_sdk.append(_ResultMessage(is_error=True, api_error_status=529, errors=["overloaded"]))
    with pytest.raises(RateLimitError):
        _run()


def test_t3_forbidden_403_maps_to_permanent(fake_sdk):
    fake_sdk.append(_ResultMessage(is_error=True, api_error_status=403, errors=["forbidden"]))
    with pytest.raises(PermanentReasoningError):
        _run()


def test_t3_top_level_rejected_status_maps_to_ratelimit(fake_sdk):
    # a non-RateLimitEvent message carrying status=='rejected' is the second 429 path
    msg = types.SimpleNamespace(status="rejected")
    fake_sdk.append(msg)
    with pytest.raises(RateLimitError):
        _run()


def test_t3_sdk_raises_mid_stream_maps_to_transient(fake_sdk):
    # the SDK/transport raising (rather than completing the stream) is a transient failure
    fake_sdk.append(RuntimeError("connection reset"))
    with pytest.raises(ReasoningError) as ei:
        _run()
    _assert_transient(ei)  # transport raise must be transient, not permanent/rate-limit (#J-005)


def test_t3_missing_auth_fails_loud(monkeypatch, fake_sdk):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(rc, "_high_stakes_auth_present", lambda: False)
    with pytest.raises(PermanentReasoningError, match="subscription auth"):
        _run()
