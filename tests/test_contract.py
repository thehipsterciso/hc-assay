"""The engine ↔ adapter contract: canonical schema, study validation, registry, fence.

The decisive architectural test (``test_engine_imports_no_adapter``) asserts the rule the
whole blueprint exists to keep: the engine package imports no dataset/adapter module.
"""

import pkgutil

import pytest

import assay_engine
from assay_engine.contracts.schema import Corpus, Relation, Unit
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


def test_corpus_accepts_relations_between_known_units():
    Corpus(units=(Unit("a"), Unit("b")), relations=(Relation("a", "b", "parent"),))


def test_corpus_rejects_relation_to_unknown_unit():
    # issue #3: a closed corpus must not reference non-existent units
    with pytest.raises(ValueError):
        Corpus(units=(Unit("a"),), relations=(Relation("a", "ghost", "parent"),))


def test_study_rejects_empty_name():
    # issue #8: name is the registry key / pre-registration anchor
    with pytest.raises(ValueError):
        StudyDefinition.discovery("  ", _StubParser(), ["q"])


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
    # issue #16: basis identifies the specific measurement (producer:inputs_hash), not just
    # the producer, so two measurements from one producer are distinguishable.
    assert interp.basis == ("similarity:abc",)
    other = Measurement(value=0.1, produced_by="similarity", inputs_hash="xyz")
    assert fence(other, "far", rationale="r", judged_by="operator").basis != interp.basis
    # there is deliberately no inverse: Interpretation cannot become a Measurement
    assert not hasattr(interp, "as_measurement")


def test_measurement_rejects_interpretation_smuggled_as_dict_key():
    # #115: the fence must scan dict KEYS, not just values — an Interpretation used as a key
    # would otherwise be smuggled back into a Measurement.
    interp = Interpretation(value="judged", basis=(), rationale="r", judged_by="op")
    with pytest.raises(TypeError):
        Measurement(value={interp: 1}, produced_by="p", inputs_hash="h")
    with pytest.raises(TypeError):
        Measurement(value=[{("nested", interp): 2}], produced_by="p", inputs_hash="h")


def test_verdict_rejects_non_enum_label():
    # #133: a study-supplied confirmer returning a bare-string label must fail fast and
    # attributable at construction, not as an opaque KeyError during scoring.
    from assay_engine.methodology.verdict import Verdict, VerdictLabel

    with pytest.raises(TypeError, match="VerdictLabel"):
        Verdict("h1", label="supported", decision_rule="rule")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="hypothesis_id"):
        Verdict("", label=VerdictLabel.SUPPORTED, decision_rule="rule")
    # a correct verdict still constructs
    assert Verdict("h1", VerdictLabel.SUPPORTED, "rule").label is VerdictLabel.SUPPORTED


def test_study_definition_coerces_modes_to_frozenset():
    # #135: the raw constructor must coerce a plain set so the frozen record stays hashable.
    d = StudyDefinition(
        name="s",
        modes={StudyMode.DISCOVERY},  # type: ignore[arg-type]
        parser=_StubParser(),
        research_questions=("q",),
    )
    assert isinstance(d.modes, frozenset)
    assert isinstance(hash(d), int)  # would raise TypeError pre-fix (unhashable set)
    with pytest.raises(TypeError, match="StudyMode"):
        StudyDefinition(
            name="s",
            modes=frozenset({"discovery"}),  # type: ignore[arg-type]
            parser=_StubParser(),
            research_questions=("q",),
        )


def test_discover_confirm_split_coerces_and_stays_immutable():
    # #135: the raw constructor must coerce mutable sets so the disjointness invariant can't be
    # defeated by post-construction in-place mutation.
    from assay_engine.methodology.firewalls import DiscoverConfirmSplit

    s = DiscoverConfirmSplit(discovery_ids={"a"}, confirm_ids={"b"})  # type: ignore[arg-type]
    assert isinstance(s.discovery_ids, frozenset) and isinstance(s.confirm_ids, frozenset)
    with pytest.raises(AttributeError):
        s.confirm_ids.add("a")  # type: ignore[attr-defined]  # frozenset has no .add


def test_feature_matrix_rejects_non_numeric_and_non_finite_rows():
    # #149: a misimplemented builder returning a non-numeric / non-finite cell must fail at
    # construction, not flow into baseline math as an opaque downstream error.
    from assay_engine.contracts.features import FeatureMatrix

    with pytest.raises(TypeError):
        FeatureMatrix(unit_ids=("a",), feature_names=("f",), rows=(("x",),))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        FeatureMatrix(unit_ids=("a",), feature_names=("f",), rows=((True,),))  # bool excluded
    with pytest.raises(ValueError):
        FeatureMatrix(unit_ids=("a",), feature_names=("f",), rows=((float("nan"),),))
    # a valid numeric matrix still constructs
    FeatureMatrix(unit_ids=("a",), feature_names=("f",), rows=((1.0,),))


def test_no_seam_protocol_is_runtime_checkable():
    # #148: consistent policy — adapter/seam validation is behavior-based, so no Protocol is
    # @runtime_checkable (which would give false-confidence name-only isinstance checks).
    import inspect

    from assay_engine.observability import tracing, tracking
    from assay_engine.persistence import vectorstore, versioning
    from assay_engine.reasoning import seam

    for mod in (tracing, tracking, vectorstore, versioning, seam):
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if getattr(obj, "_is_runtime_protocol", False):
                raise AssertionError(f"{mod.__name__}.{obj.__name__} is still runtime_checkable")


def test_measurement_rejects_interpretation_in_duck_typed_mapping():
    # #140: a dict-like that is NOT a collections.abc.Mapping (exposes keys()+__getitem__ only)
    # must still be scanned by the fence AND deep-frozen — otherwise an Interpretation hidden in
    # it slips into a Measurement and the "frozen" value stays a live mutable object.
    from assay_engine._frozen import FrozenDict, freeze

    class DuckMap:
        def __init__(self, d):
            self._d = dict(d)

        def keys(self):
            return self._d.keys()

        def __getitem__(self, k):
            return self._d[k]

    interp = Interpretation(value="judged", basis=(), rationale="r", judged_by="op")
    with pytest.raises(TypeError):
        Measurement(value=DuckMap({"k": interp}), produced_by="p", inputs_hash="h")
    # freeze() must convert a duck-mapping to a FrozenDict, not pass it through as a live leaf
    frozen = freeze(DuckMap({"a": 1}))
    assert isinstance(frozen, FrozenDict) and frozen["a"] == 1


def test_engine_imports_no_adapter():
    """The engine must be self-contained: every submodule imports without an adapter present."""
    failures = []
    for mod in pkgutil.walk_packages(assay_engine.__path__, prefix="assay_engine."):
        try:
            __import__(mod.name)
        except Exception as exc:  # noqa: BLE001
            failures.append((mod.name, repr(exc)))
    assert not failures, f"engine submodules failed to import standalone: {failures}"
