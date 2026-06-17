# Hardening Pass 3

Branch `harden/pass-3`. Protocol: ≥5 adversarial assessors → dedup → 2-agent verify → fix +
revert-discriminated regression test → 2-agent confirm → remediate CONCERNs → merge → retrospective
(see `CAMPAIGN.md`). Model: Claude Opus 4.8.

## 1. Assessment

8 independent read-only adversarial assessors across distinct dimensions (security/sovereignty,
concurrency/resource, methodology integrity, reliability/errors, performance/scale,
ops/supply-chain, observability/provenance, meta/test-quality) — including the three new
dimensions seeded by the pass-2 retrospective (artifact-vs-test fidelity, finding-completeness
audit, concurrency-guard discrimination). Raw findings: **65**; after dedup/synthesis: **54**.

## 2. Verification (2 agents, blind)

108 verifier agents (2 per finding). Outcome: **49 CONFIRMED** (both agents), **5 REJECTED**
(neither), 0 split.

**Rejected (false positives — both agents disproved):**

| ID | Title | Why it's a false positive |
|----|-------|---------------------------|
| F-009 | asserts disabled under `python -O` | `StudyPlan` is a frozen dataclass validated in `__post_init__`; the fields cannot be mutated post-construction to reach the asserted state. |
| F-011 | `anyio.run()` from a running loop | `_high_stakes_complete` is only ever dispatched through the `ThreadPoolExecutor` boundary where no loop runs; no caller invokes it inside a coroutine. |
| F-027 | tracing bootstrap order | `OtelTracer` resolves the global provider lazily at span-open time, so bootstrap order before the first span is immaterial. |
| F-041 | `subset_corpus` called 4× | adapters receive an already-partitioned corpus; the double-traversal the finding posits requires an adapter that re-partitions, which the contract does not do. |
| F-046 | gate-node double recorder | LangGraph serializes node execution within a thread; the posited parallel-branch race does not occur for the gate node. |

## 3. Fixes (49 confirmed → 43 code/test fixes + 1 reclassification + 2 scoped declines)

Implemented across six batches (commits `af6ce68`, `2b07dfd`, `8608da4`, `9b613d6`, `82f58ca`,
`ba82429`) plus a remediation commit (`1eb2f58`). Every code fix carries a revert-discriminated
regression test.

### Methodology + pipeline integrity (batch 1)
- **F-001** enforce claim-fingerprint agreement (was recorded, not enforced; `auto_approve`
  laundered a lying source). New public `claim_set_fingerprint()` is the canonical scheme.
  *(partial-closure of pass-2 #137)*
- **F-002** validate `predicted_direction` at construction + defensively in `confirm_unit_level`
  *(partial-closure of pass-2 #128)*
- **F-006** terminal deterministic `run_end` provenance entry
- **F-008** `versioner.put()` failure → `IngestionError`
- **F-010** standalone `adjudicate()` rejects empty claim set
- **F-018** `discover_and_confirm` guards duplicate hypothesis_id + empty discover
- **F-019** `adjudicate_with_baseline` guards duplicate hypothesis_id
- **F-021** confirm callables returning non-`Verdict` → `FirewallViolation`
- **F-028/F-029/F-030** tracker start-failure warning; SLO metrics; run_failed-record-failure log
- **F-042** empty `discover()` rejected on both paths

### Security + observability seams (batch 2)
- **F-003** credential scrub case-insensitive (lowercase `anthropic_api_key`)
- **F-007** `make_gate_node` warns when no recorder (silent GOVERNANCE-§3 gap)
- **F-023** MLflow run terminated FAILED on param-log failure (no orphaned RUNNING)
- **F-044** `bootstrap_tracing` logs on setup failure
- **F-045** `StudyResult.persist_trail()` + `entries_to_records()` deep-thaw
- **F-048** example uses `os.urandom` secret
- **F-049** `run_study` warns on unkeyed trail
- **F-051** bearer-token scrub covers base64 chars

### CI / supply-chain (batch 3)
- **F-004** test lanes install `--require-hashes` from lockfiles (new `requirements-core.lock`)
- **F-012** SBOM fails loud (no `|| true`; upload `if-no-files-found: error`)
- **F-013** license gate scans the pinned lockfile, not live `.[all]`
- **F-014** `all-checks` umbrella job gates the merge
- **F-015** license gate denies SSPL/EUPL/AGPL prose forms (behavioral test)
- **F-031** uv pinned in the sync check
- **F-037** GitHub Actions pinned to commit SHAs
- **F-050** license-gate report opened via context manager

### Concurrency / resource / reasoning reliability (batch 4)
- **F-020** `_close_all_pools` snapshots under `_init_lock`
- **F-025** removed dead `_INITIALIZED_CONN_STRS`
- **F-033** migration-lock timeout re-read per bootstrap (+ 0-branch tested)
- **F-040** pool size + connect-timeout env-tunable
- **F-022** retry entry gated on the deadline
- **F-032** `add_done_callback` registration guarded; `_release` made per-future idempotent
- **F-043** reasoning pool registers atexit shutdown
- **F-026/F-047/F-054** test-quality: monkeypatch env + thread-keyed conn_str; unlock asserted;
  non-discriminating test renamed

### Performance (batch 5)
- **F-034** `freeze_mapping` idempotent (preserves cached hash)
- **F-016** `corpus_fingerprint` streams JSON into SHA-256 (proven byte-identical via pinned hash)
- **F-017** numpy fast-path for resample stability (proven identical to pure-Python)
- **F-036** `run_study(verify_trail=False)` opt-out; default stays on

### Test fidelity (batch 6)
- **F-038** docs-drift guards made two-sided (exact off-box phrase; baseline attribution; all five
  ADR-0006 extras)

### Reclassification + scoped declines (verified at fix time)
- **F-005 — FALSE POSITIVE.** Claim "span does not set ERROR status" is wrong: OTel
  `start_as_current_span` defaults `record_exception=True` + `set_status_on_exception=True`, so
  errors are auto-recorded. Caught by **revert-discrimination** (the test passed with the "fix"
  reverted). Removed the redundant manual handling; kept a characterization test pinning the SDK
  guarantee.
- **F-035 — SCOPED DECLINE.** A numpy whole-matrix validation fast-path cannot preserve the
  bool-exclusion contract (#149): `np.asarray` upcasts `bool`→numeric, and it would reject numpy
  float scalars `isinstance` accepts. Kept the authoritative pure-Python check (micro-optimized).
- **F-016 double-computation — SCOPED DECLINE (sub-item).** Closing the engine+builder double
  hash would need an invasive `BaselineBuilder` protocol change across all adapters; the two
  hashes are verified equal at the pipeline boundary, so it is correctness-safe as is.
- **F-024 — DEFERRED-BY-MANDATE + mitigated.** Gitignoring `transcripts/` contradicts the campaign
  mandate to capture transcripts on every commit. Adopted the mandate-compatible mitigation the
  confirmation surfaced: the capture scrubber now redacts operator PII (email + home-path
  username) while keeping transcripts committed and path structure intact.

## 4. Confirmation (2 agents) + CONCERN remediation

92 confirmation agents (2 per implemented item). Outcome: **40/46 CONFIRMED**, **6 CONCERN**
(every concern agreed the underlying fix was appropriate). Remediated in `1eb2f58`:

| ID | Concern | Remediation |
|----|---------|-------------|
| F-032 | comment claimed `_release` idempotent but it wasn't; real double-decrement window | made `_release` per-future idempotent; test asserts no double-decrement |
| F-020 | append-mutation test didn't discriminate (CPython lists don't raise on append-during-iter) | close() now REMOVES; assert all pools closed (fails on revert) |
| F-022 | no reasoning test for the deadline gate | added test isolating the entry gate from backoff |
| F-036 | opt-out test only checked chain validity, not the skip | spy `verify`; assert it is NOT called when `verify_trail=False` |
| F-050 | fd-leak invisible to return-code test | intercept module `open()`; assert handle `.closed` |
| F-024 | deferral abandoned an available PII mitigation | added email + home-path-username redaction to the scrubber |

All 6 remediations were revert-discriminated.

## 5. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **501 passed, 5 skipped**
  (was 446 at pass-3 open — +55 tests).
- 7 commits on `harden/pass-3`.

## 6. Retrospective → pass-4 assessment dimensions

What this pass (me + the agents) still missed, feeding pass 4:

- **Test-discrimination audit as a first-class gate.** Five of six CONCERNs were
  non-discriminating tests that *passed* — the regression test existed but did not fail on revert.
  Pass-2 added concurrency-guard discrimination; pass 4 generalizes it: **every** new/changed test
  this campaign must be machine-revert-checked, and a finding class is "re-run each prior pass's
  regression test with its target fix reverted; flag any that still pass."
- **Comment/claim accuracy.** F-032 shipped with a code comment asserting an idempotency property
  the code did not have. New dimension: **assertion-vs-implementation** — audit load-bearing code
  comments (and docstrings that state invariants) against what the code actually guarantees.
- **False-positive rate at the assessment stage.** 5/54 deduped findings were false positives that
  survived to 2-agent verification, and F-005 survived verification entirely (caught only at fix
  time). New dimension: **adversarial self-refutation** — each finding gets one agent tasked solely
  with disproving it (assume false; find the code path that makes the PoC impossible) before it
  enters the fix queue.
- **Decline/deferral scrutiny.** F-024's first classification under-scoped the remedy; the dissent
  found a mandate-compatible middle path. New dimension: for every decline/deferral, an agent must
  enumerate the *partial* mitigations the binary decline skips.
