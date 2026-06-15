# ADR-0001 — The independent blind baseline is the empirical reference

**Status:** Accepted (2026-06-15)

## Context

To evaluate a dataset — or to adjudicate external claims about it — without circularity,
there must be an object derived purely from the data that no external claim had a hand in
producing. Measuring claims against themselves, or against a reference contaminated by
those claims, proves nothing.

## Decision

The **baseline** — an empirical ML/NLP model of the data — is the single privileged
reference. It is built independently from the data, is deterministic and versioned, and is
measured against nothing. When external claims exist, they are tested **against** the
baseline; the baseline is never tested against them. (See ADR-0005 for the blindness
firewall that makes this real.)

## Consequences

- Verdicts are meaningful because they are made against an independent reference.
- The baseline pipeline must be runnable with any external claims withheld.
- Where the baseline is built from artifacts an external source also worded, independence
  is *scoped* (judgments, not wording) and stated explicitly. This motivates the
  `indeterminate` verdict (ADR-0004).
