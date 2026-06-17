"""External-claims source interface — optional, and quarantined from the baseline.

If a dataset ships claims asserted by some external authority (relationships, labels, a
taxonomy, mappings), an adapter exposes them through :class:`ExternalClaimsSource`. The
engine converts each :class:`ClaimRecord` into a typed, falsifiable hypothesis and tests it
against the baseline — which is kept blind to these claims (Firewall A).

This interface is *structurally separable*: the baseline pipeline never receives it, so the
baseline can be produced with claims withheld. Pure-discovery datasets omit it entirely.
Access to a claims source while claim-blindness is in force raises ``FirewallViolation``
(see :mod:`assay_engine.methodology.firewalls`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from assay_engine._canonical import hash_value
from assay_engine._frozen import freeze_mapping


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    """One external, expert-asserted claim about the data — a falsifiable assertion.

    The engine treats this as a *hypothesis source*, never as ground truth. ``subject`` and
    ``referents`` name the units the claim is about; ``assertion`` describes what is claimed
    in a typed, machine-readable way; ``provenance`` records who asserted it and where from.
    """

    claim_id: str
    subject: str
    referents: tuple[str, ...]
    assertion: Mapping[str, Any]
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "assertion", freeze_mapping(self.assertion))
        object.__setattr__(self, "provenance", freeze_mapping(self.provenance))


def claim_set_fingerprint(claims: Iterable[ClaimRecord]) -> str:
    """The canonical, engine-reproducible content hash of a claim set (pass 3, #F-001).

    This is THE fingerprint scheme the engine uses as authoritative provenance. An
    :class:`ExternalClaimsSource` must return exactly this from ``claim_fingerprint()`` over the
    same records ``claims()`` yields — the engine recomputes it over the materialized claims and
    refuses to adjudicate on a mismatch, so the source's fingerprint is a real content
    commitment (a source cannot attest to one claim set and adjudicate another) rather than an
    unverifiable self-report in an arbitrary scheme. The hash is order-sensitive and covers
    every field of every record.
    """
    return hash_value(
        [
            {
                "claim_id": c.claim_id,
                "subject": c.subject,
                "referents": list(c.referents),
                "assertion": c.assertion,
                "provenance": c.provenance,
            }
            for c in claims
        ]
    )


class ExternalClaimsSource(Protocol):
    """Adapter-provided access to a dataset's external claims (adjudication mode only)."""

    def claims(self) -> Iterable[ClaimRecord]:
        """Yield every external claim to be adjudicated against the blind baseline."""
        ...

    def claim_fingerprint(self) -> str:
        """Content commitment to the claim set, for provenance and pre-registration.

        Must equal :func:`claim_set_fingerprint` computed over the records ``claims()`` yields.
        The engine recomputes this canonical fingerprint over the materialized claims and
        raises ``FirewallViolation`` if the source's self-report disagrees (pass 3, #F-001), so
        ``claim_fingerprint()`` is an enforced commitment, not an unverified label. Use
        :func:`claim_set_fingerprint` to implement it.
        """
        ...
