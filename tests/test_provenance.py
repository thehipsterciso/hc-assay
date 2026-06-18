"""Append-only provenance trail (GOVERNANCE §3, ADR-0010) + the hardening regressions."""

from __future__ import annotations

import datetime as _dt

import pytest

from assay_engine.provenance import (
    ProvenanceError,
    ProvenanceTrail,
    from_records,
)

_UTC = _dt.timezone.utc


def _fixed_clock():
    t = _dt.datetime(2026, 6, 16, 12, 0, 0, tzinfo=_UTC)
    return lambda: t


# ---- append-only + chain integrity ----


def test_records_chain_and_verify():
    t = ProvenanceTrail()
    t.record("a", "first", x=1)
    t.record("b", "second", y=[1, 2])
    t.verify()
    assert len(t) == 2 and t.entries[0].prev_hash != t.entries[1].prev_hash


def test_from_records_raises_typed_error_on_malformed_record():
    # #G-012: a record missing a required field must raise the typed ProvenanceError (so a caller
    # catching it to handle a corrupt/incompatible trail covers this), not a raw KeyError.
    good = ProvenanceTrail()
    good.record("a", "first", x=1)
    records = list(good.to_records())
    del records[0]["summary"]  # corrupt the record
    with pytest.raises(ProvenanceError, match="missing field"):
        from_records(records)


def test_entries_view_is_immutable_tuple():
    t = ProvenanceTrail()
    t.record("a", "x")
    assert isinstance(t.entries, tuple)
    with pytest.raises((TypeError, AttributeError)):
        t.entries[0] = None  # type: ignore[index]


def test_naive_tamper_is_detected_unkeyed():
    t = ProvenanceTrail(clock=_fixed_clock())
    t.record("a", "one")
    t.record("verdict", "H1: SUPPORTED", label="SUPPORTED")
    recs = list(t.to_records())
    recs[1] = {**recs[1], "payload": {"label": "CONTRADICTED"}}  # edit, do NOT recompute hash
    with pytest.raises(ProvenanceError):
        from_records(recs)
    # reorder/delete
    with pytest.raises(ProvenanceError):
        from_records(recs[:1] + recs[2:] if len(recs) > 2 else recs[1:])


# ---- #88: keyed (HMAC) trail is forgery-resistant; unkeyed is honestly only naive-evident ----


def test_keyed_trail_cannot_be_reforged_without_secret():
    secret = b"provenance-seal-secret-0123456789"
    t = ProvenanceTrail(secret=secret, clock=_fixed_clock())
    t.record("verdict", "H1: SUPPORTED", label="SUPPORTED")
    recs = list(t.to_records())
    # a forger edits the payload and recomputes the chain — but WITHOUT the secret, using the
    # unkeyed path — the keyed verify rejects it.
    forged = from_records  # alias
    tampered = [{**recs[0], "payload": {"label": "CONTRADICTED"}}]
    # recompute as an UNKEYED chain (forger has no secret):
    rebuilt = ProvenanceTrail(clock=_fixed_clock())
    rebuilt.record("verdict", "H1: CONTRADICTED", label="CONTRADICTED")
    forged_recs = rebuilt.to_records()
    with pytest.raises(ProvenanceError):
        forged(forged_recs, secret=secret)  # does not verify under the real key
    # the legitimate keyed trail verifies with the secret, and NOT without it
    assert from_records(recs, secret=secret)
    with pytest.raises(ProvenanceError):
        from_records(recs)  # unkeyed verify of a keyed trail fails
    _ = tampered


def test_weak_secret_refused():
    with pytest.raises(ValueError, match="16 bytes"):
        ProvenanceTrail(secret=b"short")


# ---- #89/#90: typed errors, never raw leaks ----


def test_deeply_nested_payload_raises_provenance_error():
    payload: dict = {}
    cur = payload
    for _ in range(5000):
        cur["n"] = {}
        cur = cur["n"]
    t = ProvenanceTrail()
    with pytest.raises(ProvenanceError):
        t.record("deep", "nested", tree=payload)


def test_non_finite_payload_raises_provenance_error():
    t = ProvenanceTrail()
    with pytest.raises(ProvenanceError):
        t.record("bad", "nan", v=float("nan"))


def test_non_datetime_clock_raises_provenance_error():
    t = ProvenanceTrail(clock=lambda: "not-a-datetime")  # type: ignore[arg-type,return-value]
    with pytest.raises(ProvenanceError):
        t.record("a", "x")


def test_naive_datetime_clock_raises_provenance_error():
    t = ProvenanceTrail(clock=lambda: _dt.datetime(2026, 6, 16, 12, 0, 0))  # naive
    with pytest.raises(ProvenanceError):
        t.record("a", "x")


def test_clock_that_raises_is_typed():
    # #96: a clock that raises must surface ProvenanceError, not the raw exception
    def boom() -> _dt.datetime:
        raise OverflowError("boom")

    with pytest.raises(ProvenanceError):
        ProvenanceTrail(clock=boom).record("a", "x")


def test_datetime_whose_isoformat_raises_is_typed():
    # #96: a hostile datetime whose normalization raises must still be ProvenanceError
    class BadDT(_dt.datetime):
        def isoformat(self, *a, **k):  # type: ignore[override]
            raise ValueError("nope")

    bad = BadDT(2026, 6, 16, 12, 0, 0, tzinfo=_UTC)
    with pytest.raises(ProvenanceError):
        ProvenanceTrail(clock=lambda: bad).record("a", "x")


# ---- #91: as_recorder hardened against a hostile decision object ----


def test_as_recorder_handles_missing_attrs_gracefully():
    t = ProvenanceTrail()
    t.as_recorder()(object())  # bare object -> safe defaults
    assert t.entries[-1].kind == "gate" and t.entries[-1].payload["approved"] is False


def test_as_recorder_raises_provenance_error_on_booby_trapped_decision():
    class Evil:
        gate = "g"

        @property
        def approved(self):  # property that raises
            raise ValueError("evil")

    t = ProvenanceTrail()
    with pytest.raises(ProvenanceError):
        t.as_recorder()(Evil())


# ---- determinism ----


def test_deterministic_hashes_under_fixed_clock():
    a = ProvenanceTrail(clock=_fixed_clock())
    a.record("k", "s", v={"b": 2, "a": 1})
    b = ProvenanceTrail(clock=_fixed_clock())
    b.record("k", "s", v={"a": 1, "b": 2})
    assert a.entries[0].entry_hash == b.entries[0].entry_hash


def test_record_is_thread_safe_under_concurrency():
    # #114: concurrent record() must not corrupt the seq/prev_hash chain.
    # A naive concurrency test is non-discriminating under the GIL — the read->append window is
    # too narrow to interleave. We inject a clock that sleeps INSIDE that window (record() reads
    # seq/prev_hash, then calls the clock, then appends), so an UNLOCKED record() would let
    # threads read the same seq and corrupt the chain. With the lock (held across the whole
    # _record_locked, clock included) threads serialize and the chain stays intact. Verified
    # discriminating: removing the lock makes this fail (duplicate seqs / broken chain).
    import threading
    import time

    def widening_clock():
        time.sleep(0.0005)  # widen the read->append window to force interleaving if unlocked
        return _dt.datetime.now(tz=_UTC)

    t = ProvenanceTrail(clock=widening_clock)
    n_threads, per = 8, 15
    barrier = threading.Barrier(n_threads)

    def worker(w):
        barrier.wait()  # release all threads at once → maximal contention in the window
        for i in range(per):
            t.record("k", f"w{w}-{i}", w=w, i=i)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(t) == n_threads * per
    t.verify()  # intact hash chain despite concurrent appends through a widened window
    assert [e.seq for e in t.entries] == list(range(n_threads * per))  # contiguous, no dupes/gaps


def test_record_rejects_set_payload_loudly_not_silent_verify_failure():
    # #P10-MO-1: a set/frozenset payload value is hashable (freeze accepts it) but does NOT survive
    # the to_records/from_records round-trip (unfreeze→sorted list→re-freeze→tuple), so verify
    # would SILENTLY fail on the rebuilt chain. Reject it loudly at record time instead.
    t = ProvenanceTrail()
    with pytest.raises(ProvenanceError, match="set/frozenset"):
        t.record("k", "summary", tags=frozenset({"a", "b", "c"}))
    with pytest.raises(ProvenanceError, match="set/frozenset"):
        t.record("k", "summary", nested={"inner": {1, 2, 3}})
    # a sorted list/tuple is the supported substitute and round-trips cleanly
    t.record("k", "summary", tags=["a", "b", "c"])
    from_records(t.to_records())  # verifies — no silent failure


def test_from_records_typed_error_on_non_mapping_payload():
    # #P10-MO-2: a record whose payload field is a non-mapping (list/str) must raise the module's
    # typed ProvenanceError, not a raw AttributeError from freeze_mapping calling .items() on it.
    t = ProvenanceTrail()
    t.record("k", "summary", x=1)
    recs = [dict(r) for r in t.to_records()]
    recs[0]["payload"] = ["not", "a", "mapping"]  # corrupt the payload type
    with pytest.raises(ProvenanceError):
        from_records(recs)
