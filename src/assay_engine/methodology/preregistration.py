"""Pre-registration integrity (METHODOLOGY.md §3, GOVERNANCE.md §2).

GOVERNANCE §2 defines pre-registration as three steps: a hypothesis is (1) made specific and
typed, (2) **content-hashed and committed**, and (3) **timestamped against a trusted authority**
— *before* any confirmatory test. Steps 2–3 were a presence sentinel until now: ``Hypothesis.locked``
asserted only that ``locked_at`` and ``timestamp_proof`` were non-``None``, so a hand-written
``timestamp_proof="rfc3161:demo"`` "locked" a hypothesis and nothing stopped a study from
locking *after* it had seen the baseline, or from swapping the hypothesis content after locking
(audit pass 1, issue #6). Both firewalls (:mod:`adjudication`, :mod:`discovery`) and all of
:mod:`confirm` rest on the lock, so a sentinel lock made the three verdicts decorative.

This module makes the lock mean what the method says, by construction:

- **Content binding** — :func:`canonical_hypothesis_digest` is a type-faithful SHA-256 over a
  hypothesis's *decision-bearing* fields (statement, kind, origin, test, decision rule,
  predicted direction, source claim, params). A valid proof must attest to *this* digest, so
  the content the verdict is about is provably the content that was locked: change the claim,
  the test, or the decision rule after locking and verification fails.
- **Verifiable timestamp** — a pluggable :class:`TimestampAuthority` returns a
  :class:`VerifiedTimestamp` only if the proof genuinely binds the digest. The engine ships one
  real, data-sovereign authority (:class:`LocalHmacAuthority`, on-box HMAC) and the *Protocol*
  so a study can plug an RFC-3161 TSA. It ships **no** silent-accept authority.
- **Lock before confirm** — :func:`require_preregistered` rejects a lock whose attested time is
  not strictly before the confirmation moment, so a hypothesis cannot be "pre"-registered after
  the result is known.

Honest scope (the lesson carried from ADR-0008): :class:`LocalHmacAuthority` proves content
integrity, time binding, and unforgeability *relative to a secret that lives on this box*.
Whoever holds that secret could backdate a proof — it is local tamper-evidence, **not**
third-party non-repudiation. A study that needs non-repudiation wires an RFC-3161 authority
(which sends only the digest, never the data, so it stays compatible with data sovereignty —
ADR-0003 — at the cost of an external dependency the study opts into). And content binding
covers the *structured fields*: free text inside ``statement``/``params`` is hashed (so it
cannot change after locking) but the engine cannot judge whether that text is *meaningful* —
that remains a review obligation (GOVERNANCE §2 "timestamped adaptive design").
"""

from __future__ import annotations

import datetime as _dt
import hmac
from dataclasses import dataclass, replace
from typing import Protocol

from assay_engine._canonical import canonical_json, hash_text
from assay_engine.methodology.firewalls import FirewallViolation
from assay_engine.methodology.hypothesis import Hypothesis

_UTC = _dt.timezone.utc
_PROOF_PREFIX = "local-hmac:v1:"
_PROOF_FIELD_SEP = "|"  # ISO-8601 and lowercase hex never contain "|"


class PreRegistrationError(FirewallViolation):
    """A hypothesis failed pre-registration verification (METHODOLOGY §3, GOVERNANCE §2).

    A subclass of :class:`FirewallViolation` so existing ``except FirewallViolation`` handlers
    in the runners and studies treat a bad lock as the firewall breach it is.
    """


@dataclass(frozen=True, slots=True)
class VerifiedTimestamp:
    """The authority's attestation that ``digest`` existed at ``instant``."""

    instant: _dt.datetime  # timezone-aware, normalized to UTC
    authority: str
    digest: str


class TimestampAuthority(Protocol):
    """Engine contract: verify that ``proof`` binds ``digest``, returning the attested time.

    Implementations MUST raise :class:`PreRegistrationError` (not return a sentinel) when the
    proof is malformed, does not bind ``digest``, or is otherwise invalid — the engine treats a
    non-raising return as a genuine attestation.
    """

    def verify(self, digest: str, proof: str) -> VerifiedTimestamp: ...


class StampingAuthority(TimestampAuthority, Protocol):
    """A study-side authority that can also *issue* proofs (used by :func:`lock_hypothesis`)."""

    def stamp(self, digest: str, *, instant: _dt.datetime | None = None) -> str: ...


def _require_aware_utc(instant: _dt.datetime, what: str) -> _dt.datetime:
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise PreRegistrationError(
            f"{what} must be timezone-aware (a naive datetime has no defined instant)"
        )
    return instant.astimezone(_UTC)


def canonical_hypothesis_digest(hypothesis: Hypothesis) -> str:
    """A type-faithful SHA-256 over a hypothesis's decision-bearing content **and its id**.

    Includes ``hypothesis_id``: although it is a label, it is fixed at lock time and is the key
    the runners attribute verdicts by (``verdict.hypothesis_id``), so leaving it unbound would
    let a post-lock id swap file a verdict under an id the proof never attested (adversarial
    review, #80). Excludes only the lock fields themselves (``locked_at``/``timestamp_proof`` —
    they attest *to* this digest, so binding them would be circular).

    Raises :class:`PreRegistrationError` if the content cannot be canonicalized reproducibly
    (a non-finite float or an unhashable leaf in ``params``) — the pre-registration entrypoints
    must surface a typed firewall error, not a bare ``ValueError``/``TypeError`` (#82).
    """
    payload = {
        "hypothesis_id": hypothesis.hypothesis_id,
        "statement": hypothesis.statement,
        "kind": hypothesis.kind.value,
        "origin": hypothesis.origin.value,
        "test_name": hypothesis.test_name,
        "decision_rule": hypothesis.decision_rule,
        "source_claim_id": hypothesis.source_claim_id,
        "predicted_direction": hypothesis.predicted_direction,
        # decision thresholds are decision-bearing content — bind them so a pre-registered alpha /
        # stability bar cannot be changed post-hoc (pass 5, #H-001).
        "alpha": hypothesis.alpha,
        "stability_threshold": hypothesis.stability_threshold,
        "params": dict(hypothesis.params),
    }
    try:
        return hash_text(canonical_json(payload))
    except (ValueError, TypeError) as exc:
        raise PreRegistrationError(
            f"hypothesis {hypothesis.hypothesis_id!r} cannot be canonicalized for a content "
            f"digest ({exc}); pre-registration requires reproducibly hashable content "
            "(no non-finite floats or unhashable leaves in params)"
        ) from None


class LocalHmacAuthority:
    """A real, on-box timestamp authority binding a digest and an instant under a secret key.

    ``stamp`` issues ``local-hmac:v1:<instant-iso>|<hmac-hex>`` where the MAC is
    ``HMAC-SHA256(secret, digest || instant)``. ``verify`` recomputes the MAC over the digest
    the engine derived from the *current* hypothesis and the instant carried in the proof, and
    constant-time compares. The proof therefore verifies iff the content is unchanged, the
    instant is unchanged, and the same secret is used — without the secret it cannot be forged
    for arbitrary content or time.

    Honest scope: this is local tamper-evidence, not third-party non-repudiation — the holder of
    ``secret`` could backdate (see module docstring). Use an RFC-3161 authority when you need a
    third party to vouch for the time.
    """

    authority_id = "local-hmac"

    def __init__(self, secret: bytes) -> None:
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
            raise ValueError("LocalHmacAuthority secret must be >= 16 bytes of key material")
        self._secret = bytes(secret)

    def _mac(self, digest: str, instant_iso: str) -> str:
        msg = canonical_json(["local-hmac:v1", digest, instant_iso]).encode("utf-8")
        return hmac.new(self._secret, msg, "sha256").hexdigest()

    def stamp(self, digest: str, *, instant: _dt.datetime | None = None) -> str:
        when = instant if instant is not None else _dt.datetime.now(tz=_UTC)
        when = _require_aware_utc(when, "stamp instant")
        instant_iso = when.isoformat()
        return f"{_PROOF_PREFIX}{instant_iso}{_PROOF_FIELD_SEP}{self._mac(digest, instant_iso)}"

    def verify(self, digest: str, proof: str) -> VerifiedTimestamp:
        if not proof.startswith(_PROOF_PREFIX):
            raise PreRegistrationError(
                f"proof is not a {self.authority_id} v1 token (wrong prefix)"
            )
        body = proof[len(_PROOF_PREFIX) :]
        instant_iso, sep, mac_hex = body.partition(_PROOF_FIELD_SEP)
        if not sep or not instant_iso or not mac_hex:
            raise PreRegistrationError("malformed local-hmac proof (expected <instant>|<mac>)")
        # The MAC field must be exactly the hex of a SHA-256 digest. Validating its shape here
        # (a) rejects garbage early and (b) keeps non-ASCII/non-hex out of hmac.compare_digest,
        # which raises TypeError on non-ASCII str rather than returning False (#81).
        if len(mac_hex) != 64 or any(c not in "0123456789abcdef" for c in mac_hex):
            raise PreRegistrationError("malformed local-hmac proof (mac is not 64 lowercase hex)")
        try:
            parsed = _dt.datetime.fromisoformat(instant_iso)
        except ValueError:
            raise PreRegistrationError(f"proof instant is not ISO-8601: {instant_iso!r}") from None
        instant = _require_aware_utc(parsed, "proof instant")
        expected = self._mac(digest, instant_iso)
        if not hmac.compare_digest(expected, mac_hex):
            # Either the content (digest) changed since locking, the instant was tampered, or the
            # proof was issued under a different secret. All are pre-registration failures.
            raise PreRegistrationError(
                "proof does not bind this hypothesis's content at the stated time "
                "(content changed after locking, or proof was forged/issued by another authority)"
            )
        return VerifiedTimestamp(instant=instant, authority=self.authority_id, digest=digest)


def lock_hypothesis(
    hypothesis: Hypothesis,
    *,
    authority: StampingAuthority,
    instant: _dt.datetime | None = None,
) -> Hypothesis:
    """Return a locked copy of ``hypothesis`` whose proof binds its current content.

    The engine's blessed way to pre-register: it computes the content digest, has ``authority``
    stamp it, and records the attested instant in ``locked_at`` so the displayed lock time and
    the cryptographic proof always agree. Re-locking an already-locked hypothesis is refused.

    Scope of the seal (same honest boundary as ADR-0008): this refuses re-locking *this object*.
    It cannot stop a study that willfully reconstructs a hypothesis — e.g. ``dataclasses.replace``
    to clear the lock fields, then re-lock different content — any more than the runners can stop
    a builder that reflects into their frame; both need process isolation, which is out of scope.
    What the engine *does* guarantee is that whatever is ultimately confirmed has a proof binding
    its content at an attested time before confirmation. So a re-locked copy is simply a new
    pre-registration with a new, later timestamp — visible as such, not a silent override.
    """
    if hypothesis.locked:
        raise PreRegistrationError(
            f"hypothesis {hypothesis.hypothesis_id!r} is already locked; re-locking is forbidden"
        )
    digest = canonical_hypothesis_digest(hypothesis)
    proof = authority.stamp(digest, instant=instant)
    verified = authority.verify(digest, proof)  # fail loud here if the authority is misbehaving
    return replace(hypothesis, locked_at=verified.instant.isoformat(), timestamp_proof=proof)


def verify_preregistration(
    hypothesis: Hypothesis, *, authority: TimestampAuthority
) -> VerifiedTimestamp:
    """Verify a hypothesis is genuinely pre-registered: present, content-bound, time-attested.

    Raises :class:`PreRegistrationError` if the hypothesis is not locked, the proof does not
    bind the *current* content digest, the attested instant is not a timezone-aware time, or the
    self-reported ``locked_at`` disagrees with the authority's attested instant.
    """
    if not hypothesis.locked:
        raise PreRegistrationError(
            f"hypothesis {hypothesis.hypothesis_id!r} is not locked; confirm is forbidden "
            "before pre-registration (METHODOLOGY §3 / GOVERNANCE §2)"
        )
    assert hypothesis.timestamp_proof is not None  # .locked guarantees this; for the type checker
    digest = canonical_hypothesis_digest(hypothesis)
    verified = authority.verify(digest, hypothesis.timestamp_proof)
    if verified.digest != digest:
        raise PreRegistrationError(
            f"authority attested digest {verified.digest!r} but the hypothesis content hashes to "
            f"{digest!r} — the proof does not cover this hypothesis"
        )
    # The displayed lock time must match the attested one, so a study cannot show a time the
    # authority did not vouch for.
    try:
        claimed = _dt.datetime.fromisoformat(hypothesis.locked_at or "")
    except ValueError:
        raise PreRegistrationError(
            f"locked_at {hypothesis.locked_at!r} is not an ISO-8601 timestamp"
        ) from None
    if _require_aware_utc(claimed, "locked_at") != verified.instant:
        raise PreRegistrationError(
            f"locked_at {hypothesis.locked_at!r} disagrees with the authority-attested instant "
            f"{verified.instant.isoformat()!r}"
        )
    return verified


def require_preregistered(
    hypothesis: Hypothesis,
    *,
    authority: TimestampAuthority,
    not_after: _dt.datetime,
) -> VerifiedTimestamp:
    """Gate a confirmatory step: the hypothesis must be verifiably locked *before* ``not_after``.

    ``not_after`` is the confirmation moment (a runner captures it at entry). A lock whose
    attested instant is not strictly earlier is rejected — you cannot pre-register a hypothesis
    after the result that would confirm it is already in hand.
    """
    not_after = _require_aware_utc(not_after, "not_after")
    verified = verify_preregistration(hypothesis, authority=authority)
    if not verified.instant < not_after:
        raise PreRegistrationError(
            f"hypothesis {hypothesis.hypothesis_id!r} was locked at "
            f"{verified.instant.isoformat()!r}, not strictly before the confirmation moment "
            f"{not_after.isoformat()!r} — a lock must precede confirmation (GOVERNANCE §2)"
        )
    return verified
