# Hardening Pass 7 — coverage matrix + fix-regression audit

Branch `harden/pass-7`. Two new dimensions, both added because pass 6 proved convergence is
**per-dimension, not global** and that fixes create new surface:

1. **Per-dimension coverage matrix** — probe EACH dimension explicitly (security/data-sovereignty,
   correctness/concurrency, methodology integrity, reliability/resource-leaks, ops/packaging/
   supply-chain, observability/provenance, privacy/PII) before any convergence claim, so no
   dimension is silently assumed clean by a count-trend lens (the pass-5 mistake).
2. **Fix-regression audit** — diff the prior pass's own changes for follow-on defects, because pass
   6 showed a fix (CV-O-1's "scrub all files") could itself introduce a HIGH regression.

Model: Claude Opus 4.8.

## 1. Findings (≥5 assessors + adversarial self-refutation → 2-agent blind verify)

7 confirmed (J-001..J-006 from the sweep; J-007 self-refuted/rejected), plus **J-008** found while
confirming J-002 (the privacy coverage probe):

| ID | Sev | Dimension | Finding |
|----|-----|-----------|---------|
| J-001 | HIGH | privacy (fix-regression) | **CV-O-1's own fix was fail-open.** The pass-6 "scrub every file" used strict UTF-8 decode to classify text-vs-binary; transcripts embed arbitrary subprocess stdout (latin-1/truncated multibyte) inside JSONL strings, so ONE stray byte routed the WHOLE file to the verbatim branch, re-leaking PII/secrets. Fixed: classify binary by an actual NUL byte; otherwise decode `errors="replace"` so redaction ALWAYS runs. |
| J-002 | HIGH | privacy | Operator full display name ("Thomas Jones", from `git log` author) left in cleartext — distinct PII the email/username rules miss. Fixed: `_display_name_patterns()` derives names from several sources and redacts them (+ bare name tokens, see §3). |
| J-003 | MED | supply-chain | Editable install fetched the **hatchling build backend live & un-hashed** from PyPI (unscanned build-time code-exec). Fixed: hashed `requirements-build.lock` + `--no-build-isolation --no-deps -e .` in all three lanes + a sync-guard diff. |
| J-004 | MED | concurrency | MLflow `_experiment_id` check-then-create **TOCTOU**: concurrent first-time `start_run` calls race; the loser's `RESOURCE_ALREADY_EXISTS` propagated, leaving `run_id=None` and silently dropping all metrics + provenance. Fixed: re-fetch on create race. |
| J-005 | MED | test-discrimination | `RateLimitError`/`PermanentReasoningError` both subclass `ReasoningError`, so `pytest.raises(ReasoningError)` did NOT discriminate a transient mapping from a rate-limit/permanent one. Fixed: `_assert_transient` asserts the value is not a decisive subclass. |
| J-006 | LOW | supply-chain | License gate ran `pip-licenses --with-system`, scanning system/tooling outside the shipped set (can spuriously fail or mask). Fixed: dropped `--with-system`. |
| J-008 | HIGH | privacy (coverage matrix) | Operator **GitHub handle** `thehipsterciso` leaked across **193 transcript files** (PR/issue URLs, `gh --repo <handle>/...`) — PII no rule covered (email needs `@`; username rule derives the home-dir name `thomasjones`, not the handle). Found by the privacy coverage probe while verifying J-002. |

## 2. The two new dimensions earned their place

- **Fix-regression audit caught J-001** — a HIGH fail-open regression of pass-6's *own* CV-O-1 fix.
  Without explicitly diffing the prior pass's change, a "scrub everything" fix that silently
  reverted to fail-open on the first non-UTF-8 byte would have shipped.
- **Coverage matrix caught J-008** — probing the privacy dimension explicitly (grep the committed
  corpus for every operator-identity vector, not just the ones prior fixes named) surfaced the bare
  GitHub handle that the email/username rules structurally cannot match.

## 3. Confirmation (2 agents per fix) + concern remediation

12 agents over J-001..J-006: **5/6 BOTH-CONFIRMED** (J-001, J-003, J-004, J-005, J-006), all
revert-discriminated. **J-002 returned CONCERN from both reviewers**: the full-name scrub was
correct but left the operator's **bare first/last name** in cleartext governance prose (256×
"Thomas approves …", "Thomas builds and governs …") — and one reviewer independently corroborated
the J-008 handle leak.

**Consolidated privacy remediation for the J-002 concern + J-008**, hardened across **three
adversarial confirmation rounds** — each round's 2-agent confirm found a real *adjacent* identity
vector the previous fix didn't cover, which is the privacy dimension behaving as a live surface:

| Round | Confirm verdict | New vector found | Fix |
|-------|-----------------|------------------|-----|
| 1 | both CONCERN | bare first/last name ("Thomas approves …", 256× prose) | `_display_name_patterns()` also emits a per-**token** pattern (len≥4, trailing `\b`); `Joneses` stays protected |
| 2 | both CONCERN | **lowercase** identity (`thomas@hcgrc` actor field, `thomas-jones`), handle **stem** (`hipsterciso-audience-profiles`) | `re.IGNORECASE` on name+handle patterns; emit the handle stem (drop a leading "the") |
| 3 | 1 confirm / 1 CONCERN | the **spaced source brand** ("The Hipster CISO") — handle de-spaced, reconstructable by concatenation with the redacted email | handle patterns (len≥8) become **separator-flexible** (`[\s._-]*` between each char) so spaced/hyphenated/dotted brand forms redact, while a common single token ("CISO") is **not** over-redacted (the whole ordered letter sequence must be present) |
| 4 | **both CONFIRMED** | — | — |

Mechanism (`scripts/capture_transcripts.py`):
- `_display_name_patterns()` — full-name + per-token, `re.IGNORECASE`, derived from `git log`
  author / `git config user.name` / `ASSAY_SCRUB_NAMES`.
- `_repo_handle_patterns()` (new) — derives the repo owner from `git remote -v` + `ASSAY_SCRUB_HANDLES`,
  expands to the "the"-stripped stem, and uses separator-flexible matching for len≥8. The repo name
  is preserved as legitimate provenance; the separator class is space/`._-` only, so unrelated
  prose cannot accidentally spell the handle.
- The committed corpus was **re-scrubbed in place** after each round. Final verification (both
  confirming reviewers ran it independently, case-insensitively): `grep` over `transcripts/` returns
  **0** for word-bound `thomas`, standalone `jones`, `hipsterciso`, `thomasjones`, `thomas@`/`thomas-`,
  and the spaced `hipster[sep]ciso` brand; `Joneses`, standalone `CISO`, and the provider word
  `protonmail` are correctly **preserved** (not PII / not over-redacted). The only residual `hipster`
  hits are this session's own grep-command meta-discussion and truncated `thehipster…` fragments —
  the common word, not the brand.
- Regression tests: `test_scrub_redacts_bare_name_tokens` (incl. lowercase actor tokens),
  `test_scrub_redacts_github_handle` (incl. stem + spaced brand + no-over-redaction of common tokens).

Git **history** still holds the old blobs — same accepted tradeoff as #F-024/#CV-O-1 (private node;
`git filter-repo` required before any public release; documented in `transcripts/README`).

## 4. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **543 passed, 5 skipped**.
- Branch `harden/pass-7`: fix commits + this remediation.

## 5. Convergence — explicitly NOT re-declared

The privacy/PII dimension has now yielded confirmed findings **three passes running** (CV-O-1 in
pass 6; J-001, J-002, J-008 in pass 7). Each fix on this dimension has either missed an adjacent
vector (full name → bare token → handle) or regressed (strict-decode fail-open). Per the pass-6
lesson, convergence is per-dimension and fixes create new surface — so this pass makes **no**
global convergence claim. The privacy dimension specifically remains an active surface and gets a
dedicated coverage probe again in pass 8. Other dimensions (methodology, concurrency, supply-chain)
returned only medium/low findings this pass, consistent with stabilization but not asserted closed.
The campaign continues to the deadline per mandate.
