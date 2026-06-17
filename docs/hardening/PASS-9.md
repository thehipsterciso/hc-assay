# Hardening Pass 9 — the "actual CI execution" dimension + pass-8 fix-regression

Branch `harden/pass-9`. Adds the dimension pass 8's retrospective demanded — **inspect the real CI
outcome, not just the code** — alongside the standing fix-regression audit and security/privacy/
methodology probes. Model: Claude Opus 4.8.

## 1. Assessment → self-refutation → verification

6 dimension assessors + adversarial self-refutation: **10 raw → 5 stood (5 self-refuted)**. All 5
were **2-agent verified TRUE_POSITIVE**.

## 2. Findings (5 confirmed)

| ID | Sev | Dimension | Finding |
|----|-----|-----------|---------|
| K-SEC-9-1 | HIGH | security (fix-regression) | **Pass-8's own K-SEC-1 fix introduced an off-box bypass.** The Unix-socket allowance checked the *whole* host value, so libpq's comma multi-host `host=/tmp,evil.com` (and `host=/var/run/postgresql,10.0.0.5`, and the URI-query form) was **accepted** — libpq tries the socket then falls back to the off-box TCP host, defeating ADR-0003. The authority branch split multi-host; the DSN/query branches did not. |
| CI-1 | HIGH | actual CI execution | **No enforced required status check.** Branch protection is unavailable on this repo's plan (private + free → the protection API returns 403), so the `all-checks` fan-in job is computed but **nothing blocks merging a red PR** — the precise mechanism behind the campaign's silently-red CI (merge commits for #161/#162/#166/#167/#168 all show `conclusion=failure`). |
| P9-PII-1 | MED | privacy | The operator's **machine/namespace hostname** (`hc-macmini` / `hc-macmini.local`, and the RDF-namespace `hc-grc.local`) leaked into committed transcripts — operator/infra identity no email/username/handle rule covered. |
| P9-MO-1 | MED | methodology | confirm primitives raised an **opaque `TypeError`** (`0.0 < None`) when `alpha` was locked on neither the hypothesis nor the call, instead of a clear error. |
| P9-MO-2 | LOW | reliability | Bare `int()`/`float()` parsing of `ASSAY_*` env vars in `seam.py` (8) and `checkpoint.py` (4) raised an opaque "invalid literal" naming **no var** — the exact class already fixed elsewhere via `_int_env`. |

## 3. The new dimension and the fix-regression audit both paid off immediately

- **CI-1** is a pure "actual CI execution" finding: it required reading the platform's enforcement
  state (`gh api .../branches/main/protection` → 403) and the real run history, not the code.
- **K-SEC-9-1** is a fix-regression of pass 8's *own* security fix — the second consecutive pass
  where auditing the prior pass's diff caught a HIGH (pass 8 caught J-001/CV-O-1; pass 9 catches the
  K-SEC-1 multi-host bypass). Fixes keep creating adjacent surface.

## 4. Fixes

- **K-SEC-9-1** — `is_local_socket_path()` rejects any value containing `,`; the DSN and query
  branches split host/hostaddr on `,` and validate **every** element (mirroring `_authority_hosts`).
  Verified: all multi-host bypasses rejected; single socket/loopback accepted; UNC still rejected.
- **CI-1** — the remediation is necessarily a **compensating control** (enabling protection is out of
  scope: a public repo would publish the committed transcripts; a plan upgrade is a billing
  decision). Added `scripts/require_green_ci.sh` (exits non-zero unless the latest `ci` run for the
  branch is green), `docs/MERGE-POLICY.md` (the constraint + the mandatory pre-merge procedure), and
  an honest `#CI-1` caveat on the `all-checks` comment. The campaign now runs this gate before every
  merge and never `--admin`-merges past a red check.
- **P9-PII-1** — `_hostname_patterns()` derives the machine hostname (`socket`/`platform`/`scutil`)
  and redacts bare + `.local`; `ASSAY_SCRUB_HOSTS` namespace hosts get only their `.local` form
  redacted so the bare project token (`hc-grc`) and unrelated `*.local` (e.g. `settings.local.json`)
  are preserved. Corpus re-scrubbed (`grep` now 0 for the hostnames; 1400 bare `hc-grc` intact).
- **P9-MO-1** — `_validate_alpha` rejects `None` with a `ValueError` naming `alpha`.
- **P9-MO-2** — new shared `assay_engine._envparse` (`int_env`/`float_env`, empty→default, error
  names the var) wired into `seam.py` + `checkpoint.py`.

## 5. Confirmation (2 agents per fix)

10 agents: **4/5 BOTH-CONFIRMED first round** (K-SEC-9-1, CI-1, P9-MO-1, P9-MO-2), all
revert-discriminated. **P9-PII-1 returned a CONCERN from both reviewers** — a sharp catch: the
one-shot re-scrub cleaned `hc-grc.local`, but the pre-commit hook re-captured the active session
*without* `ASSAY_SCRUB_HOSTS`, so `_hostname_patterns()` emitted no namespace rule and the host was
**re-introduced on the very commit** (the machine hostname auto-derives, so it stayed clean — the
asymmetry was the tell). Remediated by exporting `ASSAY_SCRUB_HOSTS` in `.githooks/pre-commit`
before capture and re-scrubbing; round-2 re-confirmation was **BOTH-CONFIRMED**, both reviewers
verifying the corpus stays 0 through a live re-capture and the bare project token is preserved.

Lesson recorded: a scrub rule gated on an env var must wire that var into the capture hook, or
re-capture silently re-leaks it.

## 6. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **563 passed, 5 skipped**; coverage
  floor enforced. CI watched to green before merge (per the pass-8 discipline and CI-1's control).

## 7. Convergence — not declared

Two HIGHs this pass (a security fix-regression and a CI-enforcement gap) on a codebase that is
otherwise stabilizing (the other three findings are medium/low). The privacy dimension produced
another adjacent vector (hostnames), now four passes running. No global convergence claim; pass 10
continues with the actual-CI-execution + fix-regression dimensions, watching for follow-ons of the
pass-9 fixes (the multi-host split, the hostname rule, the shared env parser).
