"""The engine ↔ adapter contract: canonical schema, study validation, registry, fence.

The decisive architectural test (``test_engine_imports_no_adapter``) asserts the rule the
whole blueprint exists to keep: the engine package imports no dataset/adapter module.
"""

import pkgutil

import pytest

import assay_engine
from assay_engine.contracts.schema import Corpus, Unit
from assay_engine.contracts.study import StudyDefinition, StudyMode
from assay_engine.methodology.fence import Interpretation, Measurement, fence
from assay_engine.registry import (
    clear_registry,
    get_study,
    register_study,
    registered_studies,
)


class _StubParser:
    def parse(self, source):  # pragma: no cover - not exercised here
        return Corpus(units=())

    def source_fingerprint(self, source):  # pragma: no cover
        return "stub"


def test_corpus_rejects_duplicate_unit_ids():
    with pytest.raises(ValueError):
        Corpus(units=(Unit("a"), Unit("a")))


def test_corpus_unit_ids():
    c = Corpus(units=(Unit("a"), Unit("b")))
    assert c.unit_ids() == frozenset({"a", "b"})


def test_discovery_study_must_not_carry_claims_source():
    with pytest.raises(ValueError):
        StudyDefinition(
            name="s",
            modes=frozenset({StudyMode.DISCOVERY}),
            parser=_StubParser(),
            research_questions=("q",),
            claims_source=object(),  # type: ignore[arg-type]
        )


def test_adjudication_study_requires_claims_source():
    with pytest.raises(ValueError):
        StudyDefinition(
            name="s",
            modes=frozenset({StudyMode.ADJUDICATE_EXTERNAL_CLAIMS}),
            parser=_StubParser(),
            research_questions=("q",),
            claims_source=None,
        )


def test_discovery_factory_builds_valid_study():
    study = StudyDefinition.discovery("s", _StubParser(), ["q1", "q2"])
    assert study.modes == frozenset({StudyMode.DISCOVERY})
    assert study.claims_source is None


def test_registry_roundtrip_and_duplicate_guard():
    clear_registry()
    register_study("demo", lambda: StudyDefinition.discovery("demo", _StubParser(), ["q"]))
    assert "demo" in registered_studies()
    assert get_study("demo").name == "demo"
    with pytest.raises(ValueError):
        register_study("demo", lambda: StudyDefinition.discovery("demo", _StubParser(), ["q"]))
    clear_registry()


def test_fence_is_one_directional():
    m = Measurement(value=0.9, produced_by="similarity", inputs_hash="abc")
    interp = fence(m, "units are close", rationale="cosine 0.9", judged_by="operator")
    assert isinstance(interp, Interpretation)
    assert interp.basis == ("similarity",)
    # there is deliberately no inverse: Interpretation cannot become a Measurement
    assert not hasattr(interp, "as_measurement")


def test_engine_imports_no_adapter():
    """The engine must be self-contained: every submodule imports without an adapter present."""
    failures = []
    for mod in pkgutil.walk_packages(assay_engine.__path__, prefix="assay_engine."):
        try:
            __import__(mod.name)
        except Exception as exc:  # noqa: BLE001
            failures.append((mod.name, repr(exc)))
    assert not failures, f"engine submodules failed to import standalone: {failures}"
