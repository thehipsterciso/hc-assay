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
import re
import shutil
import tempfile
from pathlib import Path
from typing import Protocol

_CHUNK = 1 << 20  # 1 MiB
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


# Structural Protocol only — adapter/seam validation is behavior-based, not isinstance (#148).
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
        """Store the artifact under its content hash; return the hash (version id).

        Idempotent: storing the same bytes twice is a no-op returning the same id. Publish is
        atomic — content is copied to a *per-writer-unique* temp file (so two processes
        storing the same digest never clobber a shared temp) and then ``os.replace``-d into
        place, so a reader never observes a partial artifact. The store is content-addressed,
        so an interrupted/duplicate write is harmless.
        """
        digest = self.fingerprint(path)
        dest = self._root / digest[:2] / digest
        if dest.exists():
            return digest
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp-")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            shutil.copy2(path, tmp)
            os.replace(tmp, dest)  # atomic publish within the same filesystem
        finally:
            tmp.unlink(missing_ok=True)  # no-op once replaced; cleans up on copy failure
        return digest

    def path_for(self, digest: str) -> Path:
        """Local path of a previously-stored artifact by its version id.

        The version id MUST be a SHA-256 hex digest (the only form :meth:`put` ever returns).
        Validating it rejects path-traversal payloads (e.g. ``../../etc/passwd``) that would
        otherwise compose a path outside the store (#112).
        """
        if not _SHA256_HEX.fullmatch(digest):
            raise ValueError(
                f"invalid version id {digest!r} (expected a 64-char sha256 hex digest)"
            )
        return self._root / digest[:2] / digest
