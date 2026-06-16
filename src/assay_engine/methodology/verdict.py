"""The three verdicts (ADR-0004, METHODOLOGY.md §4).

A confirmatory test returns exactly one of supported / contradicted / indeterminate — never
a forced binary. Every verdict carries the evidence and the decision rule behind it, so a
reviewer can re-derive it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from assay_engine._frozen import freeze_mapping


class VerdictLabel(Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class Verdict:
    """The outcome of one confirmatory test, structured identically for all three labels.

    ``indeterminate`` is first-class: underpowered, beyond the measurement's reach, or a
    disagreement plausibly attributable to a method limitation rather than a claim error.
    """

    hypothesis_id: str
    label: VerdictLabel
    decision_rule: str
    statistic: float | None = None
    threshold: float | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        # The label annotation is type-checker-only; a study-supplied confirmer (the public
        # ClaimConfirmer/HeldOutConfirmer Protocols) that returns a bare string label would
        # otherwise build a structurally-valid Verdict that later crashes _score with an opaque
        # KeyError and breaks verdict.label.value provenance lines. Fail fast and attributable
        # at construction instead (#133).
        if not isinstance(self.label, VerdictLabel):
            raise TypeError(
                f"Verdict.label must be a VerdictLabel, got {type(self.label).__name__!r} "
                f"({self.label!r}) for hypothesis {self.hypothesis_id!r}"
            )
        if not isinstance(self.hypothesis_id, str) or not self.hypothesis_id:
            raise ValueError("Verdict.hypothesis_id must be a non-empty str")
        object.__setattr__(self, "evidence", freeze_mapping(self.evidence))

    @property
    def is_indeterminate(self) -> bool:
        return self.label is VerdictLabel.INDETERMINATE

    @classmethod
    def supported(cls, hypothesis_id: str, decision_rule: str, **kw: Any) -> "Verdict":
        return cls(hypothesis_id, VerdictLabel.SUPPORTED, decision_rule, **kw)

    @classmethod
    def contradicted(cls, hypothesis_id: str, decision_rule: str, **kw: Any) -> "Verdict":
        return cls(hypothesis_id, VerdictLabel.CONTRADICTED, decision_rule, **kw)

    @classmethod
    def indeterminate(cls, hypothesis_id: str, decision_rule: str, **kw: Any) -> "Verdict":
        return cls(hypothesis_id, VerdictLabel.INDETERMINATE, decision_rule, **kw)
