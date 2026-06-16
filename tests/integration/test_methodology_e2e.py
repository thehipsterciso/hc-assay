"""End-to-end methodology composition (pure — always runs).

Composes the real engine pieces into one run: corpus → FeatureMatrix → baseline primitives →
reproducible BaselineArtifact (determinism harness) → a locked, pre-registered hypothesis →
confirmatory test against a null distribution → a three-valued verdict. This is the methodology
the engine exists to support, exercised composed rather than as isolated units.
"""

from __future__ import annotations

from assay_engine.baseline.determinism import build_baseline_artifact, corpus_fingerprint
from assay_engine.baseline.primitives import cosine_similarity_matrix, descriptive_stats
from assay_engine.contracts.schema import Corpus, Unit
from assay_engine.methodology.confirm import confirm_whole_corpus
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.verdict import VerdictLabel


def _corpus() -> Corpus:
    return Corpus(units=tuple(Unit(f"u{i}", f"control text {i}") for i in range(6)))


def test_baseline_to_verdict_pipeline_supported():
    corpus = _corpus()
    # baseline: a tiny embedding-like feature matrix → similarity structure → summary stat
    rows = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9], [0.7, 0.7], [0.5, 0.5]]
    sim = cosine_similarity_matrix(rows)
    offdiag = [sim[i][j] for i in range(len(rows)) for j in range(len(rows)) if i != j]
    observed = descriptive_stats(offdiag)["mean"]

    artifact = build_baseline_artifact(
        corpus, {"similarity_mean": observed}, component_versions={"builder": "e2e@1"}
    )
    assert artifact.corpus_fingerprint == corpus_fingerprint(corpus)
    assert "seed" in artifact.determinism and artifact.determinism["input_hashes"]["corpus"]

    # a pre-registered, locked, direction-bound hypothesis: "mean off-diagonal similarity is
    # higher than a null permutation of the structure"
    hypo = Hypothesis(
        hypothesis_id="H1",
        statement="corpus exhibits above-chance internal similarity",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="permutation",
        decision_rule="empirical p<=0.05 in the 'greater' tail, stable across resamples",
        locked_at="2026-06-16T00:00:00Z",
        timestamp_proof="rfc3161:demo",
        predicted_direction="greater",
    )
    # null: similarity means from shuffled/independent structure, all well below `observed`.
    # Needs enough samples that the smallest empirical p (1/(n+1)) can clear alpha=0.05.
    null = [0.05 + 0.0005 * i for i in range(100)]  # 100 nulls in ~[0.05, 0.10], << observed
    resamples = [observed] * 20  # stable: every resample reproduces the high observed value
    verdict = confirm_whole_corpus(
        hypo, observed=observed, null_distribution=null, alpha=0.05, resample_statistics=resamples
    )
    assert verdict.label is VerdictLabel.SUPPORTED
    assert verdict.evidence["stability"] == 1.0


def test_baseline_artifact_reproducible_across_two_builds():
    corpus = _corpus()
    a = build_baseline_artifact(corpus, {"k": [1, 2, 3]}, component_versions={"builder": "e2e@1"})
    b = build_baseline_artifact(corpus, {"k": [1, 2, 3]}, component_versions={"builder": "e2e@1"})
    assert a.corpus_fingerprint == b.corpus_fingerprint
    assert a.determinism["seed"] == b.determinism["seed"]
