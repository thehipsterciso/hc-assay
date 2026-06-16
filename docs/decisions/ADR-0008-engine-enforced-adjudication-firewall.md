# ADR-0008 — The engine enforces Firewall A by construction (adjudication runner)

**Status:** Accepted (2026-06-16)

## Context

Firewall A — *the baseline is built blind to the external claims it will be tested against* —
is the load-bearing guarantee of adjudication mode (METHODOLOGY.md §2, ADR-0005). If the
baseline can see the claims while it is built, "the baseline agrees with the claims" is
circular and every verdict is void.

The engine shipped the *parts* to honour this — a custodial `ClaimBlindGuard`, a
`BaselineBuilder` whose signature takes no claims source, confirmatory tests, verdicts — but no
*composition*. So a study had to assemble the firewall itself: build the baseline, then somehow
keep the claims out of that step, then adjudicate. Nothing in the engine forced that ordering.
A study could build its baseline with the claims in scope (passed in, read from a shared
object, glanced at "just for features") and the engine would raise nothing. For a blueprint
cloned into many studies, that places the single most important methodological guarantee on
each cloner's discipline — exactly the "good intentions" ADR-0005 says to replace with
structure.

Separately, METHODOLOGY.md §5 ("score the external source against the validated baseline") had
no engine implementation at all.

## Decision

1. Provide `methodology.adjudicate(corpus, claims_source, *, baseline_builder, hypothesis_for,
   confirm)` as the engine-owned adjudication composition. It enforces Firewall A **by
   construction**: the claims source is kept in the runner's local scope and is *never handed
   to the builder*; the baseline is built inside a sealed `ClaimBlindGuard` that holds nothing,
   and the claims are used only *after* the baseline exists. No object reachable from the
   builder contains the claims, so it cannot read them by any path. (An adversarial review of
   an earlier custodial-guard design — where the guard held the source — found a builder could
   read past the sealed check via the guard's private `_claims_source`; keeping the source out
   of the builder's reach entirely is strictly stronger.)
2. It enforces that every adjudicated claim yields an `EXTERNAL_CLAIM` (pre-stated) hypothesis,
   not a data-surfaced one — conflating the two would breach the discover/confirm separation.
3. It implements §5 as a `SourceScorecard`: counts of supported/contradicted/indeterminate and
   an `alignment_rate` = supported / (supported + contradicted) — the frequency with which the
   independent baseline corroborates the source on *decisive* claims, with indeterminate
   excluded. This is a measured frequency, explicitly **not** a normative judgement of the
   source; richer dimensions (where it aligns, diverges, leaves gaps) are data-surfaced
   downstream, per §5, not a fixed checklist.

The study still supplies the `confirm` callable (only it knows the baseline's structure and how
a claim maps onto a measurement) and the `hypothesis_for` adapter (claim → typed hypothesis).
The engine owns the *ordering and the firewall*, the study owns the *domain*.

## Consequences

- Firewall A is now structural at the engine level, not a per-study convention. The remaining,
  documented residual (an adapter could smuggle a claim into `Corpus.metadata`/`relations`,
  ADR-0005/#1) is unchanged and is the adapter's contract obligation — the runner never places
  claims in the corpus.
- The §5 scorecard exists and is honest: a frequency on decisive claims, not a quality score.
- Studies get a correct path instead of a footgun; a study that needs a bespoke flow can still
  compose the primitives directly, but the default is safe.
