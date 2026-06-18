# Hardening Pass 10 — actual-CI-execution + pass-9 fix-regression (4 HIGH)

Branch `harden/pass-10`. Same dimensions as pass 9 (actual CI execution + fix-regression audit +
standing security/privacy/methodology/reliability). Model: Claude Opus 4.8.

## 1. Assessment → self-refutation → verification

6 dimension assessors + adversarial self-refutation: **11 raw → 8 stood**. Deduping (one finding
surfaced by two dimensions) left **7 distinct survivors, ALL 2-agent verified TRUE_POSITIVE** —
**4 HIGH**.

## 2. Findings (7 confirmed)

| ID | Sev | Dimension | Finding |
|----|-----|-----------|---------|
| SEC-10-1 | HIGH | security | **libpq env-var bypass of the data-sovereignty guard.** `require_local_uri` validates the DSN *string*, but libpq also reads `PGHOST`/`PGHOSTADDR`/`PGSERVICE` from the environment — and `PGHOSTADDR` overrides even an explicit `host=localhost`, connecting to the off-box IP. Graph state leaves the box despite the guard passing (reproduced with psycopg/libpq). |
| P10-PII-1 | HIGH | privacy | The operator's **real LAN topology** (gateway `192.168.50.1`, host `192.168.50.134`, interface) leaked into committed transcripts from captured `route`/`lsof` output — no IP rule existed. |
| P10-CI-1 | HIGH | actual CI / fix-reg | **Fix-regression of CI-1.** `require_green_ci.sh` checked only the latest run's *conclusion*, never its **`headSha`** — so a stale green run (earlier commit) certified a newer, untested HEAD, and the documented `script && gh pr merge` decoupled the inspected branch from the merged SHA. |
| P10-MO-1 | HIGH | provenance | A `set`/`frozenset` payload value is hashable (so `freeze` accepts it) but does **not** round-trip through `to_records`→`from_records` (`unfreeze`→sorted list→re-freeze→tuple), so `verify_records` **silently failed** on a legitimately-recorded, rebuilt chain. |
| P10-MO-2 | MED | provenance | `from_records` raised a raw `AttributeError` on a non-mapping `payload` field, violating the typed-error (`ProvenanceError`) contract callers rely on. |
| P10-PII-2 | LOW | privacy / fix-reg | **Fix-regression of P9-PII-1.** The machine-hostname rule had no leading `\b`, so a short/common derived hostname matched as a **substring** (`host` redacting inside `localhost`). |
| REL-1 | LOW | reliability / fix-reg | **Fix-regression of pass-8 K-REL-1.** The SIGTERM handler missed the case where `signal.getsignal()` returns `None` (prior handler installed from C code) — neither callable nor `SIG_DFL` — so it flushed and returned, swallowing SIGTERM again. |

## 3. The fix-regression dimension caught a HIGH for the third pass running

P10-CI-1, P10-PII-2, and REL-1 are all follow-ons of passes 8–9's own fixes (the CI-gate script, the
hostname rule, the SIGTERM re-delivery). Pass 8 caught J-001 (regression of pass-6's CV-O-1); pass 9
caught K-SEC-9-1 (regression of pass-8's K-SEC-1); pass 10 caught three. Fixes keep creating adjacent
surface — the audit pays for itself every pass.

## 4. Fixes

- **SEC-10-1** — `_assert_local_libpq_env()` validates `PGHOST`/`PGHOSTADDR` (each comma-split
  element must be loopback or a local socket) and rejects `PGSERVICE`/`PGSERVICEFILE` (a service file
  can redirect off-box and can't be validated inline), called from `get_postgres_connection_string`.
- **P10-PII-1** — an RFC1918 redaction (`10/8`, `172.16/12`, `192.168/16`) with digit/dot lookarounds
  (catches the `\n`-glued form; never matches inside a longer number); loopback `127.x`, `0.0.0.0`,
  and public IPs are preserved. Corpus re-scrubbed — the operator's real LAN IPs are now 0.
- **P10-CI-1** — `require_green_ci.sh` fetches `headSha` and requires it equal `git rev-parse
  origin/<branch>`, failing closed when no completed run exists for the current commit.
- **P10-MO-1** — `ProvenanceEntry` rejects a payload containing any `(frozen)set` leaf loudly at
  record time (`ProvenanceError`); callers use a sorted list/tuple, which round-trips and digests
  identically. (Rejecting beats silent verification failure; `freeze`'s set→frozenset contract is
  unchanged for non-provenance uses.)
- **P10-MO-2** — `ProvenanceEntry` raises `ProvenanceError` when `payload` is not a `Mapping`.
- **P10-PII-2** — leading `\b` on the machine-hostname pattern.
- **REL-1** — `elif prior is None or prior == signal.SIG_DFL:` re-establishes `SIG_DFL` and
  re-delivers the signal; `SIG_IGN` still stays ignored, a callable prior still chains.

## 5. Confirmation (2 agents per fix)

All 7 findings 2-agent confirmed TRUE_POSITIVE during assessment. Three confirmation-time concerns
were raised and subsequently remediated:

- **SEC-10-1 (BOTH CONCERN)**: The initial fix blocked `PGSERVICE`/`PGSERVICEFILE` env vars but
  did not reject `service=`/`servicefile=` keywords appearing directly in the DSN string or URI
  query. Both forms load `~/.pg_service.conf` off-box. **Fixed**: `require_local_uri` now rejects
  both the URI query-param form (`?service=prod`) and the DSN keyword form (`service=prod`). Two
  new tests added; 2-agent re-confirmation: BOTH CONFIRMED-FIXED.
- **P10-PII-1 (BOTH CONCERN)**: The trailing lookahead `(?![\d.])` refused to match a sentence-
  final IP (`192.168.50.134.`) because `.` was in the class. **Fixed**: changed to `(?!\d)(?!\.\d)`
  — blocks `134.5` (dot-then-digit) but allows `134.` (sentence period). Missing regression test
  for the sentence-final form also added. 2-agent re-confirmation: BOTH CONFIRMED-FIXED.
- **P10-PII-2 (BOTH CONCERN)**: `test_scrub_hostname_does_not_over_redact_as_substring` asserted
  `"localhost" in out`, which spuriously passed via `"localhostname"` even when `localhost` was
  corrupted to `"local[REDACTED]"`. **Fixed**: changed to `"to localhost;" in out`. 2-agent re-
  confirmation: BOTH CONFIRMED-FIXED.

## 6. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **575 passed, 5 skipped**; coverage
  floor enforced. Merged only after `require_green_ci.sh` (now SHA-bound) confirms `all-checks` green.

## 7. Convergence — not declared

Four HIGHs this pass (two new security/privacy/provenance classes + the two re-surfaced via
fix-regression). Privacy produced yet another adjacent vector (network IPs), five passes running.
Security produced a new bypass class (libpq env) on top of the pass-9 multi-host one. No global
convergence claim; the actual-CI-execution + fix-regression dimensions continue.
