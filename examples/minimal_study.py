"""A minimal, runnable hc-assay study — `python examples/minimal_study.py`.

A study is: implement the adapter Protocols for your dataset, assemble a StudyPlan, and call
run_study. This example uses a tiny synthetic in-memory corpus so it runs with the
dependency-free core install (`pip install assay-engine`) — no backends, no real dataset.

It runs BOTH modes:
  - DISCOVERY: surface a hypothesis on one partition, confirm it on a held-out partition.
  - ADJUDICATE: test an external claim against the blind baseline.
"""

from __future__ import annotations

import datetime as _dt
import tempfile
from pathlib import Path

from assay_engine import (
    ClaimRecord,
    Corpus,
    StudyDefinition,
    StudyMode,
    StudyPlan,
    Unit,
    auto_approve,
    run_study,
)
from assay_engine.baseline.determinism import build_baseline_artifact
from assay_engine.baseline.toolkit import BaselineArtifact
from assay_engine.methodology.firewalls import ClaimBlindGuard, DiscoverConfirmSplit
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import LocalHmacAuthority, lock_hypothesis
from assay_engine.methodology.verdict import Verdict

# A pre-registration authority (on-box HMAC). A real study would persist this secret securely.
AUTHORITY = LocalHmacAuthority(b"example-study-secret-key-00000001")
PAST = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(hours=1)


# --- adapter: ingestion (raw source -> canonical corpus) ---
class Parser:
    def parse(self, source: Path) -> Corpus:
        # a real parser reads `source`; here we synthesize 6 units deterministically.
        return Corpus(units=tuple(Unit(f"u{i}", f"control text {i}") for i in range(6)))

    def source_fingerprint(self, source: Path) -> str:
        return "example-source-v1"


# --- adapter: the blind baseline (built from the data only) ---
class BaselineBuilder:
    def build(self, corpus: Corpus, *, claim_guard: ClaimBlindGuard[object]) -> BaselineArtifact:
        mean_len = sum(len(u.text) for u in corpus.units) / len(corpus.units)
        return build_baseline_artifact(
            corpus, {"mean_text_len": mean_len}, component_versions={"builder": "example@1"}
        )


# --- adapter: discovery + confirmation (Firewall B) ---
def discover(discovery_corpus: Corpus) -> list[Hypothesis]:
    h = Hypothesis(
        hypothesis_id="H1", statement="units share above-chance internal similarity",
        kind=HypothesisKind.WHOLE_CORPUS, origin=HypothesisOrigin.DISCOVERY,
        test_name="permutation", decision_rule="empirical p<=0.05 in the 'greater' tail",
        predicted_direction="greater",
    )
    return [lock_hypothesis(h, authority=AUTHORITY, instant=PAST)]


def confirm_held_out(hypothesis: Hypothesis, held_out: Corpus) -> Verdict:
    # a real study computes a statistic on `held_out`; here a deterministic stand-in.
    return Verdict.supported(hypothesis.hypothesis_id, "held-out test passed")


# --- adapter: external claims (Firewall A) ---
class Claims:
    def claims(self) -> list[ClaimRecord]:
        return [ClaimRecord(claim_id="c1", subject="c1", referents=("c1",),
                            assertion={"expected": "high"})]

    def claim_fingerprint(self) -> str:
        return "example-claims-v1"


def hypothesis_for(claim: ClaimRecord) -> Hypothesis:
    h = Hypothesis(
        hypothesis_id=f"H-{claim.claim_id}", statement="claim holds against the baseline",
        kind=HypothesisKind.WHOLE_CORPUS, origin=HypothesisOrigin.EXTERNAL_CLAIM,
        test_name="adjudication", decision_rule="baseline corroborates the claim",
        source_claim_id=claim.claim_id, predicted_direction="greater",
    )
    return lock_hypothesis(h, authority=AUTHORITY, instant=PAST)


def confirm_claim(hypothesis: Hypothesis, baseline: BaselineArtifact, claim: ClaimRecord) -> Verdict:
    return Verdict.supported(hypothesis.hypothesis_id, "baseline corroborates")


def main() -> None:
    source = Path(tempfile.mkdtemp()) / "corpus"  # unused by the synthetic parser
    definition = StudyDefinition(
        name="example-study",
        modes=frozenset(StudyMode),  # both DISCOVERY and ADJUDICATE
        parser=Parser(),
        research_questions=("does the example run end to end?",),
        claims_source=Claims(),
    )
    plan = StudyPlan(
        definition=definition, source=source,
        baseline_builder=BaselineBuilder(), authority=AUTHORITY,
        split=DiscoverConfirmSplit.from_partition({"u0", "u1", "u2"}, {"u3", "u4", "u5"}),
        discover=discover, confirm_held_out=confirm_held_out,
        hypothesis_for=hypothesis_for, confirm_claim=confirm_claim,
    )

    # gate_handler is required: auto_approve opts out of human review explicitly. A real run
    # supplies an operator handler that can block/park.
    result = run_study(plan, gate_handler=auto_approve)

    print(f"study: {result.study}")
    print(f"phases: {[p.name for p in result.phases]}")
    print(f"discovery verdicts: {[(v.hypothesis_id, v.label.value) for v in result.discovery_verdicts]}")
    if result.scorecard is not None:
        sc = result.scorecard
        print(f"scorecard: supported={sc.n_supported} contradicted={sc.n_contradicted} "
              f"indeterminate={sc.n_indeterminate} alignment_rate={sc.alignment_rate}")
    print(f"provenance entries: {len(result.provenance)} (chain verified before return)")


if __name__ == "__main__":
    main()
