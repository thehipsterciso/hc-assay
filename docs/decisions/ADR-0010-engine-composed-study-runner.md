# ADR-0010 — The engine composes and governs the end-to-end study run

**Status:** Accepted (2026-06-16)

## Context

By ADR-0008/0009 the engine owned each *guarantee* in isolation — the firewalls, pre-registration
— and the five infra seams (reasoning, orchestration, observability, persistence, baseline) were
ported and individually live-verified. But nothing **composed** them into one runnable flow. The
phase machine (`orchestration/phases.py`) *named* the ordered stages; `gates.py` even noted that
"the append-only provenance store … [is] wired by the orchestration layer when it lands." Until
then, "the workflow" — ingest → blind baseline → discover/confirm → adjudicate/score → report,
with the governance handoffs between them — existed only as discipline each cloning study would
have to re-implement. That is precisely the per-clone footgun ADR-0005/0008 exist to remove, and
it meant there was no end-to-end artifact to make public with confidence.

Two concrete gaps:
- No executor walked the phases, enforced the order, and wired the methodology runners + seams.
- The GOVERNANCE §3 append-only provenance trail did not exist at all.

## Decision

1. **Append-only provenance trail** (`assay_engine/provenance.py`). A `ProvenanceTrail` records
   every action — run start, ingest, baseline, each discovered/locked hypothesis, every gate
   decision, each verdict, the scorecard, the report — *before the next step runs*. Entries form
   a hash chain (each over `(prev_hash, seq, kind, summary, payload, timestamp)` via the one
   type-faithful hasher, `_canonical`) rooted at a fixed genesis. There is no remove/edit/reorder
   API; the exposed view is an immutable tuple; `verify()`/`verify_records()`/`from_records()`
   detect any removal, reorder, or edit in a serialized trail. This makes GOVERNANCE §3's "no step
   can be retroactively removed or reordered" structural.

2. **Study runner** (`assay_engine/pipeline.py`, `run_study`). The engine-owned executor that
   walks `required_phases(modes)` and at each phase: opens a trace span (observability seam),
   records provenance, and enforces the methodology by construction —
   - BASELINE is built inside a sealed `ClaimBlindGuard` (Firewall A) and its fingerprint must
     match the ingested corpus;
   - DISCOVERY hands the discover step only the discovery partition; PREREGISTER verifies every
     hypothesis with `require_preregistered`; a **governance gate** reviews the locked hypotheses
     before CONFIRM, which tests only the held-out partition (Firewall B);
   - ADJUDICATE reuses the *single* blind baseline via `adjudicate_with_baseline` (factored out of
     `adjudicate` for this) with `not_after` = the instant captured *before* the baseline build, so
     the lock-before-baseline guarantee survives the shared-baseline composition;
   - the visited phase sequence must equal the mode's required sequence (no skip/reorder/extra),
     and the provenance chain must verify, before a `StudyResult` is returned.

   A study supplies the *domain* via a `StudyPlan` (parser, baseline builder, the
   discover/confirm/hypothesis_for callables, claims source); the engine owns the *order, the
   firewalls, the gate, the provenance, and the tracing*. The runner imports no adapter.

3. **Mode-accurate phases.** Building the composition exposed that `required_phases` forced the
   discovery spine (DISCOVERY/PREREGISTER/CONFIRM) onto *every* study, including adjudicate-only
   ones — which derive hypotheses from claims, not data. The modes are independent, so the spine
   is now conditional on `DISCOVERY` mode, mirroring how ADJUDICATE/SCORE are conditional on
   adjudication mode. An adjudicate-only study is INGEST→BASELINE→ADJUDICATE→SCORE→REPORT.

4. **The governance gate is a pluggable handoff.** `run_study` takes a `gate_handler`
   (`GateReview → GateDecision`); the default auto-approves and records, and an operator/LangGraph
   handler can block (raising `GateError`) or park. This is where human-in-the-loop review of the
   pre-registered hypotheses happens, before any confirmatory test.

## Consequences

- There is now a single, engine-owned, **runnable** end-to-end workflow, verified both purely
  (`tests/test_pipeline.py`, both modes + negative paths) and **live** against a real backend
  (`tests/integration/test_pipeline_live.py` — a real OpenTelemetry span fires around every phase
  handoff, with an intact provenance chain). The reference adapter (`tests/reference_study.py`) is
  the dataset-agnostic demonstration of the workflow.
- GOVERNANCE §3 is honoured by construction, not promised. Honest scope: an in-memory trail is as
  trustworthy as its process; the hash chain's value is that a *serialized* trail round-trips only
  if untouched, so an external store/reviewer can verify integrity. Non-repudiable third-party
  attestation of the trail's *time* is the same pluggable concern as pre-registration (ADR-0009),
  out of scope here.
- The lock-before-baseline ordering for adjudication is preserved across the shared-baseline
  composition because the runner captures `not_after` before the build and passes it to
  `adjudicate_with_baseline`.
- What remains the study's job (by ADR-0002, not a gap): the concrete parser, baseline builder, and
  methodology callables — i.e. the domain. The engine guarantees the order and the firewalls around
  whatever a study plugs in.
