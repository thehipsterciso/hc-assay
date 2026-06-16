"""Targeted tests for methodology/security branches the happy-path suite left uncovered."""

from __future__ import annotations

import datetime as _dt
import decimal
import uuid
from dataclasses import replace

import pytest

from assay_engine._canonical import hash_value
from assay_engine._local import is_loopback_host
from assay_engine.methodology.hypothesis import Hypothesis, HypothesisKind, HypothesisOrigin
from assay_engine.methodology.preregistration import (
    LocalHmacAuthority,
    PreRegistrationError,
    VerifiedTimestamp,
    lock_hypothesis,
    verify_preregistration,
)
from assay_engine.registry import clear_registry, get_study, register_study

_UTC = _dt.timezone.utc


# ---- _canonical type-faithfulness for set / Decimal / UUID (the module's reason to exist) ----


def test_hash_value_type_faithful_set_decimal_uuid():
    assert hash_value({1, 2, 3}) == hash_value({3, 2, 1})  # set order-independent
    assert hash_value({1, 2}) != hash_value([1, 2])  # set != list
    assert hash_value(decimal.Decimal("1.0")) != hash_value("1.0")  # Decimal != its str
    assert hash_value(decimal.Decimal("1.0")) != hash_value(1.0)  # Decimal != float
    u = uuid.UUID(int=0)
    assert hash_value(u) != hash_value(str(u))  # UUID != its str
    assert hash_value(u) == hash_value(uuid.UUID(int=0))  # stable


# ---- _local loopback micro-branches ----


def test_is_loopback_host_empty_and_none():
    assert is_loopback_host("") is False
    assert is_loopback_host(None) is False  # type: ignore[arg-type]


# ---- pre-registration verify-side guards (fake/colluding authority, bad timestamps) ----


def _locked():
    auth = LocalHmacAuthority(b"coverage-test-secret-key-00000001")
    h = Hypothesis(
        hypothesis_id="H1",
        statement="s",
        kind=HypothesisKind.UNIT_LEVEL,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
    )
    return auth, lock_hypothesis(
        h, authority=auth, instant=_dt.datetime.now(_UTC) - _dt.timedelta(hours=1)
    )


def test_authority_attesting_a_different_digest_is_rejected():
    _real, locked = _locked()

    class LyingAuthority:
        def verify(self, digest, proof):
            # returns a VerifiedTimestamp for a DIFFERENT digest than the hypothesis hashes to
            return VerifiedTimestamp(
                instant=_dt.datetime.now(_UTC) - _dt.timedelta(hours=1),
                authority="liar",
                digest="0" * 64,
            )

    with pytest.raises(PreRegistrationError, match="does not cover|attested digest"):
        verify_preregistration(locked, authority=LyingAuthority())


def test_locked_at_not_iso_is_rejected():
    auth, locked = _locked()
    spoofed = replace(locked, locked_at="not-a-timestamp")
    with pytest.raises(PreRegistrationError):
        verify_preregistration(spoofed, authority=auth)


def test_proof_instant_not_iso_is_rejected():
    auth, _ = _locked()
    bad = Hypothesis(
        hypothesis_id="H1",
        statement="s",
        kind=HypothesisKind.UNIT_LEVEL,
        origin=HypothesisOrigin.DISCOVERY,
        test_name="t",
        decision_rule="r",
        locked_at="2026-06-16T00:00:00+00:00",
        timestamp_proof="local-hmac:v1:not-a-time|" + "0" * 64,
    )
    with pytest.raises(PreRegistrationError):
        verify_preregistration(bad, authority=auth)


# ---- registry negative paths ----


def test_registry_unknown_and_duplicate():
    clear_registry()
    with pytest.raises(KeyError, match="no study registered"):
        get_study("nope")
    register_study("s", lambda: None)  # type: ignore[arg-type,return-value]
    with pytest.raises(ValueError, match="already registered"):
        register_study("s", lambda: None)  # type: ignore[arg-type,return-value]
    clear_registry()
