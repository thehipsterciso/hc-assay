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
    # #136 + #F-038: the absolute "nothing leaves the machine" over-claim must be qualified — the
    # optional high-stakes tier sends prompt content off-box. Pin the SPECIFIC high-stakes caveat
    # phrase ("not metered, but off-box"), not a loose "off-box" substring: GOVERNANCE has a
    # second, unrelated "off-box" occurrence (the SaaS-observability disqualification), so the loose
    # check passed even if the high-stakes-tier caveat itself were deleted.
    for rel in ("README.md", "docs/CHARTER.md", "docs/GOVERNANCE.md"):
        text = _read(rel)
        assert "nothing leaves the machine" not in text, f"{rel}: unconditional over-claim (#136)"
        # each file must tie the off-box caveat to the metered/subscription distinction
        assert "off-box" in text and "metered" in text, (
            f"{rel}: high-stakes off-box / metered caveat missing (#136)"
        )
    # GOVERNANCE has a SECOND, unrelated "off-box" (the SaaS-observability disqualification), so a
    # loose substring passed even if the high-stakes-tier caveat were deleted. Pin its exact
    # localized phrase so deleting it fails (#F-038).
    gov = _read("docs/GOVERNANCE.md")
    assert "not metered, but off-box" in gov, (
        "GOVERNANCE high-stakes off-box caveat removed (#F-038)"
    )
    adr = _read("docs/decisions/ADR-0003-local-first-data-sovereign.md")
    assert "off-box" in adr and "the same as" in adr  # billing vs residency separated


def test_charter_status_is_not_stale():
    # #150: the status line must not still call the seams "stubs being wired".
    charter = _read("docs/CHARTER.md")
    assert "stubs being wired" not in charter
    assert "implemented and composed" in charter or "in place and hardened" in charter


def test_baseline_toolkit_scope_is_honest():
    # #151 + #F-038: the engine ships primitives + a determinism harness, NOT embedding/clustering/
    # graph builders — those are adapter-supplied. Two-sided: assert the POSITIVE attribution
    # (the choice-bearing builders come from the adapter's BaselineBuilder, not the engine), so a
    # regression re-introducing an "engine ships builders" claim — which leaves "BaselineBuilder"
    # in the text and so passed the old single-substring check — now fails.
    arch = _read("docs/ARCHITECTURE.md")
    init = _read("src/assay_engine/__init__.py")
    for text in (arch, init):
        assert "BaselineBuilder" in text
    assert "not shipped by the engine" in arch, "ARCHITECTURE missing the explicit non-ship caveat"
    assert "supplied per study by" in init, "__init__ missing the adapter-attribution caveat"


def test_preregistration_timestamp_wording_matches_shipped_default():
    # #152: body text must not present RFC-3161 as the in-force mechanism; HMAC is the default.
    for rel in ("docs/METHODOLOGY.md", "docs/GOVERNANCE.md"):
        text = _read(rel)
        assert "HMAC" in text, f"{rel}: shipped HMAC default not stated (#152)"
        assert "pluggable" in text, f"{rel}: RFC-3161 must be described as pluggable (#152)"
    # Guard the SPECIFIC stale over-claims, so re-introducing either one fails CI even though the
    # word "HMAC" appears elsewhere in the file (file-level substring checks alone don't catch a
    # localized regression — the pass-2 confirmation flagged this on GOVERNANCE §2 step 3).
    gov = _read("docs/GOVERNANCE.md")
    assert "RFC-3161 timestamped** against a trusted timestamp authority" not in gov, (
        "GOVERNANCE §2 step 3 stale RFC-3161 over-claim reintroduced (#152)"
    )
    meth = _read("docs/METHODOLOGY.md")
    assert "RFC-3161 timestamped before confirmation" not in meth, (
        "METHODOLOGY §7 stale RFC-3161 over-claim reintroduced (#152)"
    )


def test_readme_install_notes_not_on_pypi():
    # #153: the quickstart must not present `pip install assay-engine` as a working path without
    # the not-yet-on-PyPI caveat + a from-source path.
    readme = _read("README.md")
    assert "Not yet on PyPI" in readme
    assert "pip install -e" in readme  # the working from-source path


def test_adr0006_lists_the_baseline_extra():
    # #154 + #F-038: ADR-0006's extras enumeration must include `baseline` AND must not understate
    # the count. Two-sided: assert every current extra name is present (so dropping any one fails)
    # and that no stale "four extras" undercount survives alongside.
    adr = _read("docs/decisions/ADR-0006-optional-backends-lazy-imports.md")
    for extra in (
        "`reasoning`",
        "`observability`",
        "`persistence`",
        "`orchestration`",
        "`baseline`",
    ):
        assert extra in adr, f"ADR-0006 extras enumeration missing {extra} (#F-038)"
    assert "four extras" not in adr, "ADR-0006 understates the extras count (stale 'four extras')"
