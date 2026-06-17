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


def test_ci_allowlist_loop_is_robust_in_the_workflow_file():
    # #131/#145: guard ci.yml ITSELF (not only the behavioral copy) — the workflow must use the
    # newline-agnostic read and the quoted-array expansion, and must NOT contain the buggy forms.
    text = _ci_text()
    assert "read -r id || [ -n" in text, "ci.yml allowlist read is not newline-agnostic (#131)"
    assert "IGNORES+=(" in text and '"${IGNORES[@]}"' in text, (
        "ci.yml IGNORES not a quoted array (#145)"
    )
    # the original buggy string-accumulation form must be gone
    assert 'IGNORES="$IGNORES --ignore-vuln' not in text, (
        "buggy unquoted IGNORES string reintroduced"
    )
    assert "while read -r id; do [ -n" not in text, "buggy non-newline-agnostic loop reintroduced"
    # #F-052: the behavioral allowlist tests run a hardcoded copy of the loop against a tmp file,
    # so they cannot catch a change to the allowlist FILENAME in ci.yml. Pin the filename here.
    assert ".pip-audit-ignore" in text, "ci.yml allowlist filename changed (#F-052)"


def test_no_dependency_range_spans_multiple_majors():
    # #146: an over-wide range (e.g. arize-phoenix>=7.0,<18) admits ~10 majors and defeats the
    # reproducibility intent. Guard that each extra's pins keep floor and ceiling within one major.
    import re
    import tomllib

    pp = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = pp["project"]["optional-dependencies"]
    offenders = []
    for group, deps in extras.items():
        for spec in deps:
            m = re.search(r">=\s*(\d+)[\d.]*\s*,\s*<\s*(\d+)", spec)
            if m:
                floor_major, ceil_major = int(m.group(1)), int(m.group(2))
                if ceil_major - floor_major > 2:  # allow <floor+2; flag the wide ones
                    offenders.append(f"{group}: {spec} spans {ceil_major - floor_major} majors")
    assert not offenders, f"over-wide dependency ranges: {offenders}"


def test_dependabot_monitors_dependencies():
    # #147: automated dependency/transitive update monitoring must exist, not only a one-shot scan.
    db = _ROOT / ".github" / "dependabot.yml"
    assert db.exists(), "no .github/dependabot.yml (#147)"
    text = db.read_text(encoding="utf-8")
    assert "package-ecosystem: pip" in text
    # #F-053: the github-actions ecosystem must also be monitored so action-pinning drift (the
    # #F-037 class) is surfaced — deleting that block must fail this test.
    assert "package-ecosystem: github-actions" in text


def test_license_gate_present():
    # #147: a license gate denies strong-copyleft licenses in the dependency set.
    text = _ci_text()
    assert "License gate" in text and "pip-licenses" in text and "license_gate.py" in text
    gate = (_ROOT / "scripts" / "license_gate.py").read_text(encoding="utf-8")
    assert "AGPL" in gate and "GPL" in gate  # denies strong-copyleft families


def _load_license_gate():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "license_gate", _ROOT / "scripts" / "license_gate.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "license_name,denied",
    [
        ("Server Side Public License", True),  # #F-015: SSPL prose form
        ("European Union Public Licence 1.2", True),  # #F-015: EUPL prose form
        ("GNU Affero General Public License v3", True),  # AGPL prose form
        ("SSPL", True),
        ("GPL-3.0", True),
        ("GNU Lesser General Public License v3 (LGPLv3)", False),  # weak copyleft permitted
        ("MIT", False),
        ("Apache-2.0", False),
        ("BSD-3-Clause", False),
    ],
)
def test_license_gate_behavioral_denies_strong_copyleft(tmp_path, license_name, denied):
    # #F-015 + #F-039: a BEHAVIORAL test (call main() on a synthetic report), not a string-presence
    # check — the prose-name SSPL/EUPL bypass and any logic regression are caught here.
    import json

    gate = _load_license_gate()
    report = [{"Name": "pkg", "Version": "1.0", "License": license_name}]
    p = tmp_path / "licenses.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    rc = gate.main(str(p))
    assert rc == (1 if denied else 0), f"{license_name!r}: expected denied={denied}"


def test_ci_test_lanes_install_hash_pinned_not_live_pypi():
    # #F-004: the core AND integration test lanes must install from the hashed lockfiles with
    # --require-hashes, not a live `pip install -e .[...]` against PyPI (where a malicious patch
    # release could execute under test).
    text = _ci_text()
    assert "--require-hashes -r requirements-core.lock" in text, (
        "core lane not hash-pinned (#F-004)"
    )
    assert "--require-hashes -r requirements.lock" in text, "integration lane not hash-pinned"
    assert (_ROOT / "requirements-core.lock").exists(), "requirements-core.lock missing (#F-004)"
    # the old live-resolution install of the engine-with-extras must be gone from the test lanes
    assert 'pip install -e ".[dev]"' not in text
    assert 'pip install -e ".[dev,reasoning' not in text


def test_core_lockfile_is_pinned_and_hashed_and_extra_free():
    # #F-004: the core lock backs the no-extras lane — it must be fully pinned + hashed and must
    # NOT pull in any backend extra (preserving the ADR-0006 dependency-free-core guard).
    core = (_ROOT / "requirements-core.lock").read_text(encoding="utf-8")
    assert "--hash=sha256:" in core
    for backend in ("arize-phoenix", "langgraph", "psycopg", "qdrant-client", "langchain-ollama"):
        assert f"\n{backend}==" not in core, f"core lock leaked a backend extra: {backend}"


def test_sbom_generation_fails_loud():
    # #F-012: the SBOM step must not mask pip-audit failure with `|| true`, and the upload must
    # error (not warn) on a missing file — a broken/absent SBOM cannot pass CI green.
    text = _ci_text()
    sbom_section = text[text.index("SBOM (CycloneDX)") :]
    assert "cyclonedx-json -o sbom.cyclonedx.json || true" not in sbom_section, "SBOM masks failure"
    assert "if-no-files-found: error" in text, "SBOM/license upload must error on missing file"


def test_license_gate_scans_pinned_lockfile_not_live_resolution():
    # #F-013: the license gate must scan the hash-pinned set, not a live `pip install -e .[all]`.
    text = _ci_text()
    gate_section = text[text.index("License gate") :]
    assert 'pip install -e ".[all]"' not in gate_section, "license gate still live-resolves .[all]"
    assert "--require-hashes -r requirements.lock" in gate_section


def test_ci_has_umbrella_required_check():
    # #F-014: a single fan-in job depends on every other job so branch protection requires only it
    # — audit/integration can't be silently dropped from the merge gate.
    text = _ci_text()
    assert "all-checks:" in text
    assert "needs: [core, integration, audit]" in text


def test_ci_pins_uv_version():
    # #F-031: uv must be pinned so a format change between versions cannot cause spurious stale-lock
    # diffs that block every PR.
    text = _ci_text()
    assert "pip install uv==" in text, "uv is not pinned in the lockfile sync check (#F-031)"
    assert "pip install --upgrade uv\n" not in text, "unpinned uv upgrade reintroduced"


def test_sbom_step_applies_the_allowlist():
    # #G-015: the SBOM pip-audit (which exits non-zero on ANY finding) must apply the same
    # allowlist as the gate, or an ACCEPTED advisory fails SBOM generation under set -euo pipefail
    # even though the gate passed.
    text = _ci_text()
    sbom = text[text.index("SBOM (CycloneDX)") : text.index("Upload SBOM artifact")]
    assert "--ignore-vuln" in sbom and ".pip-audit-ignore" in sbom, (
        "SBOM step does not apply the allowlist (#G-015)"
    )
    assert 'cyclonedx-json -o sbom.cyclonedx.json "${IGNORES[@]}"' in sbom


def test_audit_tooling_is_version_pinned():
    # #G-022: pip-audit and pip-licenses must be pinned so the supply-chain gate is reproducible
    # run-to-run (a tooling bump can't silently change advisory/license results).
    text = _ci_text()
    assert "pip-audit==" in text, "pip-audit not version-pinned (#G-022)"
    assert "pip-licenses==" in text, "pip-licenses not version-pinned (#G-022)"
    assert "install --upgrade pip pip-audit\n" not in text, (
        "unpinned pip-audit install reintroduced"
    )


def test_dependabot_lockfile_regen_is_documented():
    # #G-016: Dependabot can't regenerate the uv lockfiles, so the manual regen path must be
    # documented + scripted, or every Dependabot PR is stuck on the stale-lock gate.
    regen = _ROOT / "scripts" / "regenerate_lockfiles.sh"
    assert regen.exists(), "no scripts/regenerate_lockfiles.sh (#G-016)"
    body = regen.read_text(encoding="utf-8")
    assert "uv pip compile" in body and "requirements-core.lock" in body
    db = (_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "regenerate_lockfiles.sh" in db, "dependabot.yml does not point at the regen script"


def test_license_gate_surfaces_unknown_licenses(tmp_path):
    # #H-007: an UNKNOWN/empty-license package must not pass SILENTLY (it could hide a copyleft) —
    # it is surfaced as a ::warning::; the gate still only FAILS on explicit deny matches.
    import json

    gate = _load_license_gate()
    report = [
        {"Name": "mystery", "Version": "1", "License": "UNKNOWN"},
        {"Name": "blank", "Version": "1", "License": ""},
        {"Name": "ok", "Version": "1", "License": "MIT"},
    ]
    p = tmp_path / "licenses.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = gate.main(str(p))
    out = buf.getvalue()
    assert rc == 0  # unknown licenses do not FAIL the gate (would be too brittle)
    assert "::warning::" in out and "mystery" in out and "blank" in out  # but are surfaced


def test_ci_has_least_privilege_permissions():
    # #H-008: the workflow must pin the GITHUB_TOKEN to read-only at the top level.
    text = _ci_text()
    assert "permissions:" in text and "contents: read" in text, "no least-privilege token (#H-008)"


def test_ci_integration_verifies_services_are_reachable():
    # #H-009: the integration job must fail loudly if the service containers aren't reachable, so
    # the live tests can't silently SKIP and let the gate pass vacuously.
    text = _ci_text()
    assert "service containers are reachable" in text or "never became ready" in text, (
        "integration job has no service-readiness gate (#H-009)"
    )
    assert "pg_isready" in text and "/readyz" in text


def test_ci_pins_build_backend_and_disables_live_build_isolation():
    # #J-003: the editable install must use the hashed build backend (requirements-build.lock) with
    # --no-build-isolation, so hatchling isn't fetched live/un-hashed from PyPI (an unscanned,
    # non-reproducible build-time code-exec window).
    text = _ci_text()
    assert "--no-build-isolation --no-deps -e ." in text, "build isolation still live (#J-003)"
    assert "requirements-build.lock" in text
    assert (_ROOT / "requirements-build.lock").exists()
    build = (_ROOT / "requirements-build.lock").read_text(encoding="utf-8")
    assert "hatchling==" in build and "--hash=sha256:" in build
    assert "pip install --no-deps -e .\n" not in text  # the old live-isolation install is gone


def test_ci_license_gate_scopes_to_dependency_set():
    # #J-006: the license gate must scan the dependency set, not entire site-packages
    # (--with-system pulls system tooling that can spuriously fail or mask the gate).
    text = _ci_text()
    assert "pip-licenses --format=json --with-system" not in text, (
        "license gate still --with-system"
    )


def test_github_actions_are_sha_pinned():
    # #F-037: every `uses:` third-party action must be pinned to a 40-char commit SHA (a mutable
    # tag can be force-pushed to malicious code). A version tag is allowed only as a comment.
    import re

    text = _ci_text()
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses, "no actions found"
    for ref in uses:
        _, _, pin = ref.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", pin), f"action {ref!r} not pinned to a commit SHA"


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
