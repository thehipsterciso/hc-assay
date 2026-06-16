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

> **Implementation status (engine scaffold):** the engine's lock check is currently a
> *presence sentinel* — it verifies a hypothesis carries both a lock time and a timestamp
> proof before confirmation. RFC-3161 token verification against a trusted timestamp
> authority, and enforcing that the lock precedes the confirmation run, are part of the
> pre-registration infrastructure not yet wired (audit pass 1, issue #6). Until then, treat
> the lock as a procedural sentinel, not a cryptographic guarantee.

## 3. Provenance

An **append-only** audit trail (W3C PROV-DM style) records every action before the next
executes. No step can be retroactively removed or reordered. This is the spine of
reproducibility and of the independence claim.

> **Implementation status (engine):** the engine ships the *seams* for this — gate decisions
> are emitted as append-only `gate_decisions` records, and a `ProvenanceRecorder` hook is
> available at the gate. The persistent, ordered provenance *store* itself is wired by a
> study/runner; the present-tense guarantees above describe that wired end-state.

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
