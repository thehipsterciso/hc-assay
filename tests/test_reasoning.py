"""Tiered reasoning seam — hardened invariants, all offline (backends never invoked).

Covers credential scrubbing, JSON extraction, retry budgets, the timeout/saturation guard,
loopback enforcement, and the kill switch — ported from the prior platform's reasoning tests.
"""

import pytest

from assay_engine._local import NonLocalEndpointError, require_loopback_url
from assay_engine.reasoning import seam as rc
from assay_engine.reasoning.seam import (
    PermanentReasoningError,
    RateLimitError,
    ReasoningError,
    ReasoningRequest,
    StakesTier,
    TieredReasoningSeam,
    extract_json,
    is_metered_anthropic_credential,
    scrubbed_env,
)


def _req(tier=StakesTier.BULK, **params) -> ReasoningRequest:
    return ReasoningRequest(prompt="p", tier=tier, purpose="t", params=params)


# ---- credential scrubbing (ADR-0003 / no metered API) ----

@pytest.mark.parametrize(
    "key,metered",
    [
        ("ANTHROPIC_API_KEY", True),
        ("ANTHROPIC_AUTH_TOKEN", True),
        ("ANTHROPIC_FOUNDRY_API_KEY", True),
        ("ANTHROPIC_FUTURE_TOKEN", True),  # forward-proofing
        ("ANTHROPIC_BASE_URL", False),     # not a credential
        ("CLAUDE_CODE_OAUTH_TOKEN", False),  # subscription auth — keep
        ("PATH", False),
    ],
)
def test_is_metered_credential_matches_shape(key, metered):
    assert is_metered_anthropic_credential(key) is metered


def test_scrubbed_env_strips_metered_keeps_subscription(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-remove")
    monkeypatch.setenv("ANTHROPIC_FUTURE_TOKEN", "remove")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:1234")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "keep")
    env = scrubbed_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_FUTURE_TOKEN" not in env
    assert env.get("ANTHROPIC_BASE_URL") == "http://localhost:1234"
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "keep"


# ---- JSON extraction / balanced-brace walker ----

@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ("```json\n{\"a\": 1}\n```", {"a": 1}),
        ('{"nested": {"s": "a } brace in a string"}}', {"nested": {"s": "a } brace in a string"}}),
        ('prefix {"relation": "subset"} trailing prose {junk', {"relation": "subset"}),
        ("[1, 2, 3]", [1, 2, 3]),
    ],
)
def test_extract_json_recovers(raw, expected):
    assert extract_json(raw) == expected


def test_extract_json_raises_when_absent():
    with pytest.raises(ReasoningError):
        extract_json("no json here")


def test_extract_json_raises_on_malformed():
    with pytest.raises(ReasoningError):
        extract_json('{"a": }')


# ---- retry budgets ----

def test_retry_then_success(monkeypatch):
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def flaky(_req):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ReasoningError("transient")
        return "ok"

    monkeypatch.setattr(rc, "_attempt", flaky)
    assert rc._run_with_retries(_req()) == "ok"
    assert calls["n"] == 2


def test_transient_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def always(_req):
        calls["n"] += 1
        raise ReasoningError("transient")

    monkeypatch.setattr(rc, "_attempt", always)
    with pytest.raises(ReasoningError):
        rc._run_with_retries(_req())
    assert calls["n"] == rc.MAX_RETRIES + 1


def test_permanent_error_not_retried(monkeypatch):
    calls = {"n": 0}

    def perm(_req):
        calls["n"] += 1
        raise PermanentReasoningError("nope")

    monkeypatch.setattr(rc, "_attempt", perm)
    with pytest.raises(PermanentReasoningError):
        rc._run_with_retries(_req())
    assert calls["n"] == 1


def test_rate_limit_uses_long_backpressure(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(rc.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def rated(_req):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RateLimitError("429")
        return "ok"

    monkeypatch.setattr(rc, "_attempt", rated)
    assert rc._run_with_retries(_req()) == "ok"
    # backpressure sleeps use RATE_LIMIT_BACKOFF * (attempt+1), not the small transient base
    assert sleeps == [rc.RATE_LIMIT_BACKOFF * 1, rc.RATE_LIMIT_BACKOFF * 2]


# ---- timeout pool + saturation guard ----

def test_submit_bounded_fails_fast_when_saturated(monkeypatch):
    monkeypatch.setattr(rc, "_inflight", rc._POOL_WORKERS)
    with pytest.raises(PermanentReasoningError, match="saturated"):
        rc._submit_bounded(lambda: 42)


def test_submit_bounded_releases_slot(monkeypatch):
    monkeypatch.setattr(rc, "_inflight", 0)
    fut = rc._submit_bounded(lambda: 1)
    assert fut.result(timeout=5) == 1
    # give the done-callback a moment
    import time as _t

    for _ in range(50):
        if rc._inflight == 0:
            break
        _t.sleep(0.01)
    assert rc._inflight == 0


def test_with_timeout_raises_on_overrun():
    import time as _t

    with pytest.raises(ReasoningError, match="timed out"):
        rc._with_timeout(lambda: _t.sleep(5), 0.1, "slow op")


# ---- kill switch + tier routing ----

def test_kill_switch_disables_reasoning(monkeypatch):
    monkeypatch.setenv("ASSAY_DISABLE_REASONING", "1")
    with pytest.raises(ReasoningError, match="disabled"):
        rc._attempt(_req())


def test_unknown_tier_is_permanent(monkeypatch):
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)

    class FakeTier:
        pass

    req = ReasoningRequest(prompt="p", tier=StakesTier.BULK, purpose="t")
    object.__setattr__(req, "tier", FakeTier())  # smuggle an unknown tier
    with pytest.raises(PermanentReasoningError, match="unknown tier"):
        rc._attempt(req)


# ---- loopback enforcement (ADR-0003) ----

def test_require_loopback_accepts_local():
    require_loopback_url("http://127.0.0.1:11434", what="x")
    require_loopback_url("http://localhost:11434", what="x")


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.50:11434",
        "http://127.0.0.1.evil.com:11434",  # spoof: starts with 127. but is a public name
        "http://127.attacker.net/",
        "http://0.0.0.0:11434",             # not a loopback bind for egress
        "http://example.com/",
    ],
)
def test_require_loopback_rejects_non_loopback(url):
    with pytest.raises(NonLocalEndpointError):
        require_loopback_url(url, what="x")


def test_require_loopback_accepts_ipv6_loopback():
    require_loopback_url("http://[::1]:11434", what="x")


def test_bulk_tier_rejects_non_loopback_base_url(monkeypatch):
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    monkeypatch.setattr(rc, "BULK_BASE_URL", "http://10.0.0.5:11434")
    with pytest.raises(NonLocalEndpointError):
        rc._bulk_complete("p", None, 0.0, "m")


# ---- public seam ----

def test_seam_run_delegates(monkeypatch):
    monkeypatch.setattr(rc, "_attempt", lambda _req: "answer")
    assert TieredReasoningSeam().run(_req()) == "answer"


def test_seam_run_json(monkeypatch):
    monkeypatch.setattr(rc, "_attempt", lambda _req: 'reply: {"k": 5}')
    assert TieredReasoningSeam().run_json(_req()) == {"k": 5}


def test_is_available_false_when_disabled(monkeypatch):
    monkeypatch.setenv("ASSAY_DISABLE_REASONING", "1")
    assert TieredReasoningSeam.is_available(StakesTier.BULK) is False
    assert TieredReasoningSeam.is_available(StakesTier.HIGH_STAKES) is False


def test_run_json_recovers_after_bad_then_good(monkeypatch):
    # issue #R6: parse failure must regenerate (with varied temperature), not give up.
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    seen_temps: list[float] = []

    def attempt(req):
        seen_temps.append(float(req.params.get("temperature", -1)))
        return "garbled, not json" if len(seen_temps) == 1 else '{"ok": 1}'

    monkeypatch.setattr(rc, "_attempt", attempt)
    assert TieredReasoningSeam().run_json(_req()) == {"ok": 1}
    assert len(seen_temps) >= 2 and seen_temps[0] != seen_temps[1]  # temperature varied


def test_run_json_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    monkeypatch.setattr(rc, "_attempt", lambda req: "never json")
    with pytest.raises(ReasoningError):
        TieredReasoningSeam().run_json(_req())


def test_run_json_requests_json_mode_and_system(monkeypatch):
    captured = {}

    def attempt(req):
        captured["params"] = dict(req.params)
        return '{"k": 1}'

    monkeypatch.setattr(rc, "_attempt", attempt)
    TieredReasoningSeam().run_json(_req(system="be terse"))
    assert captured["params"]["_json_mode"] is True
    assert "JSON" in captured["params"]["system"]


def test_run_emits_no_error_without_otel(monkeypatch):
    # issue #R3: tracing is a no-op when opentelemetry is absent (it is, in this env)
    monkeypatch.setattr(rc, "_attempt", lambda _req: "ok")
    assert TieredReasoningSeam().run(_req()) == "ok"


def test_unconfigured_seam_raises():
    from assay_engine.reasoning.seam import UnconfiguredReasoningSeam

    with pytest.raises(NotImplementedError):
        UnconfiguredReasoningSeam().run(_req())
