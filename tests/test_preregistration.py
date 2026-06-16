"""Pre-registration integrity (METHODOLOGY §3, GOVERNANCE §2, ADR-0009).

These tests ARE the guarantee: the lock must bind the hypothesis content, attest a verifiable
time, and precede confirmation — a hand-set proof string, a post-lock content swap, a forged
proof, or a lock dated after the confirmation moment must all be refused.
"""

import datetime as _dt
from dataclasses import replace

import pytest

from assay_engine.methodology.confirm import confirm_whole_corpus
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import (
    LocalHmacAuthority,
    PreRegistrationError,
    canonical_hypothesis_digest,
    lock_hypothesis,
    require_preregistered,
    verify_preregistration,
)

_UTC = _dt.timezone.utc


def _auth(secret=b"preregistration-unit-test-key-01"):
    return LocalHmacAuthority(secret)


def _unlocked(hid="H1", **over):
    base = dict(
        hypothesis_id=hid,
        statement="pattern",
        kind=HypothesisKind.UNIT_LEVEL,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
    )
    base.update(over)
    return Hypothesis(**base)


def _past():
    return _dt.datetime.now(tz=_UTC) - _dt.timedelta(hours=1)


# ---- the content digest ----


def test_digest_covers_content_and_id_but_not_lock_fields():
    h = _unlocked()
    # hypothesis_id IS bound (#80): it is the verdict's attribution key, so a swap must be caught
    assert canonical_hypothesis_digest(h) != canonical_hypothesis_digest(
        replace(h, hypothesis_id="X")
    )
    # decision-bearing content changes the digest
    assert canonical_hypothesis_digest(h) != canonical_hypothesis_digest(
        replace(h, decision_rule="r2")
    )
    assert canonical_hypothesis_digest(h) != canonical_hypothesis_digest(replace(h, statement="s2"))
    assert canonical_hypothesis_digest(h) != canonical_hypothesis_digest(
        replace(h, predicted_direction="greater")
    )


def test_digest_is_stable_and_does_not_change_when_locked():
    # locking adds locked_at/timestamp_proof, which are EXCLUDED from the digest — so the digest
    # the runner recomputes on the locked hypothesis equals the one the proof was issued over.
    h = _unlocked()
    d_before = canonical_hypothesis_digest(h)
    locked = lock_hypothesis(h, authority=_auth(), instant=_past())
    assert canonical_hypothesis_digest(locked) == d_before


# ---- lock_hypothesis + verify round-trip ----


def test_lock_then_verify_roundtrip():
    auth = _auth()
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=_past())
    assert locked.locked
    vt = verify_preregistration(locked, authority=auth)
    assert vt.authority == "local-hmac"
    assert vt.digest == canonical_hypothesis_digest(locked)
    assert vt.instant.tzinfo is not None


def test_relocking_is_forbidden():
    auth = _auth()
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=_past())
    with pytest.raises(PreRegistrationError, match="already locked"):
        lock_hypothesis(locked, authority=auth, instant=_past())


# ---- the breaks pre-registration must catch ----


def test_unlocked_hypothesis_is_rejected():
    with pytest.raises(PreRegistrationError, match="not locked"):
        verify_preregistration(_unlocked(), authority=_auth())


def test_hand_set_sentinel_proof_is_rejected():
    # the exact footgun this module closes: a presence-only "lock" string must NOT verify
    fake = _unlocked(locked_at="2026-06-16T00:00:00+00:00", timestamp_proof="rfc3161:demo")
    assert fake.locked  # passes the cheap presence predicate ...
    with pytest.raises(PreRegistrationError):  # ... but fails real verification
        verify_preregistration(fake, authority=_auth())


def test_content_swapped_after_locking_is_rejected():
    auth = _auth()
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=_past())
    # keep the proof but change the decision rule — the proof no longer binds the content
    tampered = replace(locked, decision_rule="a different, post-hoc decision rule")
    with pytest.raises(PreRegistrationError, match="does not bind|does not cover"):
        verify_preregistration(tampered, authority=auth)


def test_hypothesis_id_swapped_after_locking_is_rejected():
    # #80: the id is bound, so a post-lock id swap (which would misattribute the verdict) fails
    auth = _auth()
    locked = lock_hypothesis(_unlocked(hid="H_original"), authority=auth, instant=_past())
    swapped = replace(locked, hypothesis_id="H_DIFFERENT")
    with pytest.raises(PreRegistrationError):
        verify_preregistration(swapped, authority=auth)


def test_non_ascii_mac_field_raises_preregistration_error_not_typeerror():
    # #81: a non-ASCII MAC must be a controlled PreRegistrationError, not a leaked TypeError
    auth = _auth()
    bad = _unlocked(
        locked_at="2026-06-16T00:00:00+00:00",
        timestamp_proof="local-hmac:v1:2026-06-16T00:00:00+00:00|\udcffmac",
    )
    with pytest.raises(PreRegistrationError):
        verify_preregistration(bad, authority=auth)


def test_non_finite_param_raises_preregistration_error():
    # #82: a non-finite float in params must surface as a typed firewall error, not a ValueError
    auth = _auth()
    h = _unlocked(params={"alpha": float("nan")})
    with pytest.raises(PreRegistrationError):
        canonical_hypothesis_digest(h)
    with pytest.raises(PreRegistrationError):
        lock_hypothesis(h, authority=auth, instant=_past())


def test_proof_from_another_authority_is_rejected():
    locked = lock_hypothesis(
        _unlocked(), authority=_auth(b"secret-aaaaaaaaaaaaaaaaaaaaaaa1"), instant=_past()
    )
    other = _auth(b"secret-bbbbbbbbbbbbbbbbbbbbbbb2")  # different key
    with pytest.raises(PreRegistrationError):
        verify_preregistration(locked, authority=other)


def test_tampered_locked_at_disagrees_with_attested_instant():
    auth = _auth()
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=_past())
    # change the displayed lock time but keep the (now-inconsistent) proof
    spoofed = replace(locked, locked_at="2000-01-01T00:00:00+00:00")
    with pytest.raises(PreRegistrationError):
        verify_preregistration(spoofed, authority=auth)


def test_malformed_proof_is_rejected_not_crashed():
    for bad in [
        "",
        "garbage",
        "local-hmac:v1:",
        "local-hmac:v1:not-a-time|abcd",
        "local-hmac:v1:2026-06-16T00:00:00+00:00",
        "wrong-prefix:2026|ab",
    ]:
        with pytest.raises(PreRegistrationError):
            verify_preregistration(
                _unlocked(timestamp_proof=bad, locked_at="2026-06-16T00:00:00+00:00"),
                authority=_auth(),
            )


# ---- lock-before-confirm ordering ----


def test_require_preregistered_accepts_lock_before_confirmation():
    auth = _auth()
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=_past())
    vt = require_preregistered(locked, authority=auth, not_after=_dt.datetime.now(tz=_UTC))
    assert vt.instant < _dt.datetime.now(tz=_UTC)


def test_require_preregistered_rejects_lock_after_confirmation():
    auth = _auth()
    future = _dt.datetime.now(tz=_UTC) + _dt.timedelta(hours=1)
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=future)
    with pytest.raises(PreRegistrationError, match="precede confirmation|strictly before"):
        require_preregistered(locked, authority=auth, not_after=_dt.datetime.now(tz=_UTC))


def test_require_preregistered_rejects_lock_equal_to_confirmation():
    auth = _auth()
    when = _dt.datetime.now(tz=_UTC) - _dt.timedelta(hours=1)
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=when)
    with pytest.raises(PreRegistrationError):  # not strictly before
        require_preregistered(locked, authority=auth, not_after=when)


# ---- authority hygiene ----


def test_naive_instants_are_rejected():
    auth = _auth()
    with pytest.raises(PreRegistrationError, match="timezone-aware"):
        auth.stamp("deadbeef", instant=_dt.datetime(2026, 6, 16, 0, 0, 0))  # naive
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=_past())
    with pytest.raises(PreRegistrationError, match="timezone-aware"):
        require_preregistered(locked, authority=auth, not_after=_dt.datetime(2026, 6, 16))  # naive


def test_weak_secret_is_refused():
    with pytest.raises(ValueError, match="16 bytes"):
        LocalHmacAuthority(b"too-short")


def test_confirm_primitive_optional_authority_rejects_fake_lock():
    # #84: a direct confirm caller can opt into real verification by passing authority=
    auth = _auth()
    fake = Hypothesis(
        hypothesis_id="H1",
        statement="s",
        kind=HypothesisKind.WHOLE_CORPUS,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
        predicted_direction="greater",
        locked_at="2026-06-16T00:00:00+00:00",
        timestamp_proof="rfc3161:demo",  # sentinel
    )
    null = [0.05 + 0.001 * i for i in range(50)]
    # with authority: the fake (presence-only) lock is refused
    with pytest.raises(PreRegistrationError):
        confirm_whole_corpus(fake, observed=1.0, null_distribution=null, alpha=0.05, authority=auth)
    # a genuinely locked hypothesis with the same content passes the gate (verdict is produced)
    real = lock_hypothesis(
        replace(fake, locked_at=None, timestamp_proof=None), authority=auth, instant=_past()
    )
    v = confirm_whole_corpus(real, observed=1.0, null_distribution=null, alpha=0.05, authority=auth)
    assert v.hypothesis_id == "H1"


def test_non_utc_lock_instant_is_normalized():
    auth = _auth()
    plus5 = _dt.timezone(_dt.timedelta(hours=5))
    when = _dt.datetime.now(tz=plus5) - _dt.timedelta(hours=1)
    locked = lock_hypothesis(_unlocked(), authority=auth, instant=when)
    vt = verify_preregistration(locked, authority=auth)
    assert vt.instant.utcoffset() == _dt.timedelta(0)  # normalized to UTC
    assert vt.instant == when  # same instant, different representation
