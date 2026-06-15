"""Infra stubs fail loud, and FeatureMatrix validates its shape (audit pass 1: #14, #17)."""

import pytest

from assay_engine.methodology.fence import Interpretation, Measurement
from assay_engine.contracts.features import FeatureMatrix
from assay_engine.observability.tracing import UnconfiguredTracer
from assay_engine.reasoning.seam import (
    ReasoningRequest,
    StakesTier,
    UnconfiguredReasoningSeam,
)


def test_unconfigured_reasoning_seam_fails_loud():
    seam = UnconfiguredReasoningSeam()
    req = ReasoningRequest(prompt="x", tier=StakesTier.BULK, purpose="t")
    with pytest.raises(NotImplementedError):
        seam.run(req)


def test_unconfigured_tracer_fails_loud_not_silent():
    # issue #14: the placeholder tracer must raise, not silently drop spans
    tracer = UnconfiguredTracer()
    with pytest.raises(NotImplementedError):
        with tracer.span("x"):
            pass


def test_measurement_rejects_interpretation_value():
    # issue #22: interpretation must not feed back into measurement
    interp = Interpretation(value=1, basis=("p:h",), rationale="r", judged_by="op")
    with pytest.raises(TypeError):
        Measurement(value=interp, produced_by="x", inputs_hash="h")


def test_measurement_and_interpretation_with_container_value_are_hashable():
    # issue #29: the value payload is frozen so the frozen record is hashable
    m = Measurement(value=[1, 2, 3], produced_by="p", inputs_hash="h")
    assert hash(m) is not None
    assert m.value == (1, 2, 3)
    i = Interpretation(value={"k": 1}, basis=("p:h",), rationale="r", judged_by="op")
    assert hash(i) is not None


def test_measurement_rejects_nested_interpretation():
    # issue #30: a nested interpretation (in a container or metadata) must also be rejected
    interp = Interpretation(value=1, basis=("p:h",), rationale="r", judged_by="op")
    with pytest.raises(TypeError):
        Measurement(value=[interp], produced_by="x", inputs_hash="h")
    with pytest.raises(TypeError):
        Measurement(value=0.5, produced_by="x", inputs_hash="h", metadata={"leak": interp})


def test_feature_matrix_valid():
    fm = FeatureMatrix(unit_ids=("a", "b"), feature_names=("f1",), rows=((1.0,), (2.0,)))
    assert len(fm.rows) == 2


def test_feature_matrix_rejects_row_count_mismatch():
    with pytest.raises(ValueError):
        FeatureMatrix(unit_ids=("a", "b"), feature_names=("f1",), rows=((1.0,),))


def test_feature_matrix_rejects_width_mismatch():
    with pytest.raises(ValueError):
        FeatureMatrix(unit_ids=("a",), feature_names=("f1", "f2"), rows=((1.0,),))
