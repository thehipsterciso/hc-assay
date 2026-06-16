"""Data versioning — content-addressed, local, deterministic (METHODOLOGY.md §7, ADR-0003).

Every finding must cite the exact bytes it was computed from. This provides a dependency-free,
on-box content-addressing store: an artifact is hashed (SHA-256) and copied under a local
store keyed by that hash, so the same bytes always yield the same version id and any artifact
can be re-fetched by id. (The prior platform used DVC via an external tool; this keeps the
engine self-contained — an adapter may swap in DVC by implementing the same Protocol.)
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

_CHUNK = 1 << 20  # 1 MiB


@runtime_checkable
class DataVersioner(Protocol):
    def put(self, path: str) -> str:
        """Version the artifact at ``path``; return its content hash / version id."""
        ...

    def fingerprint(self, path: str) -> str:
        """Return the content hash of ``path`` without storing it."""
        ...


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


class LocalDataVersioner:
    """Content-addressed local artifact store. Deterministic and fully offline.

    ``store_dir`` defaults to ``ASSAY_DATA_STORE`` or ``./.assay-data``. Files are stored under
    ``<store>/<aa>/<full-hash>`` (sharded by the first two hex chars).
    """

    def __init__(self, store_dir: str | None = None) -> None:
        root = store_dir or os.environ.get("ASSAY_DATA_STORE") or str(Path.cwd() / ".assay-data")
        self._root = Path(root)

    def fingerprint(self, path: str) -> str:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"cannot version a non-file path: {path!r}")
        return _hash_file(p)

    def put(self, path: str) -> str:
        digest = self.fingerprint(path)
        dest = self._root / digest[:2] / digest
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            shutil.copy2(path, tmp)
            tmp.replace(dest)  # atomic publish — readers never see a partial artifact
        return digest

    def path_for(self, digest: str) -> Path:
        """Local path of a previously-stored artifact by its version id."""
        return self._root / digest[:2] / digest
