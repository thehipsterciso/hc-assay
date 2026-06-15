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


class ExternalClaimsSource(Protocol):
    """Adapter-provided access to a dataset's external claims (adjudication mode only)."""

    def claims(self) -> Iterable[ClaimRecord]:
        """Yield every external claim to be adjudicated against the blind baseline."""
        ...

    def claim_fingerprint(self) -> str:
        """Stable content hash of the claim set, for provenance and pre-registration."""
        ...
