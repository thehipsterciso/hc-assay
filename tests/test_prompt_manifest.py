"""Tests for PromptManifest (#178) and drift detection (#179)."""

from __future__ import annotations

import warnings

import pytest

from assay_engine.baseline.determinism import (
    BaselineDriftReport,
    BaselineDriftWarning,
    diff_baseline_fingerprints,
)
from assay_engine.contracts.prompts import PromptManifest, prompt_manifest
from assay_engine.pipeline import StudyPlan, auto_approve, run_study
from tests import reference_study as ref

DISCOVERY = frozenset({"discovery"})


# ---- PromptManifest ----


def test_prompt_manifest_stores_entries():
    m = prompt_manifest(discover="v1.2", confirm_held_out="v1.0")
    assert m["discover"] == "v1.2"
    assert m["confirm_held_out"] == "v1.0"


def test_prompt_manifest_is_immutable():
    m = prompt_manifest(discover="v1.0")
    with pytest.raises(TypeError):
        m["discover"] = "v2.0"  # type: ignore[index]
    with pytest.raises(TypeError):
        del m["discover"]  # type: ignore[misc]
    with pytest.raises(TypeError):
        m.clear()
    with pytest.raises(TypeError):
        m.pop("discover")  # type: ignore[misc]
    with pytest.raises(TypeError):
        m.update({"discover": "v2.0"})


def test_prompt_manifest_repr():
    m = prompt_manifest(discover="v1.0")
    assert "PromptManifest" in repr(m)


def test_prompt_manifest_from_mapping():
    m = PromptManifest({"discover": "v1.0", "confirm": "v2.0"})
    assert len(m) == 2


# ---- run_study logs prompt_manifest to trail ----


def test_run_study_logs_prompt_manifest_to_provenance(tmp_path):
    from assay_engine.contracts.study import StudyMode

    src = ref.write_source(tmp_path / "corpus.json")
    manifest = prompt_manifest(discover="v1.0", confirm_held_out="v1.0")
    plan = ref.make_plan(src, modes=frozenset({StudyMode.DISCOVERY}))
    # Attach manifest via dataclasses replace
    from dataclasses import replace

    plan_with_manifest = replace(plan, prompt_manifest=manifest)

    result = run_study(plan_with_manifest, gate_handler=auto_approve)

    events = [e.kind for e in result.provenance]
    assert "prompt_manifest" in events

    manifest_entry = next(e for e in result.provenance if e.kind == "prompt_manifest")
    assert manifest_entry.payload["callables"]["discover"] == "v1.0"


def test_run_study_without_manifest_has_no_manifest_entry(tmp_path):
    from assay_engine.contracts.study import StudyMode

    src = ref.write_source(tmp_path / "corpus.json")
    plan = ref.make_plan(src, modes=frozenset({StudyMode.DISCOVERY}))

    result = run_study(plan, gate_handler=auto_approve)

    events = [e.kind for e in result.provenance]
    assert "prompt_manifest" not in events


# ---- baseline drift detection ----


def test_no_drift_when_fingerprints_match():
    fp = "a" * 64
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = diff_baseline_fingerprints(fp, fp)
    assert not report.drifted
    assert not any(issubclass(w.category, BaselineDriftWarning) for w in caught)


def test_drift_detected_and_warning_emitted():
    old = "a" * 64
    new = "b" * 64
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = diff_baseline_fingerprints(old, new)
    assert report.drifted
    assert any(issubclass(w.category, BaselineDriftWarning) for w in caught)


def test_drift_warn_suppressed():
    old = "a" * 64
    new = "b" * 64
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = diff_baseline_fingerprints(old, new, warn=False)
    assert report.drifted
    assert not any(issubclass(w.category, BaselineDriftWarning) for w in caught)


def test_drift_report_unit_delta():
    report = BaselineDriftReport(
        prior_fingerprint="a" * 64,
        current_fingerprint="b" * 64,
        drifted=True,
        prior_n_units=100,
        current_n_units=110,
    )
    assert report.unit_delta == 10


def test_drift_report_unit_delta_none_when_missing():
    report = BaselineDriftReport(
        prior_fingerprint="a" * 64,
        current_fingerprint="b" * 64,
        drifted=True,
    )
    assert report.unit_delta is None


def test_drift_report_as_params_keys():
    old = "a" * 64
    new = "b" * 64
    report = diff_baseline_fingerprints(old, new, prior_n_units=5, current_n_units=6, warn=False)
    params = report.as_params()
    assert "drift.prior_fingerprint" in params
    assert "drift.current_fingerprint" in params
    assert "drift.detected" in params
    assert "drift.unit_delta" in params
    assert params["drift.unit_delta"] == "1"


# ---- run_study passes prior_corpus_fingerprint through ----


def test_run_study_records_drift_when_fingerprint_differs(tmp_path):
    from assay_engine.contracts.study import StudyMode

    src = ref.write_source(tmp_path / "corpus.json")
    plan = ref.make_plan(src, modes=frozenset({StudyMode.DISCOVERY}))

    fake_prior = "0" * 64  # guaranteed to differ from real fingerprint
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_study(plan, gate_handler=auto_approve, prior_corpus_fingerprint=fake_prior)

    events = [e.kind for e in result.provenance]
    assert "baseline_drift" in events
    assert any(issubclass(w.category, BaselineDriftWarning) for w in caught)


def test_run_study_no_drift_entry_without_prior_fingerprint(tmp_path):
    from assay_engine.contracts.study import StudyMode

    src = ref.write_source(tmp_path / "corpus.json")
    plan = ref.make_plan(src, modes=frozenset({StudyMode.DISCOVERY}))

    result = run_study(plan, gate_handler=auto_approve)

    events = [e.kind for e in result.provenance]
    assert "baseline_drift" not in events
