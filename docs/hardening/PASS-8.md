# Hardening Pass 8 — coverage matrix + fix-regression audit (and a red-CI discovery)

Branch `harden/pass-8`. Same two dimensions as pass 7 (per-dimension coverage matrix +
fix-regression audit). The headline result: **the merge gate itself had been red for several
passes** and nobody — including seven passes of adversarial assessors — had caught it, because the
assessors check the *code*, not whether *CI actually runs green*. Model: Claude Opus 4.8.

## 1. Assessment → self-refutation → verification

7 dimension assessors + adversarial self-refutation: **18 raw → 7 stood (11 self-refuted)**. One
(`K-OBS-1`) was a duplicate of `K-REL-1` (same SIGTERM bug surfaced by two dimensions), leaving **6
distinct survivors**, ALL **2-agent verified TRUE_POSITIVE**. The 11 self-refutations included 4
thoughtful privacy refutations confirming the pass-7 scrubber holds in real (non-contrived)
contexts.

Then, inspecting the **actual CI run history** (`gh run list`) — not just the code — surfaced **two
more** confirmed defects that the code-only assessors structurally could not see (they ran with a
full venv and `python -m pytest`). Main CI had been **failing on every merge for passes 6–8**,
silently bypassed by `--admin` merges.

## 2. Findings (8 confirmed)

### CI-red blockers (the merge gate was failing; dispositively confirmed by the CI logs)

- **K-CI-2 (high).** CI ran the bare `pytest` console script, which — unlike `python -m pytest` —
  does not put the repo root on `sys.path`. Six suites do `from tests import …`, so collection
  errored with `ModuleNotFoundError: No module named 'tests'`: **the test suite never actually ran
  in CI.** Fix: `pythonpath = ["src", "."]` in `[tool.pytest.ini_options]` so `tests` imports under
  any invocation (now collects 555+ tests).
- **K-CI-1 (high).** The dependency-free `core` lane's `mypy --strict` failed on `seam.py`'s
  runtime-guarded `import httpx` (httpx ships only with the reasoning extra, so no stub in the
  no-extras lane). Fix: `httpx.*` added to the mypy `ignore_missing_imports` overrides, like the
  other optional backends.
- **K-OPS-1 (high).** The lockfile "reproducibility guard" re-resolved against **live PyPI** with no
  point-in-time pin, so it went red the instant any in-range transitive published a release — it was
  failing on clean checkouts. Fix: pin resolution via `--exclude-newer`, sourced from a single
  committed date file `.uv-exclude-newer` read by **both** `ci.yml` and `regenerate_lockfiles.sh`.
  The cutoff (`2026-06-14`) was deliberately chosen clear of a release straddling the boundary
  (`arize-phoenix` 17.6/17.7) where `uv`'s resolution was itself **non-deterministic** between runs;
  all three locks were regenerated and verified reproducible (script output == fresh CI-style
  recompile).

### Code / ops (assessment survivors, 2-agent verified)

- **K-REL-1 (high).** The SIGTERM trace-flush handler swallowed process termination when the prior
  disposition was `SIG_DFL` (the default, non-callable): it flushed and returned, having replaced
  the default terminate action, so `docker stop`/`kill`/k8s hung until SIGKILL escalation. Fix:
  re-establish `SIG_DFL` and re-deliver the signal so the default terminate still runs (chain a
  callable prior; leave `SIG_IGN` ignored).
- **K-OBS-2 (high).** `_log_trail` called `json.dump` inside the `NamedTemporaryFile(delete=False)`
  block *before* assigning `path`; a hashable-but-non-JSON payload value (bytes/datetime — `freeze()`
  only rejects *unhashable*) raised `TypeError` there, **orphaning the temp file** (cleanup
  unreachable) **and silently dropping the #G-009 provenance artifact** (swallowed by `track()`, no
  warning). Fix: serialize up front with `default=str` (can't raise mid-write; artifact still
  attaches), `fh.name` always assigned so cleanup is reachable, and a `_log.warning` in `track()` so
  a tracker failure is never silent again.
- **K-SEC-1 (medium).** The local-URI guard rejected libpq **Unix-domain-socket** hosts (leading
  `/`, e.g. `host=/var/run/postgresql`) as "non-loopback" — the *most* data-sovereign connection
  (never touches the network), while TCP loopback was accepted. Fix: `is_local_socket_path()` accepts
  a single leading-`/` path (UNC `//`, `/\` still rejected), applied in the query-host and DSN
  branches.
- **K-OPS-2 (medium).** `regenerate_lockfiles.sh` — the one documented remediation (referenced by
  `dependabot.yml` + CI errors) — omitted `requirements-build.lock`, which CI gates; a maintainer
  following it stayed red on a build-backend bump. Fix: regenerate all three locks; CI errors now
  point at the script.
- **K-OPS-3 (medium).** The integration job ran `pytest --cov` with **no** `--cov-fail-under`, so the
  coverage gate was vacuous (exits 0 at any level). Fix: `--cov-fail-under=90` (current ~96.6%), plus
  — after a confirm-round concern that a substring test wouldn't catch a degenerate `=0` —
  `[tool.coverage.report] fail_under = 90` in pyproject (local enforcement + single source) and a
  test that asserts a *meaningful* numeric floor on a `--cov=`-instrumented run.

## 3. Confirmation (2 agents per fix)

16 agents: **7/8 BOTH-CONFIRMED first round.** K-OPS-3 returned one CONCERN (the regression test
checked only the flag's presence, not a meaningful value) → remediated (numeric-floor assertion +
pyproject `fail_under`) → effectively closed. All fixes revert-discriminated by the reviewers.

## 4. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **555 passed, 5 skipped**; coverage
  **96.58%** (floor 90, now enforced from pyproject too). Lockfiles reproducible (`regenerate_lockfiles.sh`
  output == fresh CI-style recompile under the pinned `--exclude-newer`).
- The bare-`pytest` CI invocation now collects and runs the full suite; the `core` mypy lane passes
  without extras; the lockfile gate is deterministic.

## 5. Retrospective → pass-9 dimension

**The biggest miss of the campaign so far: CI was red for ~3 passes and the assessment never noticed**
— because every assessor (and my own per-pass local gate runs) checked the code and ran `python -m
pytest`, never the *actual GitHub Actions outcome*, and merges used `--admin`. Two of pass 8's three
highest-impact findings (K-CI-1, K-CI-2) were invisible to a code-only lens and only surfaced from
`gh run list`/`gh run view`.

Pass 9 adds an **"actual CI execution" dimension**: inspect the real CI run for the branch, reproduce
each lane's *exact* command (bare `pytest`, no-extras install, cold-cache `uv` resolve) rather than a
convenient local equivalent, and treat a red required check as a finding in its own right. Corollary
process change: **do not `--admin` past a red CI without reading why** — a green-looking local gate is
not the gate. Convergence is (again) not declared.
