"""Tiered reasoning seam (contract + stub).

Implementation note: lifted from the prior platform's tiered reasoning_client —
Tier 2 (local runtime, bulk) and Tier 3 (frontier model via fixed-cost subscription OAuth,
high-stakes). Subscription credentials are scrubbed from traces/logs; no metered API key is
ever read. The concrete client is wired when the infra is ported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


class StakesTier(Enum):
    BULK = "bulk"          # local model — high volume, low stakes
    HIGH_STAKES = "high"   # frontier model via fixed-cost subscription — gated, traced


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    prompt: str
    tier: StakesTier
    purpose: str
    params: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class ReasoningSeam(Protocol):
    """Route a reasoning request to the appropriate tier with timeouts, retries, tracing."""

    def run(self, request: ReasoningRequest) -> str:
        ...


class UnconfiguredReasoningSeam:
    """Placeholder until the tiered client is ported. Fails loudly rather than silently."""

    def run(self, request: ReasoningRequest) -> str:  # noqa: D401
        raise NotImplementedError(
            "reasoning seam not yet wired — port the tiered reasoning_client from the "
            "hardened platform (local bulk tier + subscription high-stakes tier, ADR-0003)"
        )
