# ADR-0004 — Three-verdict adjudication (supported / contradicted / indeterminate)

**Status:** Accepted (2026-06-15)

## Context

A two-way verdict (supported / not-supported) collapses two very different outcomes:
"the baseline contradicts the claim" and "the method cannot decide." Conflating them
overstates what the analysis knows and invites a hostile reviewer to reject the lot.

## Decision

Confirmatory tests return exactly one of three verdicts:

- **Supported** — the baseline corroborates the claim at the pre-specified threshold.
- **Contradicted** — the baseline is inconsistent with the claim at the pre-specified
  threshold.
- **Indeterminate** — underpowered, beyond the measurement's reach, or the disagreement is
  plausibly a method limitation rather than a claim error.

All three are structured identically and are first-class outputs.

## Consequences

- A measure disagreeing with a claim is not silently reported as "the claim is wrong";
  `indeterminate` is the honest home for ambiguous cases (and for the scoped-independence
  caveat in ADR-0001).
- Every confirmatory result must carry the evidence and the decision rule behind its
  verdict, so a reviewer can re-derive it.
