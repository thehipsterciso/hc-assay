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
