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


@pytest.fixture
def fake_sdk(monkeypatch):
    """Inject a fake claude_agent_sdk whose `query` yields a scripted message stream."""
    scripted: list = []

    async def query(prompt, options):  # noqa: ANN001
        for msg in scripted:
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


def test_t3_empty_reply_raises_transient(fake_sdk):
    fake_sdk.append(_AssistantMessage([]))  # no text blocks -> empty
    with pytest.raises(ReasoningError):
        _run()


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
    with pytest.raises(ReasoningError):
        _run()


def test_t3_429_not_clobbered_by_trailing_result_error(fake_sdk):
    # a RateLimitEvent(rejected) must win over a later ResultMessage error (preserve backpressure)
    fake_sdk.append(RateLimitEvent("rejected"))
    fake_sdk.append(_ResultMessage(is_error=True, api_error_status=500))
    with pytest.raises(RateLimitError):
        _run()


def test_t3_missing_auth_fails_loud(monkeypatch, fake_sdk):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(rc, "_high_stakes_auth_present", lambda: False)
    with pytest.raises(PermanentReasoningError, match="subscription auth"):
        _run()
