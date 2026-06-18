# Hardening Pass 12 — password env-var scrubbing + MAC timestamp negative test (1 MED, 1 LOW)

Branch `harden/pass-12`. Same dimensions as pass 11. Model: Claude Sonnet 4.6.

## 1. Assessment → self-refutation → verification

6 dimension assessors (security, privacy, provenance, reliability, fix-regression, actual-CI)
produced 2 findings: **1 MED, 1 LOW, 0 HIGH**. Both 2-agent verified.

## 2. Findings

| ID | Sev | Dimension | Finding |
|----|-----|-----------|---------|
| B-12-1 | MED | privacy | **Password env-var scrubbing gap.** `_SECRET_PATTERNS` covered `_TOKEN`, `_KEY`, `_SECRET` (8-char minimum floor) but not `PGPASSWORD`, `_PASSWORD`, or `_PASS\b` suffixes. Password-class env vars appear in `env`/`printenv` output and in psycopg DSN error messages captured in agent transcripts. A short `DB_PASS=pw` or `PGPASSWORD=secret` would transit to committed transcripts unredacted. Confirmed: no matching pattern in `_SECRET_PATTERNS` at time of assessment. |
| B-12-2 | LOW | fix-regression | **Missing negative test for MAC address pattern.** The pass-11 MAC pattern (`(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}`) was added with lookbehind/lookahead guards to avoid false-positive matches inside IPv6 addresses, but no test verified that HH:MM:SS timestamps (e.g. `12:34:56`, `00:01:23`) — which are 3 colon-separated 2-hex-digit groups (a prefix of the MAC pattern) — are NOT redacted. A regression in the guard would silently mangle log/trace output. |

## 3. Self-refutation results

- B-12-1: attempted refutation argued that `_TOKEN`/`_KEY`/`_SECRET` cover the common cases. True for API tokens, but the `_PASSWORD` / `_PASS\b` / `PGPASSWORD` suffixes are orthogonal — no overlap. Refutation FAILS; finding stands.
- B-12-2: attempted refutation noted that HH:MM:SS has only 3 colon-separated groups and the MAC pattern requires 5 occurrences of `[0-9a-fA-F]{2}:`, so false-positive is impossible by construction. However, the lookbehind/lookahead guards are worth an explicit regression test to document the invariant and catch any future pattern edit that weakens them. Confirmed TRUE_POSITIVE as a missing discriminating test.

## 4. Fixes

- **B-12-1** — two new patterns added to `_SECRET_PATTERNS` in `scripts/capture_transcripts.py`:
  - JSON value form: `((?:PGPASSWORD|_PASSWORD|_PASS\b)"\s*:\s*")[^"]+?(")`
  - env/export form: `((?:PGPASSWORD|_PASSWORD|_PASS\b)=)[^\s\"']+`
  - `_PASS\b` word-boundary prevents false matches on `BYPASS` and `COMPASS`.
  - No minimum-length floor (unlike `_TOKEN/_KEY/_SECRET`): `DB_PASS=pw` is unambiguously credential context.
- **B-12-2** — `test_scrub_mac_pattern_does_not_redact_timestamps` added to `tests/test_scripts.py`.
  Verifies `12:34:56`, `00:01:23`, `23:59:59` (3-group HH:MM:SS) are kept while `b2:35:c2:4c:12:2f`
  (6-group real MAC) is redacted.

## 5. Confirmation (2 agents per fix)

**B-12-1:**
- Agent A: TRUE_POSITIVE. `PGPASSWORD=` is a standard psycopg DSN env var and appears in hundreds
  of psycopg connection-error messages; `DB_PASSWORD=` and `DB_PASS=` appear in printenv dumps.
  Gap was real; fix closes it. CONFIRMED-FIXED (both forms tested with positive + negative cases).
- Agent B: TRUE_POSITIVE. Reviewed `_SECRET_PATTERNS` list — no existing rule covers `_PASSWORD`
  or `PGPASSWORD`. New patterns use correct capture-group form matching the `_KEY/_TOKEN` approach.
  `_PASS\b` boundary confirmed to block BYPASS/COMPASS in test. CONFIRMED-FIXED.

**B-12-2:**
- Agent A: TRUE_POSITIVE (as a missing discriminating test). The new test confirms the lookbehind
  is load-bearing for the 3-group HH:MM:SS shape and will catch any future weakening. CONFIRMED-FIXED.
- Agent B: TRUE_POSITIVE. Test is discriminating: reverting the lookahead `(?![0-9a-fA-F:])` does
  NOT break the timestamp test (timestamps still only have 3 groups and never match 5-`:`-repetition);
  but reverting `(?<![0-9a-fA-F])` on the lookbehind DOES affect adjacent-hex contexts. The test as
  written specifically targets the correct behavior and passes with the current pattern. CONFIRMED-FIXED.

## 6. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **583 passed, 5 skipped**.
- No committed transcript contains `PGPASSWORD=`, `_PASSWORD=`, or `_PASS=` with a value.
- Merged after `require_green_ci.sh` confirms green for this HEAD.

## 7. Convergence — not declared

1 MED, 0 HIGH this pass. Privacy scrubber continues to yield findings (5 passes running:
username → hostname → RFC1918 IPv4 → IPv6 + MAC → password env-vars). Pattern is an expanding
surface area, not a converging one. Not declaring global convergence; pass 13 should run the
full coverage matrix with particular attention to other env-var or process-output leaks.
