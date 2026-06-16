"""Study definition — the adapter's research questions and pre-registration handle.

A study definition binds an adapter's pieces together for one concrete run: which parser,
which mode, the optional claims source, any extra feature builders, and the research
questions. It lives in the instance repository (one repo per study, ADR-0002), not in the
engine. The engine reads it to drive the run and to anchor pre-registration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from assay_engine.contracts.claims import ExternalClaimsSource
from assay_engine.contracts.features import FeatureBuilder
from assay_engine.contracts.parser import IngestionParser


class StudyMode(Enum):
    """The two modes from the charter. A study may combine both."""

    DISCOVERY = "discovery"
    ADJUDICATE_EXTERNAL_CLAIMS = "adjudicate_external_claims"


@dataclass(frozen=True, slots=True)
class StudyDefinition:
    """Everything the engine needs to run one study, supplied by an adapter."""

    name: str
    modes: frozenset[StudyMode]
    parser: IngestionParser
    research_questions: tuple[str, ...]
    feature_builders: tuple[FeatureBuilder, ...] = ()
    claims_source: ExternalClaimsSource | None = None

    def __post_init__(self) -> None:
        # Coerce modes to a frozenset so the documented frozen+hashable contract holds regardless
        # of which constructor a clone uses — the raw constructor (public API) would otherwise
        # accept a plain set, yielding a "frozen" record that is neither hashable nor immutable
        # (membership checks pass identically, so the bug is silent until hash()) (#135).
        if not isinstance(self.modes, frozenset):
            object.__setattr__(self, "modes", frozenset(self.modes))
        if not all(isinstance(m, StudyMode) for m in self.modes):
            raise TypeError("StudyDefinition.modes must contain only StudyMode members")
        if not self.name.strip():
            raise ValueError("StudyDefinition.name must be non-empty (it is the registry key)")
        if not self.modes:
            raise ValueError("StudyDefinition must declare at least one mode")
        needs_claims = StudyMode.ADJUDICATE_EXTERNAL_CLAIMS in self.modes
        if needs_claims and self.claims_source is None:
            raise ValueError("Adjudication mode requires a claims_source; none was provided")
        if not needs_claims and self.claims_source is not None:
            # A discovery-only study must not carry a claims source — it would risk
            # leaking external judgments into a pipeline that is meant to be blind.
            raise ValueError(
                "claims_source supplied but ADJUDICATE_EXTERNAL_CLAIMS mode not declared"
            )

    @staticmethod
    def discovery(
        name: str,
        parser: IngestionParser,
        research_questions: Sequence[str],
        feature_builders: Sequence[FeatureBuilder] = (),
    ) -> "StudyDefinition":
        return StudyDefinition(
            name=name,
            modes=frozenset({StudyMode.DISCOVERY}),
            parser=parser,
            research_questions=tuple(research_questions),
            feature_builders=tuple(feature_builders),
        )
