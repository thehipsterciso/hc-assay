# Hardening Pass 4

Branch `harden/pass-4`. Protocol (see `CAMPAIGN.md`): ≥5 adversarial assessors → **adversarial
self-refutation** → dedup → 2-agent verify → fix + revert-discriminated test → 2-agent confirm →
remediate CONCERNs → merge → retrospective. Model: Claude Opus 4.8.

This pass added four assessment dimensions from the pass-3 retrospective: campaign-wide
**test-discrimination audit**, **assertion-vs-implementation**, **adversarial self-refutation**,
and **decline/deferral scrutiny**.

## 1. Assessment + self-refutation

8 adversarial assessors (led by the four new dimensions) produced **33 raw findings**. A new
**self-refutation stage** then tasked one agent per finding *solely with disproving it* before it
could enter the queue — it **refuted 7** (A-3, S-3, C-3, C-5, C-6, P-2, P-5), including two
over-eager re-flags of the pass-3 `_release` idempotency fix (unreachable: `_release` only ever
receives a stdlib `Future`) and an OTLP-endpoint override (the explicit `endpoint=` wins over the
env var). **26 survived → 24 deduped.**

## 2. Verification (2 agents, blind)

48 verifier agents. Outcome: **23 CONFIRMED, 1 REJECTED, 0 split.** The high confirm rate (23/24)
reflects that self-refutation had already removed the weak findings up front.

**Rejected:** G-008 (`_CONN_INIT_LOCKS`/`_POOLS_BY_CONN` unbounded growth) — both agents judged
the single-conn_str-per-process reality makes it a non-issue in practice.

## 3. Fixes (23 confirmed → all fixed)

Five batches, each with revert-discriminated regression tests (commits `d61bd4e`, `91dfb1a`,
`2eea958`, `c49261e`, `7dccfd8`).

### Batch A — methodology integrity
- **G-001 (high)** close the HARKing hole: `_resolve_direction` refuses a directionless *locked*
  whole-corpus hypothesis. The tail must be pre-registered; a confirm-time direction is a
  cross-check only, never a supply. (closes the gap pass-2 #24 only partially shut)
- **G-005 (med)** the contradiction/support stability asymmetry is documented as intentional (a
  contradiction is evidence *of* the opposite, not absence of evidence) and `contradiction_stability`
  is recorded in evidence for transparency.
- **G-006 (med)** confirm primitives warn on the presence-only (`authority=None`) gate.
- **G-011 (med)** `discover_and_confirm` type-guards the confirmer's return (matches #F-021).
- **G-017 (low)** documented that the unit-level verdict is governed by the caller flag.

### Batch B — concurrency, reasoning tier, serialization
- **G-002 (high)** `RESET lock_timeout` so the bootstrap session GUC doesn't leak into the pooled
  connection reused for all later checkpoint ops.
- **G-003 (high)** BULK tier's inner bound made *total* via an explicit `httpx.Timeout` (a bare
  float set every phase to BULK_TIMEOUT → connect+read could reach ~2× and leak the worker slot).
- **G-004 (high)** `unfreeze()` frozenset fallback sorts by a stable `(type name, repr)` key, not
  raw hash-seed-dependent iteration order (non-reproducible serialized output across processes).

### Batch C — provenance, observability, memory
- **G-009 (med)** `run_study` persists the trail as a JSON artifact correlated to the MLflow run.
- **G-010 (med)** numpy resample-stability uses `searchsorted` (O(R) memory) not an R×N matrix.
- **G-012 (med)** `from_records` raises typed `ProvenanceError` on a malformed record.
- **G-023 (low)** corpus unit-id set computed once, reused for split + feature validation.

### Batch D — CI / supply-chain reproducibility
- **G-015 (med)** the SBOM step applies the same allowlist as the gate (an accepted advisory no
  longer fails SBOM generation).
- **G-022 (low)** `pip-audit==2.10.1` / `pip-licenses==5.5.5` pinned (reproducible gate).
- **G-016 (med)** documented + scripted the lockfile regen Dependabot can't do
  (`scripts/regenerate_lockfiles.sh`); an auto-commit workflow was considered and rejected for
  dependabot-token / `pull_request_target` security reasons that can't be validated here.

### Batch E — egress, error contracts, PII, test discrimination
- **G-007 (med)** the transcript scrubber redacts the bare operator username everywhere.
- **G-018 (low)** egress denylist scrubs the entire `ANTHROPIC_*` namespace + `NODE_EXTRA_CA_CERTS`
  / `NODE_TLS_REJECT_UNAUTHORIZED`.
- **G-019 (low)** `Gate.evaluate` type-guards the precondition return (typed `GateError`).
- **G-020 (low)** `make_gate_node` raises on recorder failure rather than diverging graph state
  from the trail.
- **G-021 (low)** `build_baseline_artifact` names the offending `extra_input` key.
- **G-024 (low)** corrected the `cosine_similarity_matrix_array` docstring (O(size), not O(1)).
- **G-013 (med)** test-discrimination: cosine fast-path test now asserts numpy dispatch +
  numpy==pure agreement.
- **G-014 (med)** test-discrimination: SIGTERM flush handler asserted unconditionally on the main
  thread (was silently skippable).

## 4. Confirmation (2 agents) + CONCERN remediation

46 confirmation agents. Outcome: **22/23 CONFIRMED, 1 CONCERN.**

- **G-004 (CONCERN → remediated):** both agents agreed the fix is correct and deterministic, but
  the in-process test only discriminated a revert ~68% of the time (CPython randomizes the hash
  seed per process, so the buggy raw order sometimes coincided with the stable order). Added
  `test_unfreeze_frozenset_order_is_seed_independent_subprocess` (runs under `PYTHONHASHSEED=2`,
  where raw iteration is verified to differ) so a revert fails **every** run. (commit `f5a350f`)

## 5. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **521 passed, 5 skipped** (was
  501 at pass-4 open — +20 tests).
- 7 commits on `harden/pass-4`.

## 6. Retrospective → pass-5 assessment dimensions

- **Probabilistic-test detection.** The G-004 CONCERN was a test that *passed sometimes* — a
  flaky guard, not an absent one. New dimension: flag any test whose pass/fail depends on
  uncontrolled nondeterminism (hash seed, wall-clock, dict/set order, timing thresholds); such
  tests must pin or assert the property directly.
- **Cross-tier symmetry.** G-002/G-003 were asymmetries between two implementations of the same
  concern (bootstrap vs pooled connection; BULK vs HIGH_STAKES bounding). New dimension: for every
  pair of parallel mechanisms, diff their hardening and flag what one has that the other lacks.
- **Self-refutation worked — keep + widen it.** It removed 7/33 at near-zero cost and the verify
  stage then confirmed 23/24. Pass 5 keeps self-refutation and adds a symmetric step: one agent
  per *rejected/refuted* finding argues for *reinstating* it, to catch over-eager refutations.
- **Diminishing returns watch.** Pass 4 found 24 (vs pass 3's 54, pass 2's 33, pass 1's 22), and
  the survivors skew low-severity (4 high, all partial-closures or cross-tier asymmetries; the
  rest medium/low). If pass 5's confirmed-high count is ~0, the campaign is approaching
  convergence and the retrospective should say so explicitly rather than manufacturing findings.
