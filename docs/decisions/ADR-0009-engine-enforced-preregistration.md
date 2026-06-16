# ADR-0009 — The engine enforces pre-registration integrity (content binding + verifiable timestamp + ordering)

**Status:** Accepted (2026-06-16)

## Context

GOVERNANCE §2 defines pre-registration as three steps performed *before* any confirmatory test:
a hypothesis is (1) made specific and typed, (2) **content-hashed and committed**, and (3)
**timestamped against a trusted authority**. METHODOLOGY §3 and both firewalls
(ADR-0005, ADR-0008) rest on it: a verdict is only meaningful if the claim, the test, and the
decision rule were fixed before the result that decides them was in hand.

Steps 2–3 were a *presence sentinel*. `Hypothesis.locked` asserted only that `locked_at` and
`timestamp_proof` were both non-`None`, so:

- a hand-written `timestamp_proof="rfc3161:demo"` "locked" a hypothesis;
- nothing bound the proof to the hypothesis *content* — a study could lock a placeholder and
  swap in a different statement, test, or decision rule afterward;
- nothing checked the lock *preceded* confirmation — a hypothesis could be "pre"-registered
  after the baseline (and therefore the answer) was known.

The confirmatory runners called `require_locked` (the presence check), so the engine's single
most load-bearing methodological guarantee was, in code, decorative (audit pass 1, issue #6;
GOVERNANCE §2 implementation-status note).

## Decision

Add `assay_engine.methodology.preregistration`, which makes the lock mean what the method says,
and wire the runners to enforce it.

1. **Content binding.** `canonical_hypothesis_digest(hypothesis)` is a type-faithful SHA-256
   over a hypothesis's *decision-bearing* fields (statement, kind, origin, test, decision rule,
   predicted direction, source claim, params). It deliberately excludes `hypothesis_id` (a
   label) and the lock fields themselves (they attest *to* the digest). The canonicalizer is
   hoisted to `assay_engine._canonical` so it sits below both `methodology` and `baseline` and
   is the **one** content-hash implementation (the baseline determinism harness now re-exports
   it) — no second, drifting hasher.

2. **Verifiable timestamp via a pluggable authority.** A `TimestampAuthority` Protocol exposes
   `verify(digest, proof) -> VerifiedTimestamp`, raising `PreRegistrationError` (a
   `FirewallViolation` subclass) on any invalid proof. The engine ships exactly one real
   authority, `LocalHmacAuthority`: `stamp` issues `local-hmac:v1:<instant>|<hmac>` where the
   MAC is `HMAC-SHA256(secret, digest ‖ instant)`; `verify` recomputes the MAC over the digest
   the engine derived from the *current* hypothesis and constant-time compares. A proof
   therefore verifies iff the content is unchanged, the instant is unchanged, and the same
   secret is used. The engine ships **no** silent-accept authority, so the runners require one
   to be supplied (the ADR-0008 principle: the engine, not each study, owns the guarantee).

3. **Lock before confirm.** `require_preregistered(hypothesis, *, authority, not_after)`
   verifies the proof and rejects a lock whose attested instant is not strictly earlier than
   `not_after`. The runners capture `not_after` at the confirmation moment and replace their
   `require_locked` calls with `require_preregistered`. `verify_preregistration` additionally
   requires the self-reported `locked_at` to equal the attested instant, so a study cannot
   display a time the authority did not vouch for.

4. **Blessed locking path.** `lock_hypothesis(hypothesis, *, authority, instant=None)` returns a
   locked copy whose proof binds its content and whose `locked_at` matches the attestation —
   the way studies (and tests) should pre-register. Re-locking is refused.

`Hypothesis.locked` and `confirm.require_locked` are retained as cheap **presence** predicates
(defense-in-depth) and documented as such; the methodology-grade check is
`require_preregistered`, enforced by the runners.

## Consequences

- Pre-registration is now structural at the engine level: a hand-set sentinel proof, a post-lock
  content swap, a forged/other-authority proof, a tampered `locked_at`, and a lock dated at or
  after confirmation are all refused — by the engine, for all 100+ studies, not by each
  cloner's discipline.
- **Honest scope (the recurring lesson, ADR-0008).** `LocalHmacAuthority` proves content
  integrity, time binding, and unforgeability *relative to a secret on this box*. Whoever holds
  that secret could backdate a proof: it is local tamper-evidence, **not** third-party
  non-repudiation. A study that needs non-repudiation implements `TimestampAuthority` over an
  RFC-3161 TSA (which receives only the digest, never the data — so it stays compatible with
  data sovereignty, ADR-0003, at the cost of an external dependency the study opts into). The
  engine provides the Protocol and the ordering/binding enforcement; it does not ship a network
  TSA client.
- Content binding covers the *structured fields*. Free text inside `statement`/`params` is
  hashed (so it cannot change after locking) but the engine cannot judge whether that text is
  *meaningful* — that remains the review obligation GOVERNANCE §2 already names ("timestamped
  adaptive design", not "predictions registered before any data").
- The ordering check is strongest when the lock genuinely predates the run (e.g. hypotheses
  pre-registered in an earlier step and loaded later). When a runner-driven `discover` step
  locks a hypothesis microseconds before confirming it, ordering is near-trivial there and the
  *content binding* is the load-bearing guarantee for that path; the ordering check still
  rejects future-dated and stale post-result locks. This is stated, not papered over.
