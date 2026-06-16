"""Docs-vs-code drift guards (pass-2 #136, #150, #151, #152, #153, #154).

Normative docs make claims a public reader relies on. These guards pin the corrected wording so
a regression (re-introducing an over-claim or a stale status) fails CI. They assert on the
*specific* stale strings the pass-2 audit found, plus presence of the honest replacement.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_data_sovereignty_is_qualified_for_high_stakes_tier():
    # #136: the absolute "nothing leaves the machine" over-claim must be qualified — the optional
    # high-stakes tier sends prompt content off-box.
    for rel in ("README.md", "docs/CHARTER.md", "docs/GOVERNANCE.md"):
        text = _read(rel)
        assert "nothing leaves the machine" not in text, f"{rel}: unconditional over-claim (#136)"
        assert "off-box" in text, f"{rel}: high-stakes off-box caveat missing (#136)"
    adr = _read("docs/decisions/ADR-0003-local-first-data-sovereign.md")
    assert "off-box" in adr and "the same as" in adr  # billing vs residency separated


def test_charter_status_is_not_stale():
    # #150: the status line must not still call the seams "stubs being wired".
    charter = _read("docs/CHARTER.md")
    assert "stubs being wired" not in charter
    assert "implemented and composed" in charter or "in place and hardened" in charter


def test_baseline_toolkit_scope_is_honest():
    # #151: the engine ships primitives + a determinism harness, NOT embedding/clustering/graph
    # builders — those are adapter-supplied. Docs/package docstring must say so.
    arch = _read("docs/ARCHITECTURE.md")
    init = _read("src/assay_engine/__init__.py")
    for text in (arch, init):
        # the corrected text names the adapter's BaselineBuilder as the source of choice-bearing
        # builders rather than claiming the engine ships them
        assert "BaselineBuilder" in text


def test_preregistration_timestamp_wording_matches_shipped_default():
    # #152: body text must not present RFC-3161 as the in-force mechanism; HMAC is the default.
    for rel in ("docs/METHODOLOGY.md", "docs/GOVERNANCE.md"):
        text = _read(rel)
        assert "HMAC" in text, f"{rel}: shipped HMAC default not stated (#152)"
        assert "pluggable" in text, f"{rel}: RFC-3161 must be described as pluggable (#152)"


def test_readme_install_notes_not_on_pypi():
    # #153: the quickstart must not present `pip install assay-engine` as a working path without
    # the not-yet-on-PyPI caveat + a from-source path.
    readme = _read("README.md")
    assert "Not yet on PyPI" in readme
    assert "pip install -e" in readme  # the working from-source path


def test_adr0006_lists_the_baseline_extra():
    # #154: ADR-0006's extras enumeration must include `baseline` (pyproject has five extras).
    adr = _read("docs/decisions/ADR-0006-optional-backends-lazy-imports.md")
    assert "`baseline`" in adr
