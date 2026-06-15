"""The two firewalls, enforced as runtime primitives (ADR-0005, METHODOLOGY.md §2).

Both separations are enforced in code and exercised by tests — never asserted only in prose.

Firewall A — claim-blindness:
    The baseline must be built blind to external claims. :class:`ClaimBlindGuard` seals a
    claims source so that any attempt to read it while the guard is active raises
    :class:`FirewallViolation`. Baseline construction runs inside the guard; adjudication
    runs outside it.

Firewall B — discover/confirm separation:
    The data used to discover a hypothesis must not be the data used to confirm it.
    :class:`DiscoverConfirmSplit` holds disjoint discovery and confirmation id sets and
    refuses to confirm on any id the discovery phase touched.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator


class FirewallViolation(RuntimeError):
    """Raised when a methodological firewall is breached at runtime."""


class ClaimBlindGuard:
    """Firewall A. While sealed, ``access()`` raises — the baseline cannot read claims.

    Usage::

        guard = ClaimBlindGuard()
        with guard.sealed():
            corpus = parser.parse(source)      # baseline build — no claims reachable
            baseline = build_baseline(corpus, claim_guard=guard)
        claims = guard.access(claims_source)    # adjudication — guard released

    The baseline builder calls ``guard.access(...)`` defensively; if it ever does so inside
    the sealed block, the violation surfaces immediately instead of silently contaminating
    the reference.
    """

    def __init__(self) -> None:
        self._sealed = False

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    @contextmanager
    def sealed(self) -> Iterator["ClaimBlindGuard"]:
        prior = self._sealed
        self._sealed = True
        try:
            yield self
        finally:
            self._sealed = prior

    def access(self, claims_source: object) -> object:
        """Return ``claims_source`` only if the guard is not sealed; else raise."""
        if self._sealed:
            raise FirewallViolation(
                "Firewall A: external claims accessed during blind baseline construction"
            )
        return claims_source


@dataclass(frozen=True, slots=True)
class DiscoverConfirmSplit:
    """Firewall B. Disjoint discovery / confirmation id partitions for unit-level claims."""

    discovery_ids: frozenset[str]
    confirm_ids: frozenset[str]

    def __post_init__(self) -> None:
        overlap = self.discovery_ids & self.confirm_ids
        if overlap:
            raise FirewallViolation(
                f"Firewall B: discovery and confirmation partitions overlap on "
                f"{len(overlap)} id(s), e.g. {sorted(overlap)[:3]}"
            )

    @classmethod
    def from_partition(
        cls, discovery_ids: Iterable[str], confirm_ids: Iterable[str]
    ) -> "DiscoverConfirmSplit":
        return cls(frozenset(discovery_ids), frozenset(confirm_ids))

    def assert_confirm_only(self, ids: Iterable[str]) -> None:
        """Raise if any of ``ids`` was seen during discovery (i.e. would double-dip)."""
        ids = frozenset(ids)
        leaked = ids & self.discovery_ids
        if leaked:
            raise FirewallViolation(
                f"Firewall B: confirmatory test touched {len(leaked)} discovery id(s) — "
                f"double-dipping, e.g. {sorted(leaked)[:3]}"
            )
        unknown = ids - self.confirm_ids
        if unknown:
            raise FirewallViolation(
                f"Firewall B: confirmatory test used {len(unknown)} id(s) outside the "
                f"confirmation partition, e.g. {sorted(unknown)[:3]}"
            )
