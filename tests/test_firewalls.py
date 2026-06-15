"""Firewalls are enforced in code, not prose (ADR-0005). These tests are the enforcement."""

import pytest

from assay_engine.methodology.firewalls import (
    ClaimBlindGuard,
    DiscoverConfirmSplit,
    FirewallViolation,
)


def test_claim_blind_guard_blocks_access_while_sealed():
    guard = ClaimBlindGuard()
    claims = object()
    with guard.sealed():
        assert guard.is_sealed
        with pytest.raises(FirewallViolation):
            guard.access(claims)
    # released after the block — adjudication may now read claims
    assert guard.access(claims) is claims


def test_claim_blind_guard_restores_prior_state_on_nesting():
    guard = ClaimBlindGuard()
    with guard.sealed():
        with guard.sealed():
            assert guard.is_sealed
        assert guard.is_sealed  # inner exit must not unseal the outer block
    assert not guard.is_sealed


def test_split_rejects_overlapping_partitions():
    with pytest.raises(FirewallViolation):
        DiscoverConfirmSplit.from_partition({"a", "b"}, {"b", "c"})


def test_confirm_only_rejects_discovery_ids():
    split = DiscoverConfirmSplit.from_partition({"a", "b"}, {"c", "d"})
    with pytest.raises(FirewallViolation):
        split.assert_confirm_only({"a"})  # double-dipping on discovery data


def test_confirm_only_rejects_ids_outside_confirmation_partition():
    split = DiscoverConfirmSplit.from_partition({"a"}, {"c", "d"})
    with pytest.raises(FirewallViolation):
        split.assert_confirm_only({"z"})


def test_confirm_only_accepts_held_out_ids():
    split = DiscoverConfirmSplit.from_partition({"a", "b"}, {"c", "d"})
    split.assert_confirm_only({"c", "d"})  # no raise


def test_split_rejects_empty_confirmation_partition():
    # issue #5: a held-out split with nothing held out is invalid by construction
    with pytest.raises(FirewallViolation):
        DiscoverConfirmSplit.from_partition({"a"}, set())


def test_confirm_only_rejects_empty_evaluated_ids():
    # issue #5: a confirmatory test that evaluated zero held-out objects must not pass
    split = DiscoverConfirmSplit.from_partition({"a"}, {"c", "d"})
    with pytest.raises(FirewallViolation):
        split.assert_confirm_only(set())


def test_custodial_guard_holds_and_releases_claims():
    # issue #1: the guard can take custody of the claims source; release() raises while sealed
    claims = object()
    guard = ClaimBlindGuard(claims)
    with guard.sealed():
        with pytest.raises(FirewallViolation):
            guard.release()
    assert guard.release() is claims


def test_custodial_guard_without_source_raises_on_release():
    guard = ClaimBlindGuard()
    with pytest.raises(FirewallViolation):
        guard.release()
