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
    is_unsafe_subprocess_var,
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
        ("anthropic_api_key", True),  # #F-003: lowercase must still match
        ("Anthropic_Auth_Token", True),  # #F-003: mixed case must still match
        ("ANTHROPIC_BASE_URL", False),  # not a credential
        ("CLAUDE_CODE_OAUTH_TOKEN", False),  # subscription auth — keep
        ("claude_code_oauth_token", False),  # #F-003: lowercase subscription auth still kept
        ("PATH", False),
    ],
)
def test_is_metered_credential_matches_shape(key, metered):
    assert is_metered_anthropic_credential(key) is metered


@pytest.mark.parametrize(
    "key,unsafe",
    [
        ("ANTHROPIC_API_KEY", True),
        ("ANTHROPIC_AUTH_TOKEN", True),
        ("ANTHROPIC_BASE_URL", True),  # off-box redirect (#101)
        ("ANTHROPIC_BEDROCK_BASE_URL", True),
        ("CLAUDE_CODE_USE_BEDROCK", True),  # metered-provider switch
        ("CLAUDE_CODE_USE_VERTEX", True),
        ("CLAUDE_CODE_API_KEY_HELPER", True),
        ("HTTP_PROXY", True),
        ("https_proxy", True),  # case-insensitive
        ("AWS_SECRET_ACCESS_KEY", True),
        ("GOOGLE_APPLICATION_CREDENTIALS", True),
        ("CLAUDE_CODE_OAUTH_TOKEN", False),  # subscription auth — keep
        ("PATH", False),
        ("HOME", False),
    ],
)
def test_is_unsafe_subprocess_var(key, unsafe):
    assert is_unsafe_subprocess_var(key) is unsafe


def test_scrubbed_env_overwrites_unsafe_and_survives_sdk_merge(monkeypatch):
    # #101: the SDK builds the child env as {**os.environ, **options.env}, so omitting a key
    # leaks the inherited value. scrubbed_env must OVERWRITE unsafe vars to "" so the merge wins.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-metered-REMOVE")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://attacker.example")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://attacker.example")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "keep")
    scrubbed = scrubbed_env()
    # simulate the claude-agent-sdk merge over the inherited environment
    import os as _os

    child = {**_os.environ, **scrubbed}
    for k in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "HTTPS_PROXY",
        "AWS_SECRET_ACCESS_KEY",
    ):
        assert child[k] == "", f"{k} leaked into the child env: {child[k]!r}"
    assert child["CLAUDE_CODE_OAUTH_TOKEN"] == "keep"  # subscription auth preserved


# ---- JSON extraction / balanced-brace walker ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
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


def test_deadline_gates_retry_entry_not_just_backoff(monkeypatch):
    # #F-022: once the overall deadline has passed, NO further _attempt is started — the deadline
    # bounds retry ENTRY, not only the backoff sleeps. Discriminating: neutralize the backoff gate
    # (_sleep_bounded → no-op) so the ONLY thing that can stop the retry loop is the entry gate,
    # and feed a deadline already in the past. With the entry gate the loop runs exactly ONE
    # attempt then raises "before retry"; without it, it would run all MAX_RETRIES+1 attempts.
    monkeypatch.setattr(rc, "_sleep_bounded", lambda *_a, **_k: None)
    calls = {"n": 0}

    def always(_req):
        calls["n"] += 1
        raise ReasoningError("transient")

    monkeypatch.setattr(rc, "_attempt", always)
    past_deadline = rc.time.monotonic() - 1.0  # already elapsed
    with pytest.raises(ReasoningError, match="deadline exceeded before retry"):
        rc._run_with_retries(_req(), deadline=past_deadline)
    assert calls["n"] == 1  # exactly one attempt ran; no retry was started past the deadline


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


def test_submit_bounded_saturation_is_retryable_backpressure(monkeypatch):
    # #104: saturation is transient — must be a retryable RateLimitError (backpressure), not a
    # permanent failure that drops the caller with no retry.
    monkeypatch.setattr(rc, "_inflight", rc._POOL_WORKERS)
    with pytest.raises(RateLimitError, match="saturated"):
        rc._submit_bounded(lambda: 42)


def test_submit_bounded_normalizes_pool_shutdown(monkeypatch):
    # #116: a RuntimeError from a shut-down pool must surface as the documented seam error type,
    # not leak the raw RuntimeError.
    monkeypatch.setattr(rc, "_inflight", 0)

    class DeadPool:
        def submit(self, fn):
            raise RuntimeError("cannot schedule new futures after shutdown")

    monkeypatch.setattr(rc, "_pool", DeadPool())
    with pytest.raises(PermanentReasoningError, match="shut down"):
        rc._submit_bounded(lambda: 1)
    assert rc._inflight == 0  # slot reservation rolled back


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


def test_pool_saturation_and_release_under_real_threads(monkeypatch):
    # genuine concurrency: fill every worker slot with real blocking tasks, confirm the next
    # submit fails fast (saturation guard), then confirm slots are released after completion.
    import threading
    import time as _t

    monkeypatch.setattr(rc, "_inflight", 0)
    gate = threading.Event()
    futures = [rc._submit_bounded(lambda: gate.wait(5)) for _ in range(rc._POOL_WORKERS)]
    with pytest.raises(RateLimitError, match="saturated"):  # retryable backpressure (#104)
        rc._submit_bounded(lambda: 1)
    gate.set()
    for f in futures:
        f.result(timeout=5)
    for _ in range(200):  # allow done-callbacks to release slots
        if rc._inflight == 0:
            break
        _t.sleep(0.01)
    assert rc._inflight == 0


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
        "http://0.0.0.0:11434",  # not a loopback bind for egress
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


def _fake_ollama(monkeypatch, captured):
    """Inject a fake langchain_ollama whose ChatOllama records its constructor kwargs."""
    import sys
    import types

    class FakeClient:
        def __init__(self, **kwargs):
            captured.append(kwargs)

        def invoke(self, messages):
            return type("R", (), {"content": '{"ok": 1}'})()

    mod = types.SimpleNamespace(ChatOllama=FakeClient)
    monkeypatch.setitem(sys.modules, "langchain_ollama", mod)


def test_bulk_complete_bounds_generation_and_passes_seed_and_schema(monkeypatch):
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    captured: list[dict] = []
    _fake_ollama(monkeypatch, captured)
    schema = {"type": "object", "properties": {"ok": {"type": "integer"}}}
    rc._bulk_complete("p", None, 0.0, "m", seed=3, json_schema=schema)
    kw = captured[0]
    assert kw["num_predict"] == rc.BULK_NUM_PREDICT  # generation is bounded (H1)
    assert kw["seed"] == 3  # seed threaded for deterministic re-rolls (M3)
    assert kw["format"] == schema  # schema-constrained JSON decoding (M2), not loose "json"


def test_bulk_complete_sets_a_total_bounded_http_timeout(monkeypatch):
    # #G-003: BULK's inner bound is the HTTP client timeout (sync-tier counterpart to HIGH_STAKES's
    # anyio.fail_after). A bare float sets every httpx phase to BULK_TIMEOUT (connect+read can total
    # ~2x, past the outer BULK_TIMEOUT+10 bound, leaking the worker slot). Assert an explicit
    # httpx.Timeout whose read==BULK_TIMEOUT and connect is small, so the TOTAL stays ~BULK_TIMEOUT.
    import httpx

    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    captured: list[dict] = []
    _fake_ollama(monkeypatch, captured)
    rc._bulk_complete("p", None, 0.0, "m")
    timeout = captured[0]["client_kwargs"]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == rc.BULK_TIMEOUT
    assert timeout.connect is not None and timeout.connect <= 10.0
    # total worst case (connect + read) must not exceed the outer _with_timeout headroom
    assert timeout.connect + timeout.read <= rc.BULK_TIMEOUT + 10


def test_bulk_complete_classifies_404_as_permanent_by_status(monkeypatch):
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    import sys
    import types

    class Err(Exception):
        status_code = 404  # typed status, NOT a recognizable substring

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def invoke(self, messages):
            raise Err("model gremlin not present")

    monkeypatch.setitem(
        sys.modules, "langchain_ollama", types.SimpleNamespace(ChatOllama=FakeClient)
    )
    with pytest.raises(rc.PermanentReasoningError):
        rc._bulk_complete("p", None, 0.0, "gremlin")


def test_run_json_varies_seed_and_never_lowers_temperature(monkeypatch):
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    monkeypatch.setattr(rc, "JSON_REROLLS", 2)
    seen: list[tuple] = []

    # the generation SUCCEEDS but returns unparseable text → run_json re-rolls (parse failure)
    def fake_run_with_retries(req, *, deadline=None):
        seen.append((req.params.get("_seed"), req.params["temperature"]))
        return "not json at all"  # parse failure forces a re-roll

    monkeypatch.setattr(rc, "_run_with_retries", fake_run_with_retries)
    with pytest.raises(rc.ReasoningError):
        TieredReasoningSeam().run_json(_req())
    seeds = [s for s, _ in seen]
    temps = [t for _, t in seen]
    assert seeds == [0, 1, 2]  # each re-roll forces a different deterministic decode
    assert temps == sorted(temps) and max(temps) <= 1.0  # monotonic non-decreasing, capped


def test_run_json_overall_deadline_bounds_rerolls(monkeypatch):
    # #102: an overall deadline must cap the re-roll loop so retries can't multiply unboundedly
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    monkeypatch.setattr(rc, "JSON_REROLLS", 50)
    monkeypatch.setattr(rc, "RUN_JSON_DEADLINE", 0.0)  # deadline already passed after attempt 0
    calls = {"n": 0}

    def bad_text(_req, *, deadline=None):
        calls["n"] += 1
        return "not json"  # parse failure would re-roll, but the deadline must stop it

    monkeypatch.setattr(rc, "_run_with_retries", bad_text)
    with pytest.raises(rc.ReasoningError):
        TieredReasoningSeam().run_json(_req())
    assert calls["n"] == 1  # stopped at the deadline, did NOT run all 51 re-rolls


def test_run_json_does_not_reroll_on_reasoning_error_no_multiplication(monkeypatch):
    # #102: a transient/exhausted reasoning error must PROPAGATE (no outer re-roll), so the inner
    # retry budget and the re-roll budget never multiply. _attempt is called only MAX_RETRIES+1
    # times total, NOT (MAX_RETRIES+1) * (JSON_REROLLS+1).
    monkeypatch.delenv("ASSAY_DISABLE_REASONING", raising=False)
    monkeypatch.setattr(rc.time, "sleep", lambda *_: None)
    monkeypatch.setattr(rc, "MAX_RETRIES", 2)
    monkeypatch.setattr(rc, "JSON_REROLLS", 5)
    calls = {"n": 0}

    def always_transient(_req):
        calls["n"] += 1
        raise rc.ReasoningError("transient")

    monkeypatch.setattr(rc, "_attempt", always_transient)
    with pytest.raises(rc.ReasoningError):
        TieredReasoningSeam().run_json(_req())
    assert calls["n"] == rc.MAX_RETRIES + 1  # 3, not 3*6 — budgets did not multiply


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
