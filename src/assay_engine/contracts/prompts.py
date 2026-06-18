"""Prompt manifest — version-tracks the adapter callables that embed LLM prompts.

The methodology's reproducibility guarantee extends to the prompts in adapter callables
(``discover``, ``confirm_held_out``, ``hypothesis_for``, ``confirm_claim``). A
:class:`PromptManifest` is a frozen record the adapter commits alongside its implementation;
the engine logs it to the experiment tracker at run start so every run is comparable by
prompt version without opening the adapter source.

Usage by an adapter::

    from assay_engine.contracts.prompts import PromptManifest, prompt_manifest

    MANIFEST = prompt_manifest(
        discover="v1.2",
        confirm_held_out="v1.0",
    )

Then pass ``prompt_manifest=MANIFEST`` to :class:`~assay_engine.pipeline.StudyPlan`.
"""

from __future__ import annotations

from typing import Mapping


class PromptManifest(dict[str, str]):
    """An immutable mapping of ``{callable_name: version_string}`` for prompt versioning.

    Version strings are adapter-defined — a semver, a git SHA of the prompt file, or a
    date string all work. The engine logs each entry as an MLflow param
    (``prompt_version.<callable_name>``) at run start so runs are comparable by prompt version
    without opening the adapter source.
    """

    def __new__(cls, entries: Mapping[str, str]) -> "PromptManifest":
        obj = super().__new__(cls, entries)
        return obj

    def __init__(self, entries: Mapping[str, str]) -> None:
        super().__init__(entries)

    def __setitem__(self, key: str, value: str) -> None:  # type: ignore[override]
        raise TypeError("PromptManifest is immutable")

    def __delitem__(self, key: str) -> None:  # type: ignore[override]
        raise TypeError("PromptManifest is immutable")

    def clear(self) -> None:
        raise TypeError("PromptManifest is immutable")

    def pop(self, *args: object) -> str:  # type: ignore[override]
        raise TypeError("PromptManifest is immutable")

    def popitem(self) -> tuple[str, str]:
        raise TypeError("PromptManifest is immutable")

    def update(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        raise TypeError("PromptManifest is immutable")

    def setdefault(self, key: str, default: str = "") -> str:
        raise TypeError("PromptManifest is immutable")

    def __repr__(self) -> str:
        return f"PromptManifest({dict(self)!r})"


def prompt_manifest(**callables: str) -> PromptManifest:
    """Convenience constructor: ``prompt_manifest(discover="v1.2", confirm_held_out="v1.0")``."""
    return PromptManifest(callables)
