# hc-assay — Charter

**Status:** Planning / documentation phase.

---

## 1. Purpose

`hc-assay` is a reusable blueprint — an engine plus a methodology — for conducting
**rigorous, reproducible empirical machine-learning and NLP analysis of security & privacy
data.** It is designed to be cloned onto any dataset in that domain and produce findings
that a hostile reviewer can reproduce, not opinions that must be taken on trust.

The blueprint is dataset-agnostic. It makes no assumption about any particular corpus,
authority, taxonomy, or set of claims. Everything dataset-specific lives in an **adapter**
and in the **instance repository** for a given study — never in the engine.

## 2. Principles

1. **Hypothesis first, evidence next, conclusion last.** Conclusions are earned by method,
   in that order — never asserted ahead of the evidence.
2. **Reproducible by a hostile reviewer.** Every finding is reconstructable from published
   data, code, configuration, and an append-only audit trail. Determinism and provenance
   are first-class, not afterthoughts.
3. **Independent baseline as the reference.** The empirical understanding of the data is
   built independently. When external claims are present, they are judged against that
   independent baseline — never against themselves.
4. **Method, not interpretation.** Truths, alignment, gaps, and misgivings are outputs of
   measurement. Where interpretation is required, it is fenced off downstream so it cannot
   contaminate upstream measurement.
5. **Local-first and data-sovereign.** All computation, storage, and observability run
   on-box. No data leaves the machine.
6. **Null and indeterminate results are first-class.** "No effect" and "cannot decide" are
   findings, structured identically to positive findings.

## 3. The two modes

- **Discovery mode.** The dataset carries no external claims. The engine builds the
  baseline and lets the data surface features, hypotheses, questions, and findings.
- **Adjudicate-external-claims mode.** The dataset ships claims asserted by an external
  authority. Each claim is converted into a typed, falsifiable hypothesis and tested
  against the independent baseline (kept blind to those claims). The external source is
  then scored against the validated baseline.

A clone selects the mode(s) that fit its dataset. The two are not exclusive.

## 4. Scope

**In scope:** an analytical engine and methodology; the governance, reproducibility, and
provenance machinery; the adapter contract that lets a new dataset be onboarded; the
three-verdict adjudication of optional external claims.

**Out of scope (lives in instance repos / adapters):** any specific dataset, the parser
for it, its domain glossary, its external-claim source, and that study's research
questions and pre-registration. The engine never imports dataset specifics.

**The engine does not:** make normative judgments about whether a dataset or an external
source is "good"; prescribe action; or generalize a study's findings beyond its own corpus
without explicit qualification.

## 5. Operating model

Single-operator. The operator builds and governs the infrastructure; the platform conducts
the analysis within approved scope. Independence from operator bias is achieved
**structurally**, not by a co-reviewer:

- deterministic, code-enforced governance gates that cannot be silently bypassed;
- an append-only provenance trail recorded before each step executes;
- pre-registration locked and timestamped before any confirmatory step;
- a complete, publishable reproducibility package.

See [GOVERNANCE.md](GOVERNANCE.md).

## 6. Instance model

Each concrete study is a **separate repository** built on this engine (e.g. one per
dataset). Separate repositories keep each study's pre-registration independent and clean —
no study's confirmatory data or hypotheses contaminate another's. The engine may be
consumed as a shared, versioned foundation.
