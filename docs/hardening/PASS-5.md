# Hardening Pass 5 — convergence

Branch `harden/pass-5`. Protocol (see `CAMPAIGN.md`): ≥5 adversarial assessors → adversarial
self-refutation → dedup → 2-agent verify → fix + revert-discriminated test → 2-agent confirm →
remediate → merge → retrospective. Model: Claude Opus 4.8. This pass added four pass-4 dimensions:
**probabilistic-test detection**, **cross-tier symmetry**, **refutation-of-refutations**, and an
explicit **convergence check**.

## 1. Assessment + self-refutation

7 assessors (led by the new dimensions) → **30 raw findings**. Self-refutation refuted **4**
(PT-2, R-3, E, F) — e.g. a claim that `verdict_from_pvalue` skips statistic-finiteness validation
(it does validate, line 129) and a numpy-NaN divergence unreachable because the confirmers reject
NaN before the helper runs. **26 survived → 24 deduped: 1 high, 10 medium, 13 low.**

## 2. Verification (2 agents, blind)

48 verifiers. Outcome: **19 CONFIRMED, 1 REJECTED, 4 SPLIT (1-of-2).** Per the binding protocol,
only both-confirmed findings proceed.

**Rejected (both agents):** H-014 (module-global reasoning pool can't self-heal a vanished
worker) — judged speculative.

**Split (1-of-2, documented, NOT fixed this pass):**
- H-005 — HIGH_STAKES lacks BULK's output-length cap (one agent: the subscription tier is gated +
  timeout-bounded, so a runaway is already bounded).
- H-006 — `discover_and_confirm` lacks the `on_step` provenance hook `adjudicate_with_baseline`
  has (one agent: discovery records verdicts via the runner, so the hook is elective).
- H-019 — no CI `concurrency:` group (one agent: efficiency, not correctness).
- H-020 — pip-audit/SBOM re-fetch the advisory DB (one agent: network flakiness, not a defect).

These are candidates for a future pass; none is a correctness hole.

## 3. Fixes (19 confirmed → all fixed)

Two batches (commits `a9f3a48`, `011942b`), each with revert-discriminated tests.

### Batch A — methodology integrity / pre-registration firewall
- **H-001 (high)** close threshold-HARKing: `alpha` and `stability_threshold` are optional,
  digest-bound `Hypothesis` fields; the confirmers cross-check the confirm-time argument against
  the locked value (mismatch raises). The threshold analogue of pass-4's #G-001 direction guard.
  Non-breaking (unlocked thresholds keep caller-supplied behavior).
- **H-002 (med)** `powered` recorded in evidence + documented as a trusted caller obligation.
- **H-003/H-015/H-016 (med/low)** documented inherent caller-obligation / intentional-asymmetry
  boundaries (test_name can't be engine-verified; unit-level direction is advisory so a
  directionless lock is harmless there; Firewall B is enforced structurally in discover_and_confirm).

### Batch B — reliability, CI, observability, docs
- **H-004 (med)** malformed reasoning params → typed `PermanentReasoningError`.
- **H-007 (med)** license gate surfaces UNKNOWN/empty licenses as a warning (was silent).
- **H-008 (med)** CI `permissions: contents: read` (least privilege).
- **H-009 (med)** integration job verifies service containers are reachable (no vacuous green).
- **H-013 (low)** provenance-artifact tempfile unlinked after upload.
- **H-021/H-022 (low)** vectorstore: `query` validates `k`/skips payloadless points; `_int_env`
  names a bad env var.
- **H-018 (med)** transcript scrubber redacts the username in the project-dir slug at any length.
- **H-010/H-011/H-012/H-017/H-023/H-024 (med/low)** assertion-vs-implementation doc honesty:
  `stable_seed` uniqueness claim, gatenode recorder-asymmetry + "atomically"/idempotency scope,
  provenance keying, `redact_creds` precision, and the probabilistic-unfreeze-test note.

## 4. Confirmation (2 agents)

38 confirmation agents. Outcome: **19/19 CONFIRMED, 0 CONCERNS** — the cleanest confirmation of
the campaign. Every fix was independently judged appropriate AND complete, with the code-change
tests verified to discriminate on revert.

## 5. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **531 passed, 5 skipped** (+10
  tests vs pass-5 open).
- 3 commits on `harden/pass-5`.

## 6. Convergence determination

**The campaign has converged.** The evidence, per the pass-4 convergence-check dimension:

- **Confirmed-finding count is falling and flattening:** 22 → 33 → 49 → 23 → **19**.
- **Only ONE high this pass (H-001)**, and it is a *refinement* of the pre-registration firewall
  pass 4 already hardened for direction (#G-001) — not a new defect class. No new high-severity
  *class* of problem was found.
- **~Half of pass 5 was documentation-honesty and test-quality polish** (assertion-vs-implementation,
  probabilistic-test), not behavioral defects.
- **Self-refutation + 2-agent verify rejected/split 5 of 24**, and **2-agent confirm raised ZERO
  concerns** on 19 fixes — the assessors are now mostly surfacing nits the verifiers/confirmers
  agree are minor or by-design.
- The four split findings (H-005/H-006/H-019/H-020) are elective improvements, not correctness holes.

The remaining surface is tail polish (the split set + any future assertion/symmetry nits), not
production-readiness risk. Per the mandate the campaign continues until the deadline; a pass 6, if
run, should treat the split set as its candidate pool and is expected to confirm convergence rather
than surface new defect classes. No pass-6 retrospective dimensions are added: the pass-4 set
(probabilistic-test, cross-tier symmetry, refutation-of-refutations, convergence check) remains
the right lens for a converged codebase.
