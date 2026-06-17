# Production-Readiness Hardening Campaign

**Mandate (2026-06-16 19:37 UTC):** run autonomously for 48 hours assessing and hardening the
project to production-ready, in repeated passes, without stopping or asking for approval.

**Deadline:** 2026-06-18 ~19:37 UTC (48h from kickoff).

## Per-pass protocol (binding)

1. **Branch.** Each pass runs on its own branch `harden/pass-N`.
2. **Assess.** ≥5 independent adversarial agents assess production-readiness across distinct
   dimensions (security/data-sovereignty, correctness/concurrency, methodology integrity,
   reliability/error-handling/resource-leaks, performance/scale, ops/packaging/supply-chain,
   observability/provenance). Each returns concrete, file:line findings.
3. **Issue.** Each distinct finding becomes a tracked issue (GitHub issue + this log).
4. **Verify (2 agents).** Each issue is independently verified by **two** agents (blind to each
   other) confirming whether it is a TRUE production-readiness problem (true/false positive),
   with a PoC where possible. Only issues both confirm proceed to fix.
5. **Fix.** The maintainer (me) implements the fix with a regression test.
6. **Confirm (2 agents).** Each fix is confirmed by **two** independent agents as appropriate
   AND complete.
7. **Commit + merge.** New modules / developments / documentation are committed; the pass branch
   is PR'd and merged.
8. **Retrospective.** Before the next pass, assess how the prior pass (me + the agents) missed
   targets — what classes of problem were not surfaced — and feed that into the next pass's
   assessment dimensions.

All passes, findings, verdicts, fixes, confirmations, and retrospectives are documented under
`docs/hardening/` (one file per pass: `PASS-N.md`).

## Pass log

| Pass | Branch | Findings | Confirmed | Fixed | PR | Status |
|------|--------|----------|-----------|-------|----|--------|
| 1 | harden/pass-1 | 22 confirmed (#101-#122) | 22/22 (2-agent) | 22/22 fixed+confirmed | #123 | merged |
| 2 | harden/pass-2 | 33 confirmed (#124-#156) | 33/33 (2-agent) | 33/33 fixed; 21 CONFIRMED + 6 CONCERN→remediated, 0 rejected | #157 | merged |
| 3 | harden/pass-3 | 54 deduped; 49 confirmed (F-001..F-054), 5 rejected | 49/49 (2-agent) | 43 code/test fixed + 1 reclassified-FP (F-005) + 2 scoped-declines (F-035, F-016 sub) + 1 deferred-by-mandate-and-mitigated (F-024); confirm 40/46 + 6 CONCERN→remediated | #161 | merged |
| 4 | harden/pass-4 | 33 raw → 7 self-refuted → 24 deduped; 23 confirmed (G-001..G-024), 1 rejected | 23/23 (2-agent) | 23 fixed; confirm 22/23 + 1 CONCERN (G-004 test) → remediated | #162 | merged |
| 5 | harden/pass-5 | 30 raw → 4 self-refuted → 24 deduped; 19 confirmed (H-001..H-024), 1 rejected, 4 split | 19/19 (2-agent) | 19 fixed; confirm 19/19, 0 CONCERN | — | in progress |

**CONVERGENCE REACHED (pass 5):** confirmed-finding count 22→33→49→23→19; pass-5 had a single
high (H-001, a refinement of the #G-001 firewall, not a new class), ~half doc-honesty/test polish,
and 0 confirmation concerns. See PASS-5.md §6. The campaign continues to the deadline per mandate,
but the codebase is hardened-stable; further passes are expected to confirm convergence.

## Pass-3 added assessment dimensions (from pass-2 retrospective)

- **Artifact-vs-test fidelity** — every test targeting a non-Python artifact (YAML/TOML/docs) must
  read *that file* and assert both corrected-content presence and stale-content absence (the
  #131/#145/#152 class).
- **Finding-completeness audit** — for each prior fix, diff the finding's *Suggested fix* against
  what was implemented; flag partial closures (the #146/#147 class).
- **Concurrency-guard discrimination** — re-run every threaded test with its synchronization
  removed and confirm it fails (the #143 class).

## Pass-4 added assessment dimensions (from pass-3 retrospective)

- **Test-discrimination audit (campaign-wide)** — machine-revert-check EVERY new/changed test:
  revert its target fix and confirm the test fails. Re-run each prior pass's regression tests with
  their fixes reverted; flag any that still pass (the F-020/F-022/F-036/F-050 class — five of six
  pass-3 CONCERNs were non-discriminating tests that passed).
- **Assertion-vs-implementation** — audit load-bearing code comments and invariant-stating
  docstrings against what the code actually guarantees (the F-032 class — a comment claimed an
  idempotency property the code lacked).
- **Adversarial self-refutation** — before a finding enters the fix queue, one agent is tasked
  solely with DISPROVING it (assume false; find the code path making the PoC impossible). Catches
  the F-005 class (a false positive that survived 2-agent verification).
- **Decline/deferral scrutiny** — for every decline or deferral, an agent enumerates the PARTIAL
  mitigations a binary decline skips (the F-024 class).

## Pass-5 added assessment dimensions (from pass-4 retrospective)

- **Probabilistic-test detection** — flag any test whose pass/fail depends on uncontrolled
  nondeterminism (hash seed, wall-clock, dict/set order, timing thresholds); it must pin or assert
  the property directly (the G-004 class — a guard that passed only ~68% of the time).
- **Cross-tier symmetry** — for every pair of parallel mechanisms (e.g. bootstrap vs pooled
  connection, BULK vs HIGH_STAKES bounding), diff their hardening and flag what one has that the
  other lacks (the G-002/G-003 class).
- **Refutation-of-refutations** — keep self-refutation, but add a step where one agent argues to
  REINSTATE each refuted/rejected finding, to catch over-eager refutations.
- **Convergence check** — if pass 5's confirmed-high count is ~0, state explicitly that the
  campaign is converging rather than manufacturing low-value findings.
