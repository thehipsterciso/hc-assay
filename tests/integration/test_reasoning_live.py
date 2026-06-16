"""Live reasoning seam — real Ollama (bulk) and a guarded real frontier (high-stakes) call."""

from __future__ import annotations

import os

import pytest

from tests.integration.conftest import have, ollama_up

pytestmark = pytest.mark.skipif(
    not have("langchain_ollama"), reason="reasoning extra not installed"
)

from assay_engine.reasoning.seam import (  # noqa: E402
    ReasoningRequest,
    StakesTier,
    TieredReasoningSeam,
)

_BULK_MODEL = os.environ.get("ASSAY_BULK_MODEL", "llama3.1:8b")


@pytest.mark.skipif(not ollama_up(), reason="ollama not running")
def test_bulk_tier_real_call_returns_text(require_ollama):
    seam = TieredReasoningSeam()
    assert TieredReasoningSeam.is_available(StakesTier.BULK) is True
    out = seam.run(
        ReasoningRequest(
            prompt="Reply with exactly the single word: pong",
            tier=StakesTier.BULK,
            purpose="integration-smoke",
            params={"model": _BULK_MODEL, "temperature": 0.0},
        )
    )
    assert isinstance(out, str) and out.strip()  # a real, non-empty model reply


@pytest.mark.skipif(not ollama_up(), reason="ollama not running")
def test_bulk_tier_run_json_parses_real_reply(require_ollama):
    seam = TieredReasoningSeam()
    result = seam.run_json(
        ReasoningRequest(
            prompt='Return a JSON object with a single key "ok" set to the boolean true.',
            tier=StakesTier.BULK,
            purpose="integration-json",
            params={"model": _BULK_MODEL},
        )
    )
    assert isinstance(result, (dict, list))  # extracted + parsed from a real model reply


@pytest.mark.skipif(not ollama_up(), reason="ollama not running")
def test_bulk_tier_missing_model_is_permanent(require_ollama):
    # a real ollama "model not found" error must map to PermanentReasoningError (not retried).
    from assay_engine.reasoning.seam import PermanentReasoningError

    seam = TieredReasoningSeam()
    with pytest.raises(PermanentReasoningError):
        seam.run(
            ReasoningRequest(
                prompt="hi",
                tier=StakesTier.BULK,
                purpose="missing-model",
                params={"model": "definitely-not-a-real-model:0b"},
            )
        )


def test_high_stakes_availability_probe():
    # cheap liveness probe (spends no LLM turn) — exercises the real shutil/env path
    avail = TieredReasoningSeam.is_available(StakesTier.HIGH_STAKES)
    assert isinstance(avail, bool)


@pytest.mark.skipif(
    os.environ.get("ASSAY_RUN_HIGH_STAKES_TESTS") != "1",
    reason="set ASSAY_RUN_HIGH_STAKES_TESTS=1 to make a real (metered-subscription) frontier call",
)
def test_high_stakes_real_call():
    seam = TieredReasoningSeam()
    if not TieredReasoningSeam.is_available(StakesTier.HIGH_STAKES):
        pytest.skip("high-stakes tier not available (no claude CLI / subscription auth)")
    out = seam.run(
        ReasoningRequest(
            prompt="Reply with exactly the single word: pong",
            tier=StakesTier.HIGH_STAKES,
            purpose="integration-smoke-t3",
        )
    )
    assert isinstance(out, str) and out.strip()
