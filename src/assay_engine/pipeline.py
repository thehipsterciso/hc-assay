"""Study runner — the composed, governed, end-to-end pipeline (ADR-0010).

The phase machine (:mod:`assay_engine.orchestration.phases`) *names* the ordered stages a
study moves through; the firewall runners enforce the methodology; the seams provide tracing,
experiment tracking, data versioning, and (in the adapter's callables) reasoning. This module
composes them into a single runnable flow, engine-owned so the ordering and the governance
handoffs are guaranteed once, not re-implemented per study:

    INGEST → BASELINE(blind, Firewall A) → [DISCOVERY → PREREGISTER → gate → CONFIRM (Firewall B)]
           → [ADJUDICATE → SCORE (Firewall A, shared baseline)] → REPORT

At every step it (a) records an append-only provenance entry *before the next step runs*
(GOVERNANCE §3), (b) opens a trace span (observability seam), optionally (c) versions the source
and logs to an experiment tracker, and (d) enforces the methodological invariants structurally:
the baseline is built blind, the split ids are validated against the corpus, hypotheses are
verifiably pre-registered before confirmation, a human gate reviews before *every* confirmatory
step, claim-derived hypotheses are locked before the baseline exists, and the visited phase
sequence must equal the mode's required sequence.

A study supplies the *domain* via a :class:`StudyPlan` (parser, baseline builder, the
discover/confirm/hypothesis_for callables, the claims source, optional feature builders); the
engine owns the *order, the firewalls, the gate, the provenance, the tracing, and the
versioning*. Reasoning enters only inside the study's own callables (which may use
:mod:`assay_engine.reasoning`); any such LLM output is *judgment*, so it should be wrapped as an
:class:`~assay_engine.methodology.fence.Interpretation` and never fed back into a measurement
(the fence). The runner imports no adapter (ARCHITECTURE §3).
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
import uuid
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, cast

from assay_engine._frozen import freeze_mapping, unfreeze
from assay_engine.baseline.determinism import corpus_fingerprint
from assay_engine.baseline.toolkit import BaselineArtifact, BaselineBuilder
from assay_engine.contracts.claims import ClaimRecord, claim_set_fingerprint
from assay_engine.contracts.features import FeatureMatrix
from assay_engine.contracts.schema import Corpus
from assay_engine.contracts.study import StudyDefinition, StudyMode
from assay_engine.methodology.adjudication import (
    ClaimConfirmer,
    SourceScorecard,
    adjudicate_with_baseline,
)
from assay_engine.methodology.discovery import HeldOutConfirmer, subset_corpus
from assay_engine.methodology.firewalls import (
    ClaimBlindGuard,
    DiscoverConfirmSplit,
    FirewallViolation,
)
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisOrigin
from assay_engine.methodology.preregistration import TimestampAuthority, require_preregistered
from assay_engine.methodology.verdict import Verdict
from assay_engine.observability.tracing import (
    OtelTracer,
    Tracer,
    bootstrap_tracing,
    run_trace_context,
)
from assay_engine.observability.tracking import ExperimentTracker
from assay_engine.orchestration.gates import GateDecision, GateError
from assay_engine.orchestration.phases import Phase, required_phases
from assay_engine.persistence.versioning import DataVersioner
from assay_engine.provenance import Clock, ProvenanceEntry, ProvenanceTrail

_UTC = _dt.timezone.utc

_log = logging.getLogger("assay_engine.pipeline")

DiscoverFn = Callable[[Corpus], Iterable[Hypothesis]]


class IngestionError(ValueError):
    """Ingestion failed (the parser raised or produced an unusable corpus)."""


@dataclass(frozen=True, slots=True)
class GateReview:
    """The packet handed to a gate handler at a governance transition.

    ``payload`` is a deep-frozen :class:`~assay_engine._frozen.FrozenDict` (immutable +
    hashable, #113). Because that is a ``Mapping`` and not a ``dict`` subclass, ``json.dumps``
    cannot serialize it directly — an operator-review handler that logs/serializes the payload
    must call :meth:`payload_dict` first (#141).
    """

    gate: str
    frm: Phase
    to: Phase
    summary: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        # deep-freeze the payload so this frozen record is truly immutable + hashable (#113)
        object.__setattr__(self, "payload", freeze_mapping(self.payload))

    def payload_dict(self) -> dict[str, Any]:
        """Return the payload as a plain, deeply-thawed, JSON-serializable ``dict`` (#141)."""
        return cast("dict[str, Any]", unfreeze(self.payload))


GateHandler = Callable[[GateReview], GateDecision]


def _engine_claim_fingerprint(claim_records: list[ClaimRecord]) -> str:
    """Engine-computed content hash of the EXACT claim set that will be scored (#137, #F-001).

    Delegates to the public :func:`~assay_engine.contracts.claims.claim_set_fingerprint` so the
    engine's authoritative fingerprint and the scheme adapters must implement in
    ``claim_fingerprint()`` are one and the same canonical function — the engine recomputes it
    over the materialized records (in scored order) and enforces agreement with the source's
    self-report, so an auditor re-deriving the fingerprint from the scored claims gets the value
    the trail records.
    """
    return claim_set_fingerprint(claim_records)


def _require_unique_ids(ids: list[str], what: str) -> None:
    """Raise FirewallViolation if ``ids`` contains a duplicate (#138).

    Identity (claim↔hypothesis↔verdict) must be unique within a run: a repeated id would
    otherwise be counted once per occurrence, inflating the scorecard denominator and biasing
    alignment_rate / verdict accounting.
    """
    seen: set[str] = set()
    dupes: list[str] = []
    for i in ids:
        if i in seen:
            dupes.append(i)
        seen.add(i)
    if dupes:
        raise FirewallViolation(
            f"duplicate {what} within one run: {sorted(set(dupes))[:3]} — identity must be "
            "unique (a repeat would inflate the scorecard denominator / verdict accounting)"
        )


def auto_approve(review: GateReview) -> GateDecision:
    """A non-interactive gate handler: approve and record the decision.

    This is the explicit "no operator" choice — it is **not** the default, so a study cannot
    silently bypass human review by omitting a handler (it must consciously pass this). Replace
    with an operator-driven handler (e.g. one wired to the LangGraph gate interrupt/resume in
    :mod:`assay_engine.orchestration`) for genuine human-in-the-loop parking; the handler may
    return ``approved=False`` to block the transition.
    """
    return GateDecision(
        approved=True,
        gate=review.gate,
        reason="non-interactive auto-approval",
        evidence={"transition": f"{review.frm.name}->{review.to.name}"},
    )


@dataclass(frozen=True, slots=True)
class StudyPlan:
    """Everything the runner needs for one run: the static definition + executable methodology.

    ``definition`` is the adapter's binding (parser, modes, claims source, questions, optional
    feature builders). The callables below are the adapter's *executable* methodology, validated
    against the declared modes: discovery needs ``split``/``discover``/``confirm_held_out``;
    adjudication needs ``hypothesis_for``/``confirm_claim`` (and a ``claims_source`` on the
    definition).
    """

    definition: StudyDefinition
    source: Path
    baseline_builder: BaselineBuilder
    authority: TimestampAuthority
    split: DiscoverConfirmSplit | None = None
    discover: DiscoverFn | None = None
    confirm_held_out: HeldOutConfirmer | None = None
    hypothesis_for: Callable[[ClaimRecord], Hypothesis] | None = None
    confirm_claim: ClaimConfirmer | None = None

    def __post_init__(self) -> None:
        modes = self.definition.modes
        if StudyMode.DISCOVERY in modes:
            missing = [
                n
                for n, v in (
                    ("split", self.split),
                    ("discover", self.discover),
                    ("confirm_held_out", self.confirm_held_out),
                )
                if v is None
            ]
            if missing:
                raise ValueError(f"DISCOVERY mode requires: {', '.join(missing)}")
        if StudyMode.ADJUDICATE_EXTERNAL_CLAIMS in modes:
            missing = [
                n
                for n, v in (
                    ("hypothesis_for", self.hypothesis_for),
                    ("confirm_claim", self.confirm_claim),
                )
                if v is None
            ]
            if missing:
                raise ValueError(f"ADJUDICATE_EXTERNAL_CLAIMS mode requires: {', '.join(missing)}")


@dataclass(frozen=True, slots=True)
class StudyResult:
    """The reproducibility package: the artifacts + the append-only trail that produced them."""

    study: str
    corpus_fingerprint: str
    baseline: BaselineArtifact
    discovery_verdicts: tuple[Verdict, ...]
    scorecard: SourceScorecard | None
    phases: tuple[Phase, ...]
    provenance: tuple[ProvenanceEntry, ...]
    source_version: str | None = None
    feature_matrices: tuple[FeatureMatrix, ...] = ()
    experiment_run_id: str | None = None

    def persist_trail(self, path: str | Path) -> Path:
        """Write the hash-chained provenance trail to ``path`` as JSON and return it (#F-045).

        ``run_study`` keeps the trail only in memory (``self.provenance``); a caller that needs a
        durable, re-verifiable audit trail across process exit must persist it. The written
        records round-trip through :func:`~assay_engine.provenance.from_records` and re-check via
        :func:`~assay_engine.provenance.verify_records`. Call ``tracker.log_artifact`` on the
        returned path to attach it to the experiment run.
        """
        import json

        from assay_engine.provenance import entries_to_records

        out = Path(path)
        out.write_text(
            json.dumps(list(entries_to_records(list(self.provenance))), indent=2),
            encoding="utf-8",
        )
        return out


def _count_logger(key: str, n: float) -> Callable[[ExperimentTracker, str], None]:
    """A typed metric-logging callback for :func:`run_study`'s best-effort tracker."""

    def _log(t: ExperimentTracker, rid: str) -> None:
        t.log_metric(rid, key, n)

    return _log


def _now() -> _dt.datetime:
    # Ordering instants are a security/methodology check and ALWAYS use real wall-clock — never
    # a test-injected clock (that is only for deterministic provenance hashes).
    return _dt.datetime.now(tz=_UTC)


def run_study(
    plan: StudyPlan,
    *,
    gate_handler: GateHandler,
    tracer: Tracer | None = None,
    tracker: ExperimentTracker | None = None,
    versioner: DataVersioner | None = None,
    clock: Clock | None = None,
    secret: bytes | None = None,
    trail: ProvenanceTrail | None = None,
    verify_trail: bool = True,
) -> StudyResult:
    """Run one study end-to-end through its governed phase sequence. See module docstring.

    ``gate_handler`` is **required** (no default), so governance review is a conscious choice —
    pass :func:`auto_approve` to opt out of human review explicitly, or an operator handler that
    can block/park. ``tracer`` defaults to :class:`OtelTracer` (real spans if OpenTelemetry + a
    provider are present, a graceful no-op otherwise). ``tracker`` (optional) logs params/metrics
    to an experiment store, best-effort (a tracker failure never aborts the run). ``versioner``
    (optional) content-addresses the source so the trail cites retrievable bytes. ``clock``
    injects a deterministic clock for the provenance timestamps only (ordering checks always use
    real time). ``secret`` keys the internal provenance trail with HMAC (forgery-resistant);
    mutually exclusive with passing your own ``trail``. ``trail`` may be a caller-owned
    :class:`ProvenanceTrail` so a run that *raises* still leaves the caller the partial trail.

    Raises ``IngestionError`` on a bad source, ``FirewallViolation``/``PreRegistrationError`` on
    a methodological breach, ``GateError`` if a gate blocks, and ``ValueError`` on a malformed run.
    """
    tracer = tracer or OtelTracer()
    if trail is not None and secret is not None:
        raise ValueError("pass either a caller-owned trail OR a secret to key a new one, not both")
    if secret is None and trail is None:
        # An engine-created unkeyed trail is tamper-evident (a naive edit breaks the SHA-256
        # chain) but NOT forgery-resistant: an adversary with write access can edit an entry and
        # recompute the whole genesis-rooted chain. That is fine for local reproducibility but
        # insufficient for an audit trail that crosses a trust boundary. Flag the insecure
        # default rather than letting it pass silently (pass 3, #F-049); pass a `secret` to key
        # the trail with HMAC, or `clock=`-driven deterministic repro if forgery is out of scope.
        warnings.warn(
            "run_study provenance trail is UNKEYED (secret=None) — tamper-evident but not "
            "forgery-resistant. Pass secret=<bytes> to HMAC-key the trail for audit trails that "
            "cross a trust boundary.",
            stacklevel=2,
        )
    defn = plan.definition
    modes = defn.modes
    required = required_phases(modes)
    trail = trail if trail is not None else ProvenanceTrail(secret=secret, clock=clock)
    visited: list[Phase] = []
    run_id: str | None = None

    def enter(phase: Phase, **payload: Any) -> None:
        visited.append(phase)
        trail.record("phase", f"enter {phase.name}", phase=phase.name, **payload)

    def track(fn: Callable[[ExperimentTracker, str], None]) -> None:
        # observability is best-effort: a tracker failure is recorded but never aborts a run.
        if tracker is None or run_id is None:
            return
        try:
            fn(tracker, run_id)
        except Exception as exc:  # noqa: BLE001 — tracker is an external, optional backend
            trail.record("tracking_error", f"experiment tracker call failed: {exc}")

    def run_gate(review: GateReview) -> None:
        # Record the decision once (snapshot approved/reason) and block on rejection (#94).
        decision = gate_handler(review)
        approved = bool(getattr(decision, "approved", False))
        reason = str(getattr(decision, "reason", ""))
        trail.record(
            "gate",
            f"gate {review.gate!r}: {'approved' if approved else 'blocked'}",
            gate=review.gate,
            approved=approved,
            reason=reason,
            transition=f"{review.frm.name}->{review.to.name}",
        )
        if not approved:
            raise GateError(
                f"gate {review.gate!r} blocked {review.frm.name}->{review.to.name}: {reason}"
            )

    trail.record(
        "run_start",
        f"study {defn.name!r} starting",
        study=defn.name,
        modes=sorted(m.value for m in modes),
        research_questions=list(defn.research_questions),
    )
    if tracker is not None:
        try:
            run_id = tracker.start_run(
                defn.name,
                {
                    "modes": ",".join(sorted(m.value for m in modes)),
                    "n_research_questions": len(defn.research_questions),
                },
            )
        except Exception as exc:  # noqa: BLE001
            # run_id stays None → every track() call silently no-ops and ALL metrics are dropped
            # for the whole run. Record it to the trail AND emit a structured warning so an
            # operator seeing no MLflow run knows why instead of guessing (pass 3, #F-028).
            trail.record("tracking_error", f"experiment tracker start_run failed: {exc}")
            _log.warning(
                "experiment tracker start_run failed (%s: %s); run metrics will not be logged "
                "to the tracker for this study",
                type(exc).__name__,
                exc,
            )

    ok = False
    started_at = time.monotonic()
    trace_ctx = ExitStack()
    try:
        # Bootstrap tracing once and correlate every phase/reasoning span to this run via baggage,
        # so a run's spans are findable by id and join the experiment-tracker run (#122).
        # Done INSIDE the try so a tracing-setup failure is still covered by the finally's
        # tracker.end_run cleanup — an already-started tracker run must never leak in RUNNING
        # state (the #110 class of bug) if bootstrap/context entry raises (#156). Best-effort.
        bootstrap_tracing()
        corr_id = run_id or uuid.uuid4().hex
        trace_ctx.enter_context(run_trace_context(corr_id))
        # ---- INGEST ----
        with tracer.span("phase:INGEST"):
            enter(Phase.INGEST)
            try:
                corpus = defn.parser.parse(plan.source)
                source_fp = defn.parser.source_fingerprint(plan.source)
            except Exception as exc:  # noqa: BLE001 — normalize adapter/IO ingestion failures
                raise IngestionError(f"parser failed to ingest {plan.source!r}: {exc}") from exc
            # The parser Protocol return type is unenforced at runtime; a misimplemented adapter
            # that returns None/list/dict would otherwise slip past the normalizer above and die
            # at `corpus.units` with an opaque AttributeError, violating the documented
            # "Raises IngestionError on a bad source" contract (#134).
            if not isinstance(corpus, Corpus):
                raise IngestionError(f"parser returned {type(corpus).__name__}, expected Corpus")
            if not isinstance(source_fp, str):
                raise IngestionError(
                    f"parser.source_fingerprint returned {type(source_fp).__name__}, expected str"
                )
            if not corpus.units:
                raise IngestionError("ingestion produced an empty corpus")
            cfp = corpus_fingerprint(corpus)
            source_version: str | None = None
            if versioner is not None:
                # The versioner is an optional seam; a storage failure (PermissionError,
                # OSError) must surface as the documented IngestionError, not a raw untyped
                # exception that the caller cannot distinguish from a fatal firewall breach
                # (pass 3, #F-008). Versioning is part of ingesting the source, so a failure to
                # content-address it is an ingestion failure.
                try:
                    source_version = versioner.put(str(plan.source))
                except Exception as exc:  # noqa: BLE001 — normalize optional-seam storage failures
                    raise IngestionError(
                        f"data versioner failed to store {plan.source!r}: {exc}"
                    ) from exc
            trail.record(
                "ingest",
                "parsed source into canonical corpus",
                source_fingerprint=source_fp,
                corpus_fingerprint=cfp,
                n_units=len(corpus.units),
                n_relations=len(corpus.relations),
                source_version=source_version,
            )
            # SLO-relevant scale metrics to the tracker so corpus-size↔latency regressions are
            # analysable from the experiment store, not only the provenance trail (pass 3,
            # #F-029). Best-effort via track() (no-ops if no tracker/run_id).
            track(_count_logger("n_units", float(len(corpus.units))))
            track(_count_logger("n_relations", float(len(corpus.relations))))
            # Compute the corpus unit-id set ONCE and reuse it for both the split-id and feature-id
            # validations (pass 4, #G-023 — was built twice on the same corpus).
            corpus_unit_ids = {u.unit_id for u in corpus.units}
            # split ids must reference real corpus units (no silent partition drift, audit H4)
            if StudyMode.DISCOVERY in modes:
                assert plan.split is not None
                unknown = (
                    set(plan.split.discovery_ids) | set(plan.split.confirm_ids)
                ) - corpus_unit_ids
                if unknown:
                    raise FirewallViolation(
                        f"split references {len(unknown)} id(s) absent from the corpus "
                        f"(e.g. {sorted(unknown)[:3]}) — partition would silently drop units"
                    )
            # optional dataset features (recorded + returned; the baseline builder is blind-built
            # from the corpus, so features are provenance/output, not a baseline input here)
            feature_matrices: list[FeatureMatrix] = []
            for fb in defn.feature_builders:
                fm = fb.build(corpus)
                # features must describe THIS corpus's units — no fictional or duplicate ids
                # (the feature-side analogue of the split-drift guard above).
                if len(set(fm.unit_ids)) != len(fm.unit_ids):
                    raise FirewallViolation(
                        f"feature builder {list(fb.provides)} returned duplicate unit_ids"
                    )
                ghost = set(fm.unit_ids) - corpus_unit_ids
                if ghost:
                    raise FirewallViolation(
                        f"feature builder {list(fb.provides)} returned {len(ghost)} unit_id(s) "
                        f"absent from the corpus (e.g. {sorted(ghost)[:3]})"
                    )
                feature_matrices.append(fm)
                trail.record(
                    "features",
                    f"built feature matrix ({len(fm.feature_names)} features)",
                    provides=list(fb.provides),
                    n_units=len(fm.unit_ids),
                    feature_names=list(fm.feature_names),
                )

        # ---- BASELINE (blind — Firewall A). Capture the ordering instant BEFORE the build. ----
        baseline_instant = _now()
        with tracer.span("phase:BASELINE"):
            enter(Phase.BASELINE)
            guard: ClaimBlindGuard[Any] = ClaimBlindGuard()
            with guard.sealed():
                baseline = plan.baseline_builder.build(corpus, claim_guard=guard)
            if baseline.corpus_fingerprint != cfp:
                raise FirewallViolation(
                    "baseline corpus_fingerprint does not match the ingested corpus — the baseline "
                    "was not built from this corpus"
                )
            trail.record(
                "baseline",
                "built blind baseline (Firewall A)",
                corpus_fingerprint=baseline.corpus_fingerprint,
                contents=sorted(baseline.contents),
                determinism=dict(baseline.determinism),
            )

        discovery_verdicts: tuple[Verdict, ...] = ()
        scorecard: SourceScorecard | None = None

        # ---- DISCOVERY → PREREGISTER → gate → CONFIRM (Firewall B) ----
        if StudyMode.DISCOVERY in modes:
            assert plan.split is not None and plan.discover is not None
            assert plan.confirm_held_out is not None
            discovery_corpus = subset_corpus(corpus, plan.split.discovery_ids)
            held_out = subset_corpus(corpus, plan.split.confirm_ids)

            with tracer.span("phase:DISCOVERY"):
                enter(Phase.DISCOVERY)
                if not discovery_corpus.units:
                    raise FirewallViolation("discovery partition selects no corpus units")
                hypotheses = list(plan.discover(discovery_corpus))  # only the discovery partition
                if not hypotheses:
                    # discover() surfaced nothing — a vacuous run indistinguishable from a broken
                    # callable that forgot to return. Fail loud (pass 3, #F-042).
                    raise FirewallViolation(
                        "discover() returned no hypotheses — a discovery run with zero "
                        "hypotheses is vacuous and cannot produce a confirmatory verdict"
                    )
                # within-run identity uniqueness: a repeated hypothesis_id would be counted once
                # per occurrence in the verdict accounting (#138)
                _require_unique_ids([h.hypothesis_id for h in hypotheses], "hypothesis_id")
                trail.record(
                    "discovery",
                    f"data surfaced {len(hypotheses)} candidate hypotheses",
                    n=len(hypotheses),
                    ids=[h.hypothesis_id for h in hypotheses],
                )

            with tracer.span("phase:PREREGISTER"):
                enter(Phase.PREREGISTER)
                if not held_out.units:
                    raise FirewallViolation("confirmation partition selects no corpus units")
                preregister_instant = _now()
                for h in hypotheses:
                    if h.origin is not HypothesisOrigin.DISCOVERY:
                        raise FirewallViolation(
                            f"hypothesis {h.hypothesis_id!r} is {h.origin.value!r}; the discovery "
                            "phase expects DISCOVERY-origin (data-surfaced) hypotheses"
                        )
                    vt = require_preregistered(
                        h, authority=plan.authority, not_after=preregister_instant
                    )
                    trail.record(
                        "preregister",
                        f"locked hypothesis {h.hypothesis_id!r}",
                        hypothesis_id=h.hypothesis_id,
                        digest=vt.digest,
                        locked_at=vt.instant.isoformat(),
                    )
                run_gate(
                    GateReview(
                        gate="review-locked-hypotheses",
                        frm=Phase.PREREGISTER,
                        to=Phase.CONFIRM,
                        summary="review locked hypotheses before confirmatory testing",
                        payload={
                            "hypothesis_ids": [h.hypothesis_id for h in hypotheses],
                            "research_questions": list(defn.research_questions),
                        },
                    )
                )

            with tracer.span("phase:CONFIRM"):
                enter(Phase.CONFIRM)
                confirmed: list[Verdict] = []
                for h in hypotheses:
                    verdict = plan.confirm_held_out(h, held_out)  # only the held-out partition
                    # A confirmer that forgets to `return` yields None; accessing
                    # verdict.hypothesis_id would raise an opaque AttributeError instead of the
                    # documented typed error (pass 3, #F-021). Guard the contract explicitly.
                    if not isinstance(verdict, Verdict):
                        raise FirewallViolation(
                            f"confirm_held_out returned {type(verdict).__name__} for hypothesis "
                            f"{h.hypothesis_id!r} — expected a Verdict"
                        )
                    if verdict.hypothesis_id != h.hypothesis_id:
                        raise FirewallViolation(
                            f"verdict reports hypothesis_id {verdict.hypothesis_id!r} for "
                            f"hypothesis {h.hypothesis_id!r} — hypothesis↔verdict misattribution"
                        )
                    confirmed.append(verdict)
                    trail.record(
                        "verdict",
                        f"confirmed {h.hypothesis_id!r}: {verdict.label.value}",
                        hypothesis_id=h.hypothesis_id,
                        label=verdict.label.value,
                        rule=verdict.decision_rule,
                    )
                discovery_verdicts = tuple(confirmed)
                for lbl in ("supported", "contradicted", "indeterminate"):
                    n = sum(1 for v in discovery_verdicts if v.label.value == lbl)
                    track(_count_logger(f"discovery_{lbl}", float(n)))

        # ---- ADJUDICATE → SCORE (Firewall A; the baseline built above is reused, blind) ----
        if StudyMode.ADJUDICATE_EXTERNAL_CLAIMS in modes:
            assert defn.claims_source is not None
            assert plan.hypothesis_for is not None and plan.confirm_claim is not None
            claim_records = list(defn.claims_source.claims())
            if not claim_records:
                raise ValueError(
                    "adjudication mode but the claims source yielded no claims — nothing to adjudicate"
                )
            # within-run identity uniqueness: a repeated claim_id would inflate the scorecard (#138)
            _require_unique_ids([c.claim_id for c in claim_records], "claim_id")
            track(_count_logger("n_claims", float(len(claim_records))))  # SLO metric (#F-029)
            # The engine fingerprints the EXACT claims it will score (authoritative), and records
            # the source's self-report separately for cross-check rather than trusting it (#137).
            engine_claim_fp = _engine_claim_fingerprint(claim_records)
            source_claim_fp = defn.claims_source.claim_fingerprint()
            # Enforce — do not merely *record* — the fingerprint agreement (pass 3, #F-001).
            # Pass-2 #137 made the engine fingerprint authoritative and surfaced the match as a
            # boolean in the gate payload, but a non-interactive gate (auto_approve) approves
            # regardless, so a source whose claim_fingerprint() lies about a claim set that
            # claims() does not actually yield completed a run with the discrepancy silently
            # recorded. The source's self-report is a content commitment for pre-registration;
            # a disagreement means the scored claims are not the set the source attested to —
            # a provenance-integrity breach the engine must refuse, not defer to a human.
            if source_claim_fp != engine_claim_fp:
                raise FirewallViolation(
                    "claims source self-reported claim_fingerprint "
                    f"{source_claim_fp!r} but the engine computed {engine_claim_fp!r} over the "
                    "claims actually yielded — the scored claim set does not match the source's "
                    "attested fingerprint (provenance-integrity breach)"
                )
            prev_phase = Phase.CONFIRM if StudyMode.DISCOVERY in modes else Phase.BASELINE
            run_gate(
                GateReview(
                    gate="review-baseline-and-claims",
                    frm=prev_phase,
                    to=Phase.ADJUDICATE,
                    summary="review the blind baseline and the external claim set before adjudication",
                    payload={
                        "n_claims": len(claim_records),
                        "claim_ids": [c.claim_id for c in claim_records],
                        "claim_fingerprint": engine_claim_fp,  # engine-computed over scored claims
                        "source_reported_claim_fingerprint": source_claim_fp,  # unverified self-report
                        "claim_fingerprint_matches_source": engine_claim_fp == source_claim_fp,
                        "baseline_fingerprint": baseline.corpus_fingerprint,
                        "research_questions": list(defn.research_questions),
                    },
                )
            )
            with tracer.span("phase:ADJUDICATE"):
                enter(Phase.ADJUDICATE)

                def _record_adjudication_step(h: Hypothesis, v: Verdict) -> None:
                    trail.record(
                        "preregister",
                        f"locked claim hypothesis {h.hypothesis_id!r}",
                        hypothesis_id=h.hypothesis_id,
                        source_claim_id=h.source_claim_id,
                        locked_at=h.locked_at,
                    )
                    trail.record(
                        "verdict",
                        f"adjudicated {v.hypothesis_id!r}: {v.label.value}",
                        hypothesis_id=v.hypothesis_id,
                        label=v.label.value,
                        rule=v.decision_rule,
                    )

                # not_after = baseline_instant: a claim-derived hypothesis must have been locked
                # before the (shared) baseline existed. The SAME materialized claim_records that
                # were gated/recorded are scored (#95).
                scorecard = adjudicate_with_baseline(
                    baseline,
                    claim_records,
                    hypothesis_for=plan.hypothesis_for,
                    confirm=plan.confirm_claim,
                    authority=plan.authority,
                    not_after=baseline_instant,
                    source_name=defn.name,
                    on_step=_record_adjudication_step,
                )
            with tracer.span("phase:SCORE"):
                enter(Phase.SCORE)
                trail.record(
                    "score",
                    f"source scorecard for {defn.name!r}",
                    n_supported=scorecard.n_supported,
                    n_contradicted=scorecard.n_contradicted,
                    n_indeterminate=scorecard.n_indeterminate,
                    alignment_rate=scorecard.alignment_rate,
                )
                sc = scorecard
                track(lambda t, rid: t.log_metric(rid, "n_supported", float(sc.n_supported)))
                track(lambda t, rid: t.log_metric(rid, "n_contradicted", float(sc.n_contradicted)))
                track(
                    lambda t, rid: t.log_metric(rid, "n_indeterminate", float(sc.n_indeterminate))
                )
                ar = sc.alignment_rate
                if ar is not None:
                    track(lambda t, rid: t.log_metric(rid, "alignment_rate", float(ar)))

        # ---- REPORT ----
        with tracer.span("phase:REPORT"):
            enter(Phase.REPORT)
            trail.record(
                "report",
                "assembled reproducibility package",
                n_discovery_verdicts=len(discovery_verdicts),
                has_scorecard=scorecard is not None,
            )

        if tuple(visited) != required:
            raise FirewallViolation(
                f"visited phase sequence {[p.name for p in visited]} != required "
                f"{[p.name for p in required]}"
            )
        if verify_trail:
            # Re-verify the whole chain before handing back the result. This re-hashes every
            # entry — O(N) — which is redundant for an in-memory trail this call built and never
            # mutated (each entry was hashed correctly when appended). It is a cheap safety net in
            # the common case but a real cost for very large trails, so a perf-sensitive caller
            # that trusts the in-process trail may pass verify_trail=False (pass 3, #F-036). The
            # important re-verification — of a trail deserialized from an external store — is the
            # caller's verify_records() on from_records(), which this flag does not affect.
            trail.verify()  # the provenance chain must be intact before we hand back the result
        # Terminal success entry (pass 3, #F-006): a phase 'report' record is not a run-level
        # terminus, so a trail truncated mid-run is otherwise indistinguishable from one that
        # completed. Record run_end ONLY after verify() passes, so its presence as the last
        # entry is an affirmative "this run finished with an intact chain" marker. The payload is
        # deterministic (no wall-clock) so the provenance-hash determinism guarantee holds — the
        # non-deterministic run duration goes to the experiment tracker as an SLO metric instead.
        trail.record(
            "run_end",
            f"study {defn.name!r} completed successfully",
            study=defn.name,
            experiment_run_id=run_id,
            n_provenance_entries=len(trail.entries) + 1,  # +1 counts this terminal entry itself
        )
        track(_count_logger("run_duration_s", time.monotonic() - started_at))  # SLO metric (#F-029)
        # Correlate the hash-chained trail to the experiment run (#G-009): persist it as a JSON
        # artifact on the tracker so an auditor opening the run can retrieve the provenance that
        # produced its metrics. Best-effort, like the other tracker calls — never aborts the run.
        if tracker is not None and run_id is not None:

            def _log_trail(t: ExperimentTracker, rid: str) -> None:
                import json
                import os
                import tempfile

                from assay_engine.provenance import entries_to_records

                with tempfile.NamedTemporaryFile(
                    "w", suffix="_provenance.json", delete=False, encoding="utf-8"
                ) as fh:
                    json.dump(list(entries_to_records(list(trail.entries))), fh, indent=2)
                    path = fh.name
                # Clean up the scratch file after the tracker has copied it into its store, so a
                # tracked run does not leak a temp file (with provenance contents) on every call
                # (#H-013). The tracker reads/copies synchronously in log_artifact.
                try:
                    t.log_artifact(rid, path)
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

            track(_log_trail)
        ok = True
    except Exception as exc:
        # Record a terminal failure entry BEFORE re-raising so the abort reason is recoverable
        # from the (caller-owned) trail, not lost (#109).
        last_phase = visited[-1].name if visited else "start"
        try:
            trail.record(
                "run_failed",
                f"{type(exc).__name__} during {last_phase}",
                error_type=type(exc).__name__,
                message=str(exc)[:2000],
                last_phase=last_phase,
            )
        except Exception as inner:  # noqa: BLE001 — never mask the original failure
            # The run_failed entry could not be recorded (payload unserializable, clock raised,
            # trail lock contended). Don't silently swallow — emit a structured warning so the
            # failure reason is at least in the logs, even though it is absent from the trail
            # (pass 3, #F-030). The original exception is still re-raised below.
            _log.warning(
                "could not record run_failed provenance entry (%s: %s)",
                type(inner).__name__,
                inner,
            )
        raise
    finally:
        trace_ctx.close()
        if tracker is not None and run_id is not None:
            try:
                # a failed run must be distinguishable from a successful one in the store (#110)
                tracker.end_run(run_id, status="FINISHED" if ok else "FAILED")
            except Exception:  # noqa: BLE001,S110 — best-effort cleanup
                pass

    return StudyResult(
        study=defn.name,
        corpus_fingerprint=cfp,
        baseline=baseline,
        discovery_verdicts=discovery_verdicts,
        scorecard=scorecard,
        phases=tuple(visited),
        provenance=trail.entries,
        source_version=source_version,
        feature_matrices=tuple(feature_matrices),
        experiment_run_id=run_id,
    )
