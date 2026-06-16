# hc-assay — Governance, Reproducibility & Independence

The governance machinery is what lets a single operator produce results a hostile reviewer
cannot dismiss. It is engine-level and dataset-agnostic.

---

## 1. Gates (human-in-the-loop at structural transitions)

The analysis cannot cross a structural boundary without an explicit, recorded approval.
Gates are **deterministic code** — they cannot be silently bypassed. The canonical
transitions a gate guards:

- **Pre-analysis checkpoint** — prerequisites verified before any data enters the system
  (skeleton runs, split determinism verified, provenance store live).
- **Lock / pre-registration** — the data-surfaced or claim-derived hypotheses are locked
  and timestamped before any confirmatory step. This is the firewall between exploration
  and confirmation.
- **Review** — the exploratory characterization and the locked hypotheses are reviewed
  before confirmatory results are produced or any held-out / null-tested data is touched.
- **Reporting** — confirmed results are reviewed before anything is framed as a conclusion
  or leaves the analytical layer.
- **Escalation** — any move into new territory (new data, materially different method,
  scope expansion) parks for explicit approval rather than auto-proceeding.

A concrete study maps its phases onto these transitions; the exact count and labels are an
engine convention, not a dataset concern.

### Gate interrupt/resume protocol (engine mechanics)

A gate node parks the run via an `interrupt` and resumes when the operator's decision is
delivered (`{gate_id, decision, rationale}`). The engine enforces three properties so the
governance trail is sound; a cloning study must respect the state-shape requirement:

- **Correlation guard** — a resumed decision must name the gate currently parked; a stale or
  misrouted decision aimed at another gate is refused, not applied to whatever is waiting.
- **Recoverable, never bricked** — `interrupt` persists the resume value into the checkpoint
  before the node returns, so a malformed/mis-correlated value re-fires a fresh interrupt
  (the operator can re-submit) instead of raising and stranding the gate forever. Only an
  **approved** decision is terminal (re-entry is a no-op); a **rejected/deferred** gate
  re-prompts so a revise→re-review loop works.
- **Durable parking** — gate graphs must be compiled with the durable checkpointer
  (`compile_graph(..., requires_checkpointer=True)`); without one `interrupt` is a silent
  no-op and the gate would never pause. Resume must use the *same* checkpointer (keyed by
  `run_id` as `thread_id`).

**State-shape requirement for cloners:** gate decisions are returned as
`{"gate_decisions": [record]}` partial updates, so a study's graph state must declare
`gate_decisions` with a list/append reducer — otherwise each gate would overwrite the prior
one and the append-only trail would lose all but the last decision.

## 2. Pre-registration

Before any confirmatory test runs, the relevant hypotheses are:

1. made specific and typed (what is claimed, the test, the data, the decision rule),
2. content-hashed and committed,
3. **RFC-3161 timestamped** against a trusted timestamp authority.

This is honestly characterized as a **timestamped adaptive design**: methods are fixed
first; the data informs the questions; the questions are then locked and timestamped before
they are tested. It is not claimed to be "predictions registered before any data."

> **Implementation status (engine):** pre-registration is enforced by construction **in the
> confirmatory runners** (`adjudicate`, `discover_and_confirm`; ADR-0009). They verify, via a
> supplied `TimestampAuthority`, that a hypothesis's proof **binds its content and id** (the
> canonical digest of its decision-bearing fields), that the attested **timestamp is
> verifiable**, and that the lock **precedes confirmation** — a hand-set sentinel string, a
> post-lock content/id swap, a forged proof, or a lock dated at/after the ordering instant are
> all refused. (In adjudication the ordering instant is captured *before the baseline build*, so
> a claim-derived hypothesis must be locked before the baseline exists; in discovery a
> data-surfaced hypothesis is necessarily locked inside the runner, so there the *content*
> binding is the load-bearing guarantee — see ADR-0009.) The engine ships one real,
> data-sovereign authority (`LocalHmacAuthority`, on-box HMAC) and the Protocol so a study can
> plug an RFC-3161 TSA. Honest scope: the local authority is tamper-evidence *relative to an
> on-box secret*, not third-party non-repudiation. The lower-level confirm *primitives*
> (`confirm_whole_corpus`/`confirm_unit_level`) gate on the cheap presence predicate by default
> and take an optional `authority=` to opt into the full check; a study that confirms outside a
> runner must pass it (or call `require_preregistered` itself). `Hypothesis.locked` is only a
> presence predicate; `methodology.preregistration.require_preregistered` is the
> methodology-grade check.

## 3. Provenance

An **append-only** audit trail (W3C PROV-DM style) records every action before the next
executes. No step can be retroactively removed or reordered. This is the spine of
reproducibility and of the independence claim.

> **Implementation status (engine):** wired (ADR-0010). `assay_engine.provenance.ProvenanceTrail`
> is an append-only, hash-chained trail; the study runner (`assay_engine.pipeline.run_study`)
> records every action — ingest, blind baseline, each locked hypothesis (discovery *and*
> claim-derived), every gate decision, each verdict, the scorecard, the report — *before the next
> runs*, and verifies the chain before returning. There is no remove/edit/reorder API.
> **Integrity, honestly, in two tiers:** the default unkeyed chain is *tamper-evident against
> naive tampering and accidental corruption* (a single-entry edit, a reorder, or a deletion is
> caught by `verify_records`) but is **not** forgery-proof — a party who controls the serialized
> bytes can edit a payload and recompute the whole SHA-256 chain. Pass a `secret=` and the chain
> is HMAC-keyed, so the head cannot be recomputed without the secret (a downstream store cannot
> silently rewrite and re-seal history); `verify_records` must be given the same secret. An
> in-memory trail is still as trustworthy as its process, and non-repudiable third-party
> attestation of the trail's *time* is the same pluggable concern as pre-registration (§2),
> out of scope here. A caller may pass its own trail to `run_study` so a run that *raises* (a
> blocked gate, a firewall violation) still leaves an auditable partial trail.

## 4. Single-operator structural independence

Independence from operator bias is achieved structurally, not by a co-reviewer:

- **Code gates** the operator cannot silently bypass.
- **Append-only provenance** that records the full decision history.
- **Timestamped pre-registration** committing to hypotheses before they are tested.
- **A complete reproducibility package** published with findings.

This is a deliberate methodological position and is stated explicitly in any output.

## 5. Data sovereignty

All computation, storage, tracing, and experiment tracking run **on-box**. No data,
embeddings, traces, or results leave the machine. SaaS observability and any service that
would ship analyzed content off-box are disqualified by this constraint, independent of
cost.

## 6. Reproducibility guarantees (summary)

- Deterministic seeds (documented); inputs hashed; model names + versions recorded.
- Append-only provenance for every action.
- Timestamped pre-registration before confirmation.
- Published data + code + configuration + logs sufficient to reconstruct every verdict.
