"""Append-only provenance trail (GOVERNANCE §3, W3C PROV-DM style).

Every action a study takes is recorded, in order, before the next executes: ingestion, the
blind baseline build, each discovered/locked hypothesis, every gate decision, each verdict,
the source scorecard, the final report. The trail is the spine of reproducibility and of the
independence claim — "no step can be retroactively removed or reordered" (GOVERNANCE §3).

The trail enforces that structurally, not by promise:

- **Append-only.** Entries are added through :meth:`ProvenanceTrail.record` only; there is no
  remove/edit/reorder API and the exposed view is an immutable tuple of frozen entries.
- **Chained.** Each entry carries ``prev_hash`` and an ``entry_hash`` over
  ``(prev_hash, seq, kind, summary, payload, timestamp)`` using the engine's one type-faithful
  serializer (:mod:`assay_engine._canonical`), rooted at a fixed genesis.

Integrity — honest scope, two tiers:

- **Unkeyed (default).** The chain is plain SHA-256. It is *tamper-evident against naive
  tampering and accidental corruption*: editing one entry without recomputing downstream
  hashes, reordering, or deleting an entry is caught by :func:`verify_records`. It is **not**
  forgery-proof: a motivated party who controls the serialized bytes can edit a payload and
  recompute the whole genesis-rooted chain, and the result verifies. Unkeyed integrity buys
  "is this a valid chain?", not "is this *the* chain the engine produced."
- **Keyed (``secret=...``).** Pass an on-box secret (as pre-registration does, ADR-0009) and
  the chain is HMAC-SHA256. The head cannot be recomputed without the secret, so a downstream
  store cannot silently rewrite history and re-seal it; :func:`verify_records` must be given
  the same secret. This is local tamper-*resistance*; non-repudiable third-party attestation of
  the trail's time remains the same pluggable concern as pre-registration, out of scope here.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from assay_engine._canonical import canonical_json
from assay_engine._frozen import freeze_mapping

_UTC = _dt.timezone.utc
_GENESIS = "assay-provenance:v1:genesis"

Clock = Callable[[], _dt.datetime]


class ProvenanceError(RuntimeError):
    """The provenance trail is inconsistent (a broken chain) or an entry cannot be recorded."""


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    """One immutable, chained record of a single action."""

    seq: int
    kind: str
    summary: str
    payload: Mapping[str, Any]
    timestamp: str  # ISO-8601 UTC
    prev_hash: str
    entry_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_mapping(self.payload))


def _digest(
    seq: int,
    kind: str,
    summary: str,
    payload: Mapping[str, Any],
    timestamp: str,
    prev_hash: str,
    secret: bytes | None,
) -> str:
    try:
        msg = canonical_json(
            ["assay-prov:v1", prev_hash, seq, kind, summary, dict(payload), timestamp]
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        # RecursionError (deeply nested payload) is a RuntimeError, not Value/TypeError — catch it
        # too so the entrypoints surface a typed ProvenanceError, never a raw exception (#89).
        raise ProvenanceError(
            f"provenance payload for {kind!r} cannot be serialized reproducibly ({exc}); "
            "record only JSON-native / hashable values of bounded depth"
        ) from None
    if secret is None:
        return hashlib.sha256(msg).hexdigest()
    return hmac.new(secret, msg, "sha256").hexdigest()


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_UTC)


class ProvenanceTrail:
    """An append-only, chained audit trail for one study run.

    ``secret`` (>= 16 bytes) keys the chain with HMAC so a serialized trail cannot be forged
    without it (see module docstring). ``clock`` injects the timestamp source (deterministic
    tests); it must return a timezone-aware ``datetime``.
    """

    def __init__(self, *, secret: bytes | None = None, clock: Clock | None = None) -> None:
        if secret is not None and (not isinstance(secret, (bytes, bytearray)) or len(secret) < 16):
            raise ValueError("provenance secret must be >= 16 bytes of key material")
        self._entries: list[ProvenanceEntry] = []
        self._secret: bytes | None = bytes(secret) if secret is not None else None
        self._clock: Clock = clock or _utc_now

    def record(self, kind: str, summary: str, **payload: Any) -> ProvenanceEntry:
        """Append one entry. Returns it. The only way to add to the trail."""
        if not kind:
            raise ProvenanceError("provenance entry kind must be non-empty")
        seq = len(self._entries)
        prev_hash = self._entries[-1].entry_hash if self._entries else _GENESIS
        try:
            instant = self._clock()
        except Exception as exc:  # noqa: BLE001 — the clock is an injected dependency
            raise ProvenanceError(f"provenance clock raised: {exc}") from None
        if not isinstance(instant, _dt.datetime):
            raise ProvenanceError("provenance clock must return a datetime")
        try:
            # utcoffset()/astimezone()/isoformat() can raise on a hostile datetime subclass or an
            # out-of-range value — keep the typed-error contract (#96).
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise ProvenanceError("provenance clock must return a timezone-aware datetime")
            timestamp = instant.astimezone(_UTC).isoformat()
        except ProvenanceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvenanceError(f"provenance timestamp could not be normalized: {exc}") from None
        entry_hash = _digest(seq, kind, summary, payload, timestamp, prev_hash, self._secret)
        try:
            entry = ProvenanceEntry(
                seq=seq,
                kind=kind,
                summary=summary,
                payload=payload,
                timestamp=timestamp,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
        except (ValueError, TypeError, RecursionError) as exc:
            raise ProvenanceError(
                f"provenance entry for {kind!r} could not be frozen ({exc})"
            ) from None
        self._entries.append(entry)
        return entry

    def as_recorder(self) -> Callable[[Any], None]:
        """A :data:`gates.ProvenanceRecorder` bound to this trail (records GateDecisions).

        Reads each attribute exactly once and defensively, so a booby-trapped decision object
        (a property that raises) surfaces a typed ``ProvenanceError`` rather than a raw error.
        """

        def _record(decision: Any) -> None:
            try:
                gate = getattr(decision, "gate", None)
                approved = bool(getattr(decision, "approved", False))
                reason = getattr(decision, "reason", "")
                evidence = dict(getattr(decision, "evidence", {}) or {})
            except Exception as exc:  # noqa: BLE001 — the decision is on the trust boundary
                raise ProvenanceError(
                    f"could not read gate decision for provenance: {exc}"
                ) from None
            self.record(
                "gate",
                f"gate {gate!r}: {'approved' if approved else 'blocked'}",
                gate=gate,
                approved=approved,
                reason=reason,
                evidence=evidence,
            )

        return _record

    @property
    def entries(self) -> tuple[ProvenanceEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        """The current chain head (last entry_hash, or the genesis if empty)."""
        return self._entries[-1].entry_hash if self._entries else _GENESIS

    def __len__(self) -> int:
        return len(self._entries)

    def verify(self) -> None:
        """Recompute the chain; raise :class:`ProvenanceError` on any inconsistency."""
        verify_records(self._entries, secret=self._secret)

    def to_records(self) -> tuple[dict[str, Any], ...]:
        """Serialize to plain dicts (for a persistent store); re-checkable via :func:`verify_records`."""
        return tuple(
            {
                "seq": e.seq,
                "kind": e.kind,
                "summary": e.summary,
                "payload": dict(e.payload),
                "timestamp": e.timestamp,
                "prev_hash": e.prev_hash,
                "entry_hash": e.entry_hash,
            }
            for e in self._entries
        )


def verify_records(
    entries: "list[ProvenanceEntry] | tuple[ProvenanceEntry, ...]",
    *,
    secret: bytes | None = None,
) -> None:
    """Verify a sequence of entries forms an intact chain (order, linkage, content).

    Pass the same ``secret`` the trail was keyed with; an unkeyed trail verifies with
    ``secret=None``. A keyed trail will not verify under the wrong/absent secret.
    """
    prev = _GENESIS
    for i, e in enumerate(entries):
        if e.seq != i:
            raise ProvenanceError(f"provenance entry {i} has seq {e.seq} (reordered or removed)")
        if e.prev_hash != prev:
            raise ProvenanceError(f"provenance entry {i} prev_hash breaks the chain")
        recomputed = _digest(e.seq, e.kind, e.summary, e.payload, e.timestamp, e.prev_hash, secret)
        if not hmac.compare_digest(recomputed, e.entry_hash):
            raise ProvenanceError(
                f"provenance entry {i} content was altered, or the wrong key was used (hash mismatch)"
            )
        prev = e.entry_hash


def from_records(
    records: "list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]",
    *,
    secret: bytes | None = None,
) -> tuple[ProvenanceEntry, ...]:
    """Rebuild entries from :meth:`ProvenanceTrail.to_records` output and verify the chain."""
    entries = tuple(
        ProvenanceEntry(
            seq=r["seq"],
            kind=r["kind"],
            summary=r["summary"],
            payload=r["payload"],
            timestamp=r["timestamp"],
            prev_hash=r["prev_hash"],
            entry_hash=r["entry_hash"],
        )
        for r in records
    )
    verify_records(entries, secret=secret)
    return entries
