"""Determinism & reproducibility harness for the baseline (ADR-0001, METHODOLOGY.md §1, §7).

A baseline is only a yardstick if the *same inputs reproduce the same baseline*. This module
makes that contract concrete and engine-level: it content-hashes inputs, derives seeds
deterministically from those hashes, records component versions, and stamps all of it into a
:class:`~assay_engine.baseline.toolkit.BaselineArtifact`'s ``determinism`` record — so a
hostile reviewer can confirm a baseline was produced exactly as claimed.

It is dependency-free and pure. The heavy, *choice-bearing* builders (which embedding model,
which clustering algorithm, which graph construction) encode dataset/study decisions and are
supplied by a study's adapter as :class:`~assay_engine.baseline.toolkit.BaselineBuilder`
implementations — not prescribed by the engine (ADR-0002). This harness records *how* such a
builder ran so the result is reproducible regardless of which builder it was.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from assay_engine import __version__ as _ENGINE_VERSION
from assay_engine._frozen import freeze_mapping
from assay_engine.baseline.toolkit import BaselineArtifact
from assay_engine.contracts.schema import Corpus


def _plain(value: Any) -> Any:
    """Canonicalize a value for stable serialization (Mapping→sorted dict, set→sorted list)."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=repr)
    return value


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_value(value: Any) -> str:
    """Stable content hash of an arbitrary (canonicalizable) value."""
    return hash_text(json.dumps(_plain(value), sort_keys=True, default=str))


def corpus_fingerprint(corpus: Corpus) -> str:
    """Deterministic content hash of a corpus (order-independent across units/relations)."""
    units = [
        {"id": u.unit_id, "text": u.text, "attrs": _plain(u.attributes)}
        for u in sorted(corpus.units, key=lambda u: u.unit_id)
    ]
    relations = [
        {"s": r.source_id, "t": r.target_id, "k": r.kind, "attrs": _plain(r.attributes)}
        for r in sorted(corpus.relations, key=lambda r: (r.source_id, r.target_id, r.kind))
    ]
    payload = {"units": units, "relations": relations, "metadata": _plain(corpus.metadata)}
    return hash_text(json.dumps(payload, sort_keys=True, default=str))


def stable_seed(*parts: str, bits: int = 32) -> int:
    """A deterministic non-negative integer seed derived from ``parts``.

    Derived from a hash so the same inputs always yield the same seed — reproducible without a
    hard-coded magic number, and distinct inputs get distinct seeds.
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return int(digest, 16) % (1 << bits)


@dataclass(frozen=True, slots=True)
class DeterminismRecord:
    """The reproducibility provenance stamped onto a baseline (ADR-0001)."""

    seed: int
    input_hashes: Mapping[str, str]
    component_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_hashes", freeze_mapping(self.input_hashes))
        object.__setattr__(self, "component_versions", freeze_mapping(self.component_versions))

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "input_hashes": dict(self.input_hashes),
            "component_versions": dict(self.component_versions),
        }


def build_baseline_artifact(
    corpus: Corpus,
    contents: Mapping[str, Any],
    *,
    component_versions: Mapping[str, str] | None = None,
    extra_inputs: Mapping[str, Any] | None = None,
    seed: int | None = None,
) -> BaselineArtifact:
    """Assemble a :class:`BaselineArtifact` with a complete determinism record.

    ``contents`` is the builder's output (embeddings, similarity graph, clusters, …).
    ``component_versions`` records the builder + any model/library versions (the engine and
    Python versions are added automatically). ``extra_inputs`` are additional inputs to hash
    (e.g. config). ``seed``, if omitted, is derived deterministically from the corpus + inputs
    so it is reproducible.
    """
    corpus_hash = corpus_fingerprint(corpus)
    input_hashes = {"corpus": corpus_hash}
    for name, value in (extra_inputs or {}).items():
        input_hashes[name] = hash_value(value)

    versions = {"engine": _ENGINE_VERSION, "python": sys.version.split()[0]}
    versions.update(component_versions or {})

    if seed is None:
        seed = stable_seed(*[corpus_hash, *(input_hashes[k] for k in sorted(input_hashes))])

    record = DeterminismRecord(
        seed=seed, input_hashes=input_hashes, component_versions=versions
    )
    return BaselineArtifact(
        corpus_fingerprint=corpus_hash, contents=contents, determinism=record.as_dict()
    )
