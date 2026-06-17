"""A synthetic, dataset-agnostic reference adapter for exercising the study runner.

This is NOT a dataset — it is a minimal, deterministic double that implements every adapter
Protocol so the engine's composed pipeline can be run end-to-end (both modes) without any real
corpus. It is the runnable demonstration of "the workflow", and the fixture the pipeline tests
and the live integration test drive.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Iterable

from assay_engine.baseline.determinism import build_baseline_artifact
from assay_engine.baseline.toolkit import BaselineArtifact
from assay_engine.contracts.claims import ClaimRecord, claim_set_fingerprint
from assay_engine.contracts.schema import Corpus, Unit
from assay_engine.contracts.study import StudyDefinition, StudyMode
from assay_engine.methodology.firewalls import ClaimBlindGuard, DiscoverConfirmSplit
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import LocalHmacAuthority, lock_hypothesis
from assay_engine.methodology.verdict import Verdict
from assay_engine.pipeline import StudyPlan

AUTHORITY = LocalHmacAuthority(b"reference-study-secret-key-000001")
_PAST = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(hours=1)


def write_source(path: Path, n_units: int = 6) -> Path:
    """Write a tiny JSON corpus source the ReferenceParser can ingest deterministically."""
    units = [{"id": f"u{i}", "text": f"control text number {i}"} for i in range(n_units)]
    path.write_text(json.dumps({"units": units}), encoding="utf-8")
    return path


class ReferenceParser:
    def parse(self, source: Path) -> Corpus:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        return Corpus(units=tuple(Unit(u["id"], u["text"]) for u in data["units"]))

    def source_fingerprint(self, source: Path) -> str:
        return hashlib.sha256(Path(source).read_bytes()).hexdigest()


class ReferenceBaselineBuilder:
    """Blind baseline: a deterministic summary stat over the corpus text only."""

    def build(self, corpus: Corpus, *, claim_guard: ClaimBlindGuard[object]) -> BaselineArtifact:
        mean_len = sum(len(u.text) for u in corpus.units) / max(1, len(corpus.units))
        return build_baseline_artifact(
            corpus,
            {"mean_text_len": mean_len, "n_units": len(corpus.units)},
            component_versions={"builder": "reference@1"},
        )


class ReferenceClaims:
    def __init__(self, claim_ids: tuple[str, ...] = ("c1", "c2")) -> None:
        self._ids = claim_ids

    def claims(self) -> Iterable[ClaimRecord]:
        return [
            ClaimRecord(claim_id=c, subject=c, referents=(c,), assertion={"expected": "high"})
            for c in self._ids
        ]

    def claim_fingerprint(self) -> str:
        # The engine enforces that this equals its canonical recomputation over claims() (#F-001),
        # so commit to the same content the engine will score, via the public helper.
        return claim_set_fingerprint(self.claims())


def discover(discovery_corpus: Corpus) -> list[Hypothesis]:
    """Data-surface one whole-corpus hypothesis, locked (pre-registered) in the past."""
    h = Hypothesis(
        hypothesis_id="H-disc-1",
        statement="discovery-partition units share above-chance internal similarity",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="permutation",
        decision_rule="empirical p<=0.05 in the 'greater' tail",
        predicted_direction="greater",
    )
    return [lock_hypothesis(h, authority=AUTHORITY, instant=_PAST)]


def confirm_held_out(hypothesis: Hypothesis, held_out: Corpus) -> Verdict:
    # a study computes its real statistic on held_out; here a deterministic stand-in verdict
    assert held_out.units, "confirm must receive a non-empty held-out partition"
    return Verdict.supported(hypothesis.hypothesis_id, "held-out test passed (reference)")


def hypothesis_for(claim: ClaimRecord) -> Hypothesis:
    """Map a claim to its pre-stated, locked EXTERNAL_CLAIM hypothesis (locked pre-baseline)."""
    h = Hypothesis(
        hypothesis_id=f"H-{claim.claim_id}",
        statement="claim holds against the blind baseline",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.EXTERNAL_CLAIM,
        test_name="adjudication",
        decision_rule="baseline corroborates the asserted relationship",
        source_claim_id=claim.claim_id,
        predicted_direction="greater",
    )
    return lock_hypothesis(h, authority=AUTHORITY, instant=_PAST)


def confirm_claim(
    hypothesis: Hypothesis, baseline: BaselineArtifact, claim: ClaimRecord
) -> Verdict:
    assert "mean_text_len" in baseline.contents  # the real baseline is passed through
    return Verdict.supported(hypothesis.hypothesis_id, "baseline corroborates (reference)")


def make_plan(source: Path, *, modes: frozenset[StudyMode]) -> StudyPlan:
    """Assemble a StudyPlan over the reference adapter for the requested modes."""
    adjudicate = StudyMode.ADJUDICATE_EXTERNAL_CLAIMS in modes
    discovery = StudyMode.DISCOVERY in modes
    definition = StudyDefinition(
        name="reference-study",
        modes=modes,
        parser=ReferenceParser(),
        research_questions=("does the reference pipeline run end-to-end?",),
        claims_source=ReferenceClaims() if adjudicate else None,
    )
    split = (
        DiscoverConfirmSplit.from_partition({"u0", "u1", "u2"}, {"u3", "u4", "u5"})
        if discovery
        else None
    )
    return StudyPlan(
        definition=definition,
        source=source,
        baseline_builder=ReferenceBaselineBuilder(),
        authority=AUTHORITY,
        split=split,
        discover=discover if discovery else None,
        confirm_held_out=confirm_held_out if discovery else None,
        hypothesis_for=hypothesis_for if adjudicate else None,
        confirm_claim=confirm_claim if adjudicate else None,
    )
