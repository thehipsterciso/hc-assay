# hc-assay — Architecture

The blueprint is split into a reusable **engine** and per-dataset **adapters**. The
single most important architectural rule is the boundary between them:

> **The engine never imports dataset specifics. Adapters implement defined interfaces the
> engine calls.** A clone is: implement the adapter, register it, run.

This is the line the prior internal platform blurred and that `hc-assay` exists to keep
clean.

---

## 1. The engine (reusable, dataset-agnostic)

| Component | Responsibility |
|---|---|
| **Orchestration & governance gates** | The analysis graph, phase machine, and human-in-the-loop gates at structural transitions (see GOVERNANCE.md). |
| **Reasoning seam** | A single abstraction over LLM execution by *stakes tier* — local model for bulk/low-stakes, frontier model for high-stakes — with timeouts, retries, and tracing. No component talks to an LLM directly. |
| **Observability** | Self-hosted tracing (OpenTelemetry → on-box collector) and experiment tracking. On-box only; no SaaS. |
| **Persistence** | Durable run state / checkpointing, data versioning, and a vector store — all local. |
| **Baseline toolkit** | Generic, dataset-agnostic builders: embeddings, similarity/distance, graph/topology, clustering, descriptive statistics. The raw material for any baseline. |
| **Methodology core** | Hypothesis types; the three-verdict confirmatory test (supported / contradicted / indeterminate); the two firewalls (claim-blindness, discover/confirm); the measurement↔interpretation fence; null/permutation + stability machinery for whole-corpus confirmation. |

The engine knows nothing about *what* the data is. It knows how to build a baseline from a
canonical schema, how to test typed hypotheses against it, and how to govern and record the
process.

## 2. The adapter (per-dataset — what a clone writes)

| Adapter piece | Responsibility |
|---|---|
| **Ingestion parser** | Raw source → the canonical schema. The only place that understands the source's native format. |
| **Canonical-schema binding** | Maps the dataset's entities/fields onto the engine's canonical types. |
| **External-claims source** *(optional)* | If the dataset ships external expert-asserted claims, this exposes them so the engine can convert each into a typed hypothesis. Absent for pure-discovery datasets. **Quarantined from baseline construction** (Firewall A). |
| **Domain glossary / feature builders** | Dataset-specific vocabulary handling and any features only meaningful for this dataset. |
| **Study definition** | The study's research questions and its pre-registration. |

## 3. The engine ↔ adapter contract

- The engine depends only on **interfaces** (canonical schema types, an optional
  claims-provider interface, a feature-builder interface). It imports no adapter module.
- Adapters depend on the engine, never the reverse, and never on each other.
- The external-claims source is structurally separable so the baseline pipeline can be run
  with it withheld — that is how Firewall A (claim-blindness) is enforced, not just
  promised.

## 4. Onboarding a new dataset

1. Create a new instance repository on the engine.
2. Implement the adapter (parser, schema binding, optional claims source, glossary).
3. Write the study definition (questions + pre-registration).
4. Run: the engine builds the baseline, runs discovery and/or claim-adjudication, gates the
   transitions, records provenance, and emits verdicts and (if applicable) the source
   scorecard.

## 5. Technical substrate

Local-first, on-box, data-sovereign:

- Python; LangGraph / LangChain for the analysis graph and agent orchestration.
- Reasoning seam over a local LLM runtime (bulk) and a frontier model via fixed-cost
  subscription (high-stakes) — no metered API.
- Self-hosted OpenTelemetry tracing collector + a local experiment-tracking store.
- Durable checkpointer (local database), data versioning, and a local vector store.

Specific tools are engine implementation details and may evolve; the engine/adapter
boundary and the methodology core are the stable contract.
