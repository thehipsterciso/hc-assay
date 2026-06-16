"""Packaging/config regression guards (pass-1 #120, #121)."""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_version_is_single_sourced_not_static():
    # #120: the version must be declared dynamic (read from __init__.__version__), with no second
    # static literal in pyproject that could drift from the module/provenance value.
    pp = _pyproject()
    assert "version" not in pp["project"], "static version literal reintroduced (drift risk)"
    assert "version" in pp["project"].get("dynamic", [])
    assert pp.get("tool", {}).get("hatch", {}).get("version", {}).get("path") == (
        "src/assay_engine/__init__.py"
    )


def test_version_matches_installed_distribution():
    import importlib.metadata as md

    import assay_engine

    try:
        dist = md.version("assay-engine")
    except md.PackageNotFoundError:  # pragma: no cover - only if not installed
        return
    assert dist == assay_engine.__version__


def test_mypy_is_not_pinned_to_a_single_python_version():
    # #121: a fixed python_version would hide 3.12-3.14-only type errors that the CI matrix
    # is supposed to catch.
    pp = _pyproject()
    assert "python_version" not in pp.get("tool", {}).get("mypy", {})
