# hc-assay

**A reusable blueprint for rigorous, reproducible empirical ML/NLP on security & privacy data.**

`hc-assay` is not a single study. It is an **engine + a methodology** that you clone onto a
dataset to build an independent, empirical understanding of it — and, where the dataset
carries external expert-asserted claims, to adjudicate those claims against that
independent understanding.

Status: **engine implemented and composed.** The dataset-agnostic engine (`src/assay_engine`)
is in place and hardened — the contracts, the methodology core (hypotheses, three verdicts, the
two firewalls, content-bound pre-registration, the measurement↔interpretation fence), all five
infrastructure seams (tiered reasoning, self-hosted observability, persistence, orchestration,
baseline toolkit), an append-only hash-chained provenance trail, and a single composed runner —
`run_study` — that ties them into one governed end-to-end flow (ADR-0010). The engine core is
dependency-free; heavy backends are lazy-imported behind optional extras (`reasoning`,
`observability`, `persistence`, `orchestration`, `baseline`, or `all`) so it installs, imports,
and unit-tests offline (ADR-0006). You build a study by implementing the adapter Protocols for
your dataset and calling `run_study`.

## Quickstart

```bash
pip install assay-engine            # dependency-free core
pip install "assay-engine[all]"     # + every optional backend
```

```python
from assay_engine import StudyPlan, run_study, auto_approve

# implement the adapter Protocols for your dataset (parser, baseline builder, the
# discover/confirm callables, an optional external-claims source), then:
plan = StudyPlan(definition=..., source=..., baseline_builder=..., authority=..., ...)

result = run_study(plan, gate_handler=auto_approve)   # gate_handler is required
print(result.phases, result.discovery_verdicts, result.scorecard)
result.provenance        # append-only, hash-chained audit trail (verified before return)
```

A complete, runnable example (both modes, synthetic data, no backends needed) is in
[`examples/minimal_study.py`](examples/minimal_study.py):

```bash
python examples/minimal_study.py
```

`gate_handler` is required so governance is a conscious choice: pass `auto_approve` to opt out
of human review explicitly, or an operator handler that can block/park before each confirmatory
step. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the adapter contract and
[docs/METHODOLOGY.md](docs/METHODOLOGY.md) for the method.

---

## What it does

Given a security & privacy dataset, `hc-assay`:

1. **Builds an independent empirical baseline** of the data using ML/NLP — deterministic,
   versioned, and reproducible by a hostile reviewer. This baseline is the one object in
   the system derived purely from the data.
2. Lets the data **surface features, hypotheses, questions, and findings** — discovery
   driven by method, not by a pre-conceived narrative.
3. **Optionally adjudicates external expert claims.** If the dataset ships claims asserted
   by some external authority (relationships, labels, a taxonomy, mappings), those are
   converted into typed, falsifiable hypotheses and tested **against the baseline** —
   which is kept blind to those claims. Each test returns a verdict: **supported,
   contradicted, or indeterminate.**
4. **Scores the external source** against the validated baseline — where it aligns, where
   it doesn't — as an output of method, with interpretation fenced off from measurement.

Everything runs **on-box** (local-first, data-sovereign); nothing leaves the machine.

## Two modes

- **Discovery** — no external claims; the data surfaces the questions and the findings.
- **Adjudicate external claims** — external expert assertions exist and are tested against
  the independent baseline. *(Optional, per dataset.)*

The external claims are a **pluggable adapter input**. A clone may run pure discovery with
no claims at all. The blueprint itself never assumes any particular dataset, claim source,
or domain taxonomy.

## Engine + adapter

- The **engine** is dataset-agnostic and reusable: orchestration, governance gates, the
  reasoning seam, observability, persistence, the baseline toolkit, and the methodology
  core (hypothesis typing, three-verdict testing, the firewalls, the measurement↔
  interpretation fence).
- An **adapter** is what you write when you clone onto a new dataset: an ingestion parser,
  the canonical-schema binding, an optional external-claims source, a domain glossary /
  feature builders, and that study's pre-registration.

Each concrete study lives in **its own repository** built on this engine, to keep every
study's pre-registration clean and independent.

## Documentation

| Doc | Purpose |
|---|---|
| [docs/CHARTER.md](docs/CHARTER.md) | Purpose, principles, scope, operating model |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | The research method, the two firewalls, verdicts, reproducibility |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Engine vs adapter, components, the adapter contract, onboarding |
| [docs/GOVERNANCE.md](docs/GOVERNANCE.md) | Gates, pre-registration, provenance, independence, data sovereignty |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Canonical terms |
| [docs/decisions/](docs/decisions/) | Architecture Decision Records |
