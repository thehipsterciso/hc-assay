# hc-assay — Glossary

Canonical, dataset-agnostic terms. A study's own glossary (in its instance repo) defines
dataset-specific vocabulary; this file defines only blueprint terms.

| Term | Definition |
|---|---|
| **Engine** | The reusable, dataset-agnostic core: orchestration, gates, reasoning seam, observability, persistence, baseline toolkit, methodology core. |
| **Adapter** | The per-dataset code a clone implements: ingestion parser, canonical-schema binding, optional external-claims source, glossary/feature builders, study definition. |
| **Instance** | A concrete study built on the engine, in its own repository. |
| **Baseline** | The independent empirical model of a dataset, built purely from the data with ML/NLP. The privileged reference everything else is measured against. |
| **External claim** | An assertion about the data made by an external authority (a relationship, label, strength, mapping, or taxonomy). Optional input; quarantined from baseline construction. |
| **Discovery mode** | Operating with no external claims: the data surfaces features, hypotheses, questions, and findings. |
| **Adjudicate-external-claims mode** | Operating where external claims exist: each is converted to a typed hypothesis and tested against the blind baseline. |
| **Hypothesis** | A typed, falsifiable claim naming what is asserted, the test, the data it runs on, and a pre-specified decision rule. |
| **Verdict** | The outcome of a confirmatory test: **supported**, **contradicted**, or **indeterminate**. |
| **Exploratory phase** | Characterization / discovery on exploration data; produces no decision-language outputs. |
| **Confirmatory phase** | Testing of locked hypotheses on untouched data (held-out split) or against null/permutation + stability (whole-corpus). |
| **Firewall A — claim-blindness** | The baseline is built blind to any external claims, so adjudication is not circular. |
| **Firewall B — discover/confirm separation** | The data used to discover a hypothesis is not the data used to confirm it. |
| **Null / permutation test** | Confirmation mechanism for whole-corpus claims that cannot be held out: the observed pattern must beat randomized versions of the data. |
| **Pre-registration** | Locking a hypothesis before confirmation with a proof that **binds its content and id** and carries a **verifiable timestamp** from a trusted authority (on-box HMAC by default, RFC-3161 pluggable); the confirmatory runners enforce content-binding + lock-before-confirm, and the confirm primitives take an optional `authority=` to opt into the same check (ADR-0009). |
| **Provenance** | The append-only audit trail of every action. |
| **Measurement ↔ interpretation fence** | The hard boundary keeping interpretation downstream so it cannot contaminate upstream measurement. |
| **Scoped independence** | Independence of an external source's *judgments* even when the baseline is built from artifacts that source also *worded*. |
