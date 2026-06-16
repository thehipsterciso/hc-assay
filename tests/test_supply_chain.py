"""Supply-chain / CI audit-gate regression guards (pass-2 #130, #131, #132, #145, #146, #147).

These guard configuration that lives in .github/workflows/ci.yml and the committed lockfile.
The CI YAML cannot be unit-imported, so the guards are twofold:
  1. config-level: assert the hardened invocation is present in ci.yml (a revert to the buggy
     form fails the test);
  2. behavioral: run the exact allowlist-parsing bash loop against fixtures to prove it is
     newline-agnostic and comment/blank tolerant (the original `while read -r id` form drops a
     final line that lacks a trailing newline).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_LOCK = _ROOT / "requirements.lock"

# The hardened allowlist loop, lifted verbatim from ci.yml's audit job. Kept here so the
# behavioral test exercises the SAME logic the workflow runs.
_PARSE_LOOP = r"""
set -euo pipefail
IGNORES=()
if [ -f "$1" ]; then
  while IFS= read -r id || [ -n "$id" ]; do
    case "$id" in ''|\#*) continue ;; esac
    IGNORES+=(--ignore-vuln "$id")
  done < "$1"
fi
printf '%s\n' "${IGNORES[@]:-<none>}"
"""

# The ORIGINAL buggy loop, for the revert-discrimination assertion in the behavioral test.
_PARSE_LOOP_BUGGY = r"""
IGNORES=""
if [ -f "$1" ]; then
  while read -r id; do [ -n "$id" ] && IGNORES="$IGNORES --ignore-vuln $id"; done < "$1"
fi
printf '%s\n' "$IGNORES"
"""


def _ci_text() -> str:
    return _CI.read_text(encoding="utf-8")


def test_pip_audit_runs_strict_and_require_hashes():
    # #130: without --strict an unauditable dependency is silently skipped while CI stays green.
    # --require-hashes ties the scan to the pinned, hashed lockfile.
    text = _ci_text()
    assert "pip-audit --strict --require-hashes" in text, (
        "audit gate must run pip-audit with --strict --require-hashes (#130)"
    )


def test_audit_scans_the_committed_lockfile_not_the_live_env():
    # #132: the scan must run against the committed lockfile so it is reproducible run-to-run.
    text = _ci_text()
    assert "-r requirements.lock" in text, "pip-audit must scan -r requirements.lock (#132)"
    assert _LOCK.exists(), "requirements.lock must be committed (#132)"


def test_lockfile_is_fully_pinned_and_hashed():
    # #132/#146: every dependency line is an exact == pin carrying at least one sha256 hash, so the
    # audited set is reproducible and no over-wide range can drift the resolved version.
    body = [
        ln
        for ln in _LOCK.read_text(encoding="utf-8").splitlines()
        if ln and not ln.lstrip().startswith("#") and not ln.lstrip().startswith("--hash")
    ]
    pinned = [ln for ln in body if "==" in ln]
    assert len(pinned) >= 50, "lockfile looks empty/under-resolved"
    text = _LOCK.read_text(encoding="utf-8")
    assert "--hash=sha256:" in text, "lockfile must carry hashes (#132 --require-hashes)"
    # no loose comparators that admit a range in the LOCK (pyproject ranges stay permissive)
    for ln in pinned:
        assert ">=" not in ln and "<" not in ln.split(";")[0], f"lock pin not exact: {ln!r}"


def test_lockfile_sync_is_enforced_in_ci():
    # #132: a stale lock (pyproject changed, lock not regenerated) must fail CI.
    text = _ci_text()
    assert "uv pip compile" in text and "requirements.lock is stale" in text


def test_sbom_is_emitted():
    # #147: a CycloneDX SBOM artifact is produced for downstream license/transitive monitoring.
    text = _ci_text()
    assert "cyclonedx-json" in text and "sbom" in text.lower()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_allowlist_parse_is_newline_agnostic_and_comment_tolerant(tmp_path):
    # #131/#145: the last advisory id must be honored even with no trailing newline, comments and
    # blank lines skipped, and ids must not word-split/glob-expand.
    f = tmp_path / "ignore"
    f.write_bytes(b"# a comment\n\nGHSA-aaaa\nPYSEC-2024-last-no-newline")  # no trailing \n
    out = subprocess.run(
        ["bash", "-c", _PARSE_LOOP, "_", str(f)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "GHSA-aaaa" in out
    assert "PYSEC-2024-last-no-newline" in out, "final newline-less id dropped (#131)"
    assert "# a comment" not in out, "comment line leaked into ignores (#131)"

    # revert-discrimination: the original loop DROPS the final newline-less id.
    buggy = subprocess.run(
        ["bash", "-c", _PARSE_LOOP_BUGGY, "_", str(f)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "PYSEC-2024-last-no-newline" not in buggy, (
        "buggy loop unexpectedly kept the id — test no longer discriminates"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_allowlist_ids_do_not_glob_expand(tmp_path):
    # #145: an allowlist line is passed as a single argv element even if it contains shell glob
    # metacharacters (it must never expand against the working directory).
    f = tmp_path / "ignore"
    f.write_text("GHSA-*\n", encoding="utf-8")
    (tmp_path / "GHSA-real-file").write_text("x", encoding="utf-8")
    out = subprocess.run(
        ["bash", "-c", f"cd {tmp_path} && " + _PARSE_LOOP, "_", str(f)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "GHSA-*" in out, "glob metacharacter expanded against cwd (#145)"
    assert "GHSA-real-file" not in out
