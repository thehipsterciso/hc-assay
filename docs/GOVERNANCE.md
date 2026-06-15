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

## 2. Pre-registration

Before any confirmatory test runs, the relevant hypotheses are:

1. made specific and typed (what is claimed, the test, the data, the decision rule),
2. content-hashed and committed,
3. **RFC-3161 timestamped** against a trusted timestamp authority.

This is honestly characterized as a **timestamped adaptive design**: methods are fixed
first; the data informs the questions; the questions are then locked and timestamped before
they are tested. It is not claimed to be "predictions registered before any data."

## 3. Provenance

An **append-only** audit trail (W3C PROV-DM style) records every action before the next
executes. No step can be retroactively removed or reordered. This is the spine of
reproducibility and of the independence claim.

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
