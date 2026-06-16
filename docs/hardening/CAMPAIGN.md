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
| 3 | harden/pass-3 | (assessing) | — | — | — | in progress |

## Pass-3 added assessment dimensions (from pass-2 retrospective)

- **Artifact-vs-test fidelity** — every test targeting a non-Python artifact (YAML/TOML/docs) must
  read *that file* and assert both corrected-content presence and stale-content absence (the
  #131/#145/#152 class).
- **Finding-completeness audit** — for each prior fix, diff the finding's *Suggested fix* against
  what was implemented; flag partial closures (the #146/#147 class).
- **Concurrency-guard discrimination** — re-run every threaded test with its synchronization
  removed and confirm it fails (the #143 class).
