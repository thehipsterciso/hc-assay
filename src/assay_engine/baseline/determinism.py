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

# The canonical hashing primitives moved to ``assay_engine._canonical`` (see note below); these
# imports re-export them at their historical home so existing call sites keep working.
from assay_engine._canonical import canonical_plain as _plain  # noqa: F401
from assay_engine._canonical import hash_bytes as hash_bytes  # noqa: F401  (re-export)
from assay_engine._canonical import hash_text as hash_text  # noqa: F401  (re-export, historical home)
from assay_engine._canonical import hash_value as hash_value  # re-export (baseline public API)
from assay_engine._canonical import keytag as _keytag  # noqa: F401
from assay_engine._frozen import freeze_mapping
from assay_engine.baseline.toolkit import BaselineArtifact
from assay_engine.contracts.schema import Corpus

# The canonical hashing primitives (``_plain``/``_keytag``/``hash_bytes``/``hash_text``/
# ``hash_value``) live in ``assay_engine._canonical`` so they sit below both ``baseline`` and
# ``methodology`` in the import graph (audit #B1/#B2/#B5 originally landed here; hoisted so
# pre-registration can content-bind a hypothesis with the *same* type-faithful digest). They are
# re-exported above for back-compat.


def corpus_fingerprint(corpus: Corpus) -> str:
    """Deterministic content hash of a corpus (order-independent across units/relations).

    The fingerprint is SHA-256 over the canonical JSON of the corpus payload. The JSON is
    streamed into the hash via ``JSONEncoder.iterencode`` rather than materialized as one giant
    string (pass 3, #F-016): for a large corpus this avoids holding the full serialized payload
    in RAM on top of the row dicts at hash time. ``iterencode`` with the same options yields the
    identical byte stream ``json.dumps`` would, so the fingerprint is byte-for-byte unchanged.
    """
    units = [
        {"id": u.unit_id, "text": u.text, "attrs": _plain(u.attributes)}
        for u in sorted(corpus.units, key=lambda u: u.unit_id)
    ]
    relations = [
        {"s": r.source_id, "t": r.target_id, "k": r.kind, "attrs": _plain(r.attributes)}
        for r in sorted(corpus.relations, key=lambda r: (r.source_id, r.target_id, r.kind))
    ]
    payload = {"units": units, "relations": relations, "metadata": _plain(corpus.metadata)}
    h = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, allow_nan=False)
    for chunk in encoder.iterencode(payload):
        h.update(chunk.encode("utf-8"))
    return h.hexdigest()


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
    corpus_hash: str | None = None,
    trust_corpus_hash: bool = False,
) -> BaselineArtifact:
    """Assemble a :class:`BaselineArtifact` with a complete determinism record.

    ``contents`` is the builder's output (embeddings, similarity graph, clusters, …).
    ``component_versions`` records the builder + any model/library versions (the engine and
    Python versions are added automatically). ``extra_inputs`` are additional inputs to hash
    (e.g. config). ``seed``, if omitted, is derived deterministically from the corpus + inputs
    so it is reproducible.

    ``corpus_hash`` lets a caller pass an already-computed :func:`corpus_fingerprint` (#119). By
    default it is **verified** against the corpus and a mismatch raises ``ValueError`` — a
    stale/typo'd hash would otherwise produce a determinism record whose fingerprint and derived
    seed describe a *different* corpus than the one passed, silently defeating the reproducibility
    guarantee this harness exists to provide (#155). Pass ``trust_corpus_hash=True`` to skip the
    recompute (the #119 optimization) only when the caller computed the hash from this exact
    corpus and accepts integrity responsibility.
    """
    if corpus_hash is None:
        corpus_hash = corpus_fingerprint(corpus)
    elif not trust_corpus_hash:
        # Verify the supplied hash binds the corpus actually passed (default-safe, #155).
        actual = corpus_fingerprint(corpus)
        if corpus_hash != actual:
            raise ValueError(
                f"corpus_hash {corpus_hash!r} does not match the corpus "
                f"(corpus_fingerprint={actual!r}) — the determinism record would bind the wrong "
                "data; pass trust_corpus_hash=True only if you accept integrity responsibility"
            )
    if extra_inputs and "corpus" in extra_inputs:
        raise ValueError("'corpus' is a reserved input-hash key — rename the extra input (#B7)")
    input_hashes = {"corpus": corpus_hash}
    for name, value in (extra_inputs or {}).items():
        input_hashes[name] = hash_value(value)

    versions = {"engine": _ENGINE_VERSION, "python": sys.version.split()[0]}
    versions.update(component_versions or {})

    if seed is None:
        # Derive from all input hashes (the corpus hash is already among them under "corpus").
        seed = stable_seed(*(input_hashes[k] for k in sorted(input_hashes)))

    record = DeterminismRecord(seed=seed, input_hashes=input_hashes, component_versions=versions)
    return BaselineArtifact(
        corpus_fingerprint=corpus_hash, contents=contents, determinism=record.as_dict()
    )
