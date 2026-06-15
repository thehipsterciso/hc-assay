# ADR-0005 — Two firewalls: claim-blindness and discover/confirm separation

**Status:** Accepted (2026-06-15)

## Context

Two distinct ways to fool yourself: (1) build the reference using the very claims you mean
to test (circularity), and (2) confirm a pattern on the same data you discovered it on
(double-dipping). Both must be prevented structurally, not by good intentions.

## Decision

**Firewall A — claim-blindness.** When external claims exist, the baseline is built blind to
them: the claim source's answers never enter baseline construction as inputs, features, or
labels. Enforced by making the external-claims source structurally separable from the
baseline pipeline, so the baseline can be produced with it withheld.

**Firewall B — discover/confirm separation.** The data used to discover a hypothesis is not
the data used to confirm it. Unit-level claims: a held-out split sealed until pre-
registration. Whole-corpus claims (no held-out object possible): null/permutation
distributions plus stability across resamples. Same principle, different mechanism.

## Consequences

- Data-derived questions are legitimate, because discovery and confirmation use different
  data — this is what separates the method from HARKing.
- The engine must provide both confirmation mechanisms and refuse to confirm on
  discovery data.
- Both firewalls are enforced in code and exercised by tests, not asserted in docstrings.
