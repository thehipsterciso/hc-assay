# Hardening Pass 6 — convergence verification (and a correction)

Branch `harden/pass-6`. Intended as a lightweight convergence-verification pass: re-verify the
four pass-5 split findings and run a small fresh assessment to confirm the codebase had reached
hardened-stable. It did **not** fully confirm convergence — the fresh sweep found a real HIGH that
five prior passes missed. Model: Claude Opus 4.8.

## 1. Split-set re-verification (2 agents each)

The four pass-5 split (1-of-2) findings were re-verified with fresh blind pairs:

| ID | Finding | Re-verdict |
|----|---------|-----------|
| H-005 | HIGH_STAKES lacks BULK's output cap | **both reject** — HIGH_STAKES is hard-bounded by `anyio.fail_after` (real cancellation, frees the slot) + fixed-cost subscription; a token cap is elective. |
| H-006 | `discover_and_confirm` lacks `on_step` | **both reject** — the production GOVERNANCE-§3 path is `run_study` (records inline); the standalone runner records no trail at all. |
| H-019 | no CI `concurrency:` group | **both reject** — efficiency, not correctness. |
| H-020 | pip-audit/SBOM re-fetch advisory DB | **both reject** — network flakiness, not a defect. |

**0 of 4 proceeded** — confirming they were genuinely elective, exactly as pass-5 classified them.

## 2. Fresh convergence assessment — found a HIGH the convergence call missed

3 assessors + self-refutation → 3 findings, **all 2-agent confirmed**:

- **CV-O-1 (HIGH).** `capture_transcripts._copy_scrubbed` scrubbed **only `.jsonl`**; every other
  file — including the `.json` workflow/subagent transcripts under the session subtree — was copied
  RAW, so operator PII (email, username, paths) and credential-shaped secrets bypassed redaction
  entirely and were committed to `transcripts/`. **Every prior pass's scrubbing work (#F-024,
  #F-051, #G-007, #H-018) silently assumed `.jsonl` and never covered `.json`.** Fixed:
  `_copy_scrubbed` now decode-classifies and scrubs every text file (binary copied verbatim). The
  pre-commit re-capture re-scrubbed the working tree (verified: 0 raw-username occurrences across
  `transcripts/`). Git **history** still holds the old blobs — the same accepted tradeoff as F-024
  (private node; `git filter-repo` required before any public release; documented in
  `transcripts/README`).
- **CV-M-1 (medium).** Follow-on regression of pass-5 **#H-001**: `stability_threshold`'s
  confirm-time default of `0.9` was indistinguishable from a caller passing `0.9`, so a hypothesis
  that *locked* a threshold ≠ 0.9 always raised a spurious "contradicts pre-registered" error
  unless the caller restated it. Fixed: the confirm-time default is a `None` sentinel
  (locked-wins-else-supplied; fall back to 0.9 only when neither is given). The override-HARKing
  guard (#H-001) is preserved.
- **CV-S-1 (low).** Follow-on of **#H-022**: `ASSAY_TRACING_PORT` used a bare import-time `int()`;
  now parsed via `_int_env` (names the bad var). H-022 fixed the vectorstore port but not this one.

## 3. Confirmation (2 agents)

6 agents. **3/3 CONFIRMED, 0 CONCERNS.** All revert-discriminated (the binary-copy guard is a
regression guard, not a discriminator — acknowledged; the security-bearing scrub test discriminates).

## 4. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **535 passed, 5 skipped**.
- 2 commits on `harden/pass-6`.

## 5. Correction to the pass-5 convergence claim

**The pass-5 convergence declaration was premature.** It was right that *behavioral methodology*
findings had converged (the split set proved elective; methodology highs are now refinements), but
it generalized that to the whole codebase, and pass 6 found a HIGH on the **privacy/tooling
dimension** that the count-trend lens didn't predict. Two lessons:

1. **Convergence is per-dimension, not global.** A falling confirmed-count can mask a whole
   dimension (here, "does redaction cover *all* artifact types?") that no prior pass had probed at
   the right altitude. The methodology firewall was hammered five times; the transcript scrubber's
   *file-type coverage* was never the explicit target until pass 6.
2. **Two of three pass-6 findings were follow-on regressions of pass-5's own fixes** (#H-001,
   #H-022). Fixes create new surface; a pass should always re-audit the *previous* pass's changes
   specifically. (Pass 4's self-refutation already did this for findings; pass 7 should do it for
   *fixes*.)

## 6. Pass-7 dimensions (from this correction)

- **Per-dimension coverage matrix.** Before declaring convergence, enumerate the hardening
  dimensions (methodology, concurrency, security/PII, supply-chain, observability, error-contracts,
  docs, tests) and confirm each was the *explicit primary target* of at least one assessor in a
  recent pass — not merely "no findings this pass".
- **Fix-regression audit.** One assessor dedicated to the diff of the immediately-prior pass:
  every fix is new code; does it introduce a follow-on defect (the #H-001→#CV-M-1, #H-022→#CV-S-1
  class)?
- Retain self-refutation + the pass-4/5 dimensions.

Convergence is **not** re-declared here. Pass 7 should apply the coverage matrix and the
fix-regression audit; only if those come back clean is a convergence claim warranted.
