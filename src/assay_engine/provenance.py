"""Append-only provenance trail (GOVERNANCE §3, W3C PROV-DM style).

Every action a study takes is recorded, in order, before the next executes: ingestion, the
blind baseline build, each discovered/locked hypothesis, every gate decision, each verdict,
the source scorecard, the final report. The trail is the spine of reproducibility and of the
independence claim — "no step can be retroactively removed or reordered" (GOVERNANCE §3).

The trail enforces that structurally, not by promise:

- **Append-only.** Entries are added through :meth:`ProvenanceTrail.record` only; there is no
  remove/edit/reorder API and the exposed view is an immutable tuple.
- **Tamper-evident.** Each entry carries ``prev_hash`` and an ``entry_hash`` over
  ``(prev_hash, seq, kind, summary, payload, timestamp)`` using the engine's one type-faithful
  hasher (:mod:`assay_engine._canonical`). The entries form a hash chain rooted at a fixed
  genesis, so removing, reordering, or editing any entry in a *persisted* trail is detected by
  :meth:`verify` (a downstream store cannot silently rewrite history).

Honest scope: an in-memory trail held by one process is as trustworthy as that process; the
hash chain's value is that a *serialized* trail (``to_records``) round-trips through
``from_records`` only if untouched, so an external store or reviewer can verify integrity.
Non-repudiable third-party attestation of the trail's *time* is the same pluggable concern as
pre-registration (see :mod:`assay_engine.methodology.preregistration`) and is out of scope here.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from assay_engine._canonical import canonical_json, hash_text
from assay_engine._frozen import freeze_mapping

_UTC = _dt.timezone.utc
_GENESIS = "assay-provenance:v1:genesis"

Clock = Callable[[], _dt.datetime]


class ProvenanceError(RuntimeError):
    """The provenance trail is inconsistent (a broken hash chain) or cannot be recorded."""


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    """One immutable, hash-chained record of a single action."""

    seq: int
    kind: str
    summary: str
    payload: Mapping[str, Any]
    timestamp: str  # ISO-8601 UTC
    prev_hash: str
    entry_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_mapping(self.payload))


def _digest(seq: int, kind: str, summary: str, payload: Mapping[str, Any],
            timestamp: str, prev_hash: str) -> str:
    try:
        return hash_text(canonical_json(
            ["assay-prov:v1", prev_hash, seq, kind, summary, dict(payload), timestamp]
        ))
    except (ValueError, TypeError) as exc:
        raise ProvenanceError(
            f"provenance payload for {kind!r} cannot be canonicalized reproducibly ({exc}); "
            "record only JSON-native / hashable values"
        ) from None


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_UTC)


class ProvenanceTrail:
    """An append-only, tamper-evident audit trail for one study run."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._entries: list[ProvenanceEntry] = []
        self._clock: Clock = clock or _utc_now

    def record(self, kind: str, summary: str, **payload: Any) -> ProvenanceEntry:
        """Append one entry. Returns it. The only way to add to the trail."""
        if not kind:
            raise ProvenanceError("provenance entry kind must be non-empty")
        seq = len(self._entries)
        prev_hash = self._entries[-1].entry_hash if self._entries else _GENESIS
        instant = self._clock()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ProvenanceError("provenance clock must return a timezone-aware datetime")
        timestamp = instant.astimezone(_UTC).isoformat()
        entry_hash = _digest(seq, kind, summary, payload, timestamp, prev_hash)
        entry = ProvenanceEntry(
            seq=seq, kind=kind, summary=summary, payload=payload,
            timestamp=timestamp, prev_hash=prev_hash, entry_hash=entry_hash,
        )
        self._entries.append(entry)
        return entry

    def as_recorder(self) -> Callable[[Any], None]:
        """A :data:`gates.ProvenanceRecorder` bound to this trail (records GateDecisions)."""
        def _record(decision: Any) -> None:
            self.record(
                "gate",
                f"gate {getattr(decision, 'gate', '?')!r}: "
                f"{'approved' if getattr(decision, 'approved', False) else 'blocked'}",
                gate=getattr(decision, "gate", None),
                approved=bool(getattr(decision, "approved", False)),
                reason=getattr(decision, "reason", ""),
                evidence=dict(getattr(decision, "evidence", {}) or {}),
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
        verify_records(self._entries)

    def to_records(self) -> tuple[dict[str, Any], ...]:
        """Serialize to plain dicts (for a persistent store); re-checkable via :func:`verify_records`."""
        return tuple(
            {
                "seq": e.seq, "kind": e.kind, "summary": e.summary,
                "payload": dict(e.payload), "timestamp": e.timestamp,
                "prev_hash": e.prev_hash, "entry_hash": e.entry_hash,
            }
            for e in self._entries
        )


def verify_records(entries: "list[ProvenanceEntry] | tuple[ProvenanceEntry, ...]") -> None:
    """Verify a sequence of entries forms an intact hash chain (order, linkage, content)."""
    prev = _GENESIS
    for i, e in enumerate(entries):
        if e.seq != i:
            raise ProvenanceError(f"provenance entry {i} has seq {e.seq} (reordered or removed)")
        if e.prev_hash != prev:
            raise ProvenanceError(f"provenance entry {i} prev_hash breaks the chain")
        recomputed = _digest(e.seq, e.kind, e.summary, e.payload, e.timestamp, e.prev_hash)
        if recomputed != e.entry_hash:
            raise ProvenanceError(f"provenance entry {i} content was altered (hash mismatch)")
        prev = e.entry_hash


def from_records(records: "list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]") -> tuple[ProvenanceEntry, ...]:
    """Rebuild entries from :meth:`ProvenanceTrail.to_records` output and verify the chain."""
    entries = tuple(
        ProvenanceEntry(
            seq=r["seq"], kind=r["kind"], summary=r["summary"], payload=r["payload"],
            timestamp=r["timestamp"], prev_hash=r["prev_hash"], entry_hash=r["entry_hash"],
        )
        for r in records
    )
    verify_records(entries)
    return entries
