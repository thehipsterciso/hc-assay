"""The two firewalls, enforced as runtime primitives (ADR-0005, METHODOLOGY.md §2).

Both separations are enforced in code and exercised by tests — never asserted only in prose.

Firewall A — claim-blindness:
    The baseline must be built blind to external claims. The *structural* guarantee is that
    the baseline builder is never handed an ``ExternalClaimsSource`` (its ``build`` signature
    takes only a ``Corpus``) and that ``StudyDefinition`` refuses a claims source outside
    adjudication mode. On top of that, :class:`ClaimBlindGuard` gives the claims source
    *custody*: hand the source to the guard, and the only way to obtain it is
    ``release()``/``access()``, which raise while the guard is sealed. Baseline construction
    runs inside ``sealed()``; adjudication runs after it.

    Caveat (audit pass 1, issue #1): the guard cannot police a baseline builder that ignores
    it and reads external judgments smuggled into ``Corpus`` metadata/relations — that path
    is closed by the adapter contract (see schema.py), not by this guard. The guard is
    custodial defense-in-depth over the type-level separation, not the sole barrier.

Firewall B — discover/confirm separation:
    The data used to discover a hypothesis must not be the data used to confirm it.
    :class:`DiscoverConfirmSplit` holds disjoint, non-empty discovery and confirmation id
    sets and refuses to confirm on any id the discovery phase touched (or on an empty set).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generic, Iterable, Iterator, TypeVar

C = TypeVar("C")


class FirewallViolation(RuntimeError):
    """Raised when a methodological firewall is breached at runtime."""


class ClaimBlindGuard(Generic[C]):
    """Firewall A. While sealed, the held claims source is unreachable.

    Custodial usage (preferred) — the guard owns the source, so the baseline pipeline holds
    the guard rather than the source and cannot read claims while sealed::

        guard = ClaimBlindGuard(claims_source)
        with guard.sealed():
            corpus = parser.parse(source)            # baseline build — claims unreachable
            baseline = build_baseline(corpus, claim_guard=guard)
        claims = guard.release()                      # adjudication — guard released

    ``access(obj)`` remains for defensive checks at call sites that hold a reference directly:
    it returns ``obj`` when unsealed and raises while sealed.
    """

    def __init__(self, claims_source: C | None = None) -> None:
        self._sealed = False
        self._claims_source = claims_source

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    @contextmanager
    def sealed(self) -> Iterator["ClaimBlindGuard[C]"]:
        prior = self._sealed
        self._sealed = True
        try:
            yield self
        finally:
            self._sealed = prior

    def release(self) -> C:
        """Return the custodial claims source, or raise while sealed / if none was given."""
        if self._sealed:
            raise FirewallViolation(
                "Firewall A: external claims released during blind baseline construction"
            )
        if self._claims_source is None:
            raise FirewallViolation("Firewall A: no claims source is under this guard's custody")
        return self._claims_source

    def access(self, claims_source: C) -> C:
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
        # An empty confirmation partition means there is nothing held out to confirm on; a
        # unit-level held-out split with no held-out object is invalid by construction. The
        # genuine no-holdout case must use the whole-corpus null path (audit pass 1, issue #5).
        if not self.confirm_ids:
            raise FirewallViolation(
                "Firewall B: confirmation partition is empty — a unit-level held-out split "
                "must hold out at least one object (use whole-corpus confirmation otherwise)"
            )

    @classmethod
    def from_partition(
        cls, discovery_ids: Iterable[str], confirm_ids: Iterable[str]
    ) -> "DiscoverConfirmSplit":
        return cls(frozenset(discovery_ids), frozenset(confirm_ids))

    def assert_confirm_only(self, ids: Iterable[str]) -> None:
        """Raise if ``ids`` is empty or any of it was seen during discovery (double-dip)."""
        ids = frozenset(ids)
        if not ids:
            raise FirewallViolation(
                "Firewall B: confirmatory test evaluated zero held-out objects — a verdict "
                "cannot be produced from an empty confirmation set (audit pass 1, issue #5)"
            )
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
