# hc-assay — Methodology

This is the scientific core of the blueprint. It is dataset-agnostic: it speaks of *the
data*, *the baseline*, *external claims (optional)*, and *verdicts* — never of any
specific dataset, authority, or taxonomy.

---

## 1. The independent baseline (the yardstick)

The **baseline** is an empirical model of the dataset built purely from the data using
ML/NLP — embeddings, similarity and distance structure, graph/topology, clustering,
descriptive statistics. It is:

- **independent** — derived from the data itself, not from any external claim about the
  data;
- **deterministic and versioned** — fixed seeds, hashed inputs, recorded model/version, so
  the same inputs reproduce the same baseline;
- **the one privileged object** — every external claim is measured against it; it is
  measured against nothing.

The baseline is what makes a verdict mean something. Without an independent reference, a
study can only describe; with one, it can adjudicate.

## 2. Two firewalls

The rigor of the whole method rests on two separations, both enforced in code, not just
documented.

**Firewall A — claim-blindness (adjudication mode only).** When external claims exist, the
baseline must be built **blind to those claims.** The external source's answers — its
asserted relationships, strengths, labels, taxonomy — must never enter baseline
construction as inputs, features, or training labels. If they do, "the baseline agrees
with the claims" is circular and the result is void. The baseline is built from the data;
the claims are quarantined until adjudication.

> **Honest scope (engine):** the engine enforces this structurally where it can — the baseline
> builder is never *handed* a claims source (it is built inside a sealed `ClaimBlindGuard`), and
> the adjudication runner keeps claims out of the builder's reach (ADR-0008). What the guard
> cannot police is an adapter that smuggles external judgments into `Corpus` metadata/attributes
> or relations and then reads them in the builder — that path is closed by the adapter contract,
> not by the guard. Nor is it frame isolation: a builder that deliberately reflects into the
> runner's stack could reach the claims; only running the builder in a separate process would
> prevent that. The guarantee is against *accidental* circularity, which is the realistic failure.

**Firewall B — discover / confirm separation.** A pattern used to *discover* a hypothesis
must not be the data used to *confirm* it. Discovering a pattern and then "testing" it on
the same data proves nothing. So:

- discover on an exploration partition (or via descriptive analysis), lock the now-specific
  claim, then
- confirm on data the discovery never touched.

For unit-level claims this is a **held-out split**. For whole-corpus claims (where you
cannot hold out part of the object — e.g. global structure or coverage), confirmation is
against **null / permutation distributions** and **stability across resamples**: the
pattern must beat chance on something it was not fit to. Same principle, different
mechanism.

## 3. Hypotheses

Every hypothesis is **typed and falsifiable** — it names what is claimed, the test, the
data it runs on, and a pre-specified decision rule.

- **Discovery mode:** the data surfaces candidate hypotheses; they are made specific,
  **locked, and timestamped before confirmation** (see Firewall B). The questions are
  data-derived, which is legitimate *because* discovery and confirmation use different
  data — not because the questions were guessed in advance.
- **Adjudicate-external-claims mode:** each external claim is itself a pre-stated,
  falsifiable assertion about the data. The adapter converts each into a typed hypothesis.
  These are tested against the blind baseline.

"The claim" and "whether the claim is correct" are kept as separate objects throughout.

## 4. Verdicts

Confirmatory tests return one of **three** verdicts — never a forced binary:

- **Supported** — the baseline corroborates the claim/hypothesis at the pre-specified
  threshold.
- **Contradicted** — the baseline is inconsistent with the claim at the pre-specified
  threshold.
- **Indeterminate** — the method cannot decide: underpowered, out of the measurement's
  reach, or the disagreement is plausibly a limitation of the method rather than of the
  claim. Indeterminate is a real outcome, structured like the others — not a failure.

The third verdict is deliberate. A measure disagreeing with a claim is not automatically
proof the claim is wrong; it may be a limit of what the baseline can see. `indeterminate`
is the honest home for that case.

## 5. Scoring the external source (adjudication mode)

Once claims are adjudicated, the external source can be **scored against the validated
baseline** — alignment, divergence, gaps, redundancy, and whatever else the data surfaces.
The scoring dimensions are **outputs of method, not a pre-set checklist**: the data, not a
narrative, determines what is worth scoring. The source had no hand in producing the
reference it is scored against.

> **Implementation status (engine):** the engine computes the **measured frequency** part — a
> `SourceScorecard` with supported/contradicted/indeterminate counts and an `alignment_rate`
> (supported / decisive, indeterminate excluded). This is a measured frequency, explicitly not a
> normative quality score. The richer, data-surfaced dimensions (where it diverges, what it
> leaves as gaps, where it is redundant) are produced **downstream from the per-claim verdicts**
> the scorecard carries — a study surfaces them from the data; the engine does not impose a fixed
> set. The per-verdict evidence needed for that analysis is all in `SourceScorecard.verdicts`.

## 6. Method, not interpretation

There is a hard boundary between **measurement** (numbers produced by the engine) and
**interpretation** (what they mean). Interpretation lives strictly downstream and cannot
feed back into measurement. Any use of judgment — including LLM-assisted classification —
is treated as interpretation, fenced off, and labeled, so it cannot contaminate the
upstream baseline or the verdicts.

> **Implementation status (engine):** the engine provides this as a **type-level boundary**,
> not an automatic whole-pipeline retrofit. `assay_engine.methodology.fence` defines
> `Measurement` and `Interpretation`, and `Measurement` **refuses at construction** to hold an
> `Interpretation` (even nested) — so once a value is typed as a measurement, judgment cannot be
> smuggled into it. `fence()` crosses the boundary in the one legal direction
> (measurement → interpretation) and records the source measurement's ref. A study applies these
> types where judgment enters: LLM output from the reasoning seam is *raw judgment* and must be
> wrapped as an `Interpretation` (`judged_by` = the model id), never passed where a `Measurement`
> is expected. The engine enforces the direction structurally at the type boundary; it does not,
> and cannot, retro-classify arbitrary study values it never sees.

## 7. Reproducibility

- **Determinism:** fixed, documented seeds; inputs hashed; model names + versions recorded.
- **Provenance:** an append-only audit trail records every action before the next executes.
- **Pre-registration:** hypotheses (data-surfaced or claim-derived) are locked and
  RFC-3161 timestamped before confirmation. This is honestly described as an adaptive
  design with a timestamped lock — not as predictions guessed before any data.
- **Reproducibility package:** data, code, configuration, and logs are published with
  findings so any reviewer can reconstruct the full decision history.

## 8. Scoped-independence caveat

When the baseline is built from text or artifacts that an external source also authored,
the baseline is independent of that source's **judgments**, but not of its **wording or
framing**. This is an acceptable, necessary compromise — but it is claimed as *scoped*
independence, stated explicitly, and is one of the reasons `indeterminate` exists.
