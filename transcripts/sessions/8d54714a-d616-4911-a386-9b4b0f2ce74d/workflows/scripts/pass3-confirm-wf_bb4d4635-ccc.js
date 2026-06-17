
export const meta = {
  name: 'pass3-confirm',
  description: 'Pass-3: 2-agent confirmation that each fix is appropriate AND complete',
  phases: [
    { title: 'Confirm', detail: '2 independent confirmers per fix' },
    { title: 'Tally', detail: 'collect CONFIRMED / CONCERN verdicts' },
  ],
}

const ROOT = '/Users/thomasjones/hc-assay'

// Implemented fixes this pass (id, file, summary, test). Reclassifications/declines included so
// confirmers can challenge them too.
const FIXES = [
  { id: 'F-001', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'run_study raises FirewallViolation when a claims source self-reported claim_fingerprint() disagrees with the canonical claim_set_fingerprint() of the claims it yields (no longer merely surfaced to the gate). Added public claim_set_fingerprint() in contracts/claims.py as the canonical scheme adapters must use.', test: 'test_lying_claim_fingerprint_is_rejected_not_merely_recorded, test_recorded_claim_fingerprint_is_engine_computed_over_scored_claims' },
  { id: 'F-002', kind: 'fix', file: 'src/assay_engine/methodology/hypothesis.py + confirm.py', what: 'Hypothesis.__post_init__ rejects predicted_direction not in {greater,less,None}; confirm_unit_level defensively re-validates a locked direction.', test: 'test_hypothesis_rejects_invalid_predicted_direction_at_construction, test_confirm_unit_level_revalidates_locked_direction_defensively' },
  { id: 'F-006', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'run_study records a terminal deterministic run_end provenance entry after trail.verify() passes (no wall-clock in the entry; duration goes to the tracker).', test: 'res_verify_ok (asserts kinds[-1]==run_end), test_verify_trail_default_still_verifies' },
  { id: 'F-008', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'versioner.put() failure is wrapped as IngestionError (was raw PermissionError).', test: 'test_versioner_failure_is_wrapped_as_ingestion_error' },
  { id: 'F-010', kind: 'fix', file: 'src/assay_engine/methodology/adjudication.py', what: 'standalone adjudicate() rejects an empty claim set with ValueError (consistency with the pipeline).', test: 'test_adjudicate_rejects_no_claims' },
  { id: 'F-018', kind: 'fix', file: 'src/assay_engine/methodology/discovery.py', what: 'discover_and_confirm rejects duplicate hypothesis_id and an empty discover() result.', test: 'test_discover_and_confirm_rejects_duplicate_hypothesis_ids, test_discover_and_confirm_rejects_empty_discovery' },
  { id: 'F-019', kind: 'fix', file: 'src/assay_engine/methodology/adjudication.py', what: 'adjudicate_with_baseline rejects two distinct claims mapping to the same hypothesis_id (would double-count the scorecard).', test: 'test_adjudicate_rejects_two_claims_mapping_to_one_hypothesis_id' },
  { id: 'F-021', kind: 'fix', file: 'src/assay_engine/pipeline.py + adjudication.py', what: 'confirm callables returning a non-Verdict raise FirewallViolation (was opaque AttributeError) on both the pipeline and adjudication paths.', test: 'test_confirm_held_out_returning_none_raises_firewall_violation, test_adjudicate_rejects_confirmer_returning_non_verdict' },
  { id: 'F-028', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'tracker.start_run failure emits a structured logging.warning (metrics were silently dropped).', test: 'test_tracker_start_run_failure_warns_and_continues' },
  { id: 'F-029', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'SLO metrics n_units, n_relations, n_claims, run_duration_s logged to the tracker.', test: 'test_tracker_receives_run_and_metrics_and_failures_dont_abort (asserts the 3 metric keys)' },
  { id: 'F-030', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'failure to record the run_failed entry is logged (was silently swallowed); original exception still re-raised.', test: 'test_run_failed_record_failure_is_logged_not_swallowed' },
  { id: 'F-042', kind: 'fix', file: 'src/assay_engine/pipeline.py + discovery.py', what: 'empty discover() return rejected on both the pipeline and standalone paths.', test: 'test_empty_discover_in_pipeline_raises, test_discover_and_confirm_rejects_empty_discovery' },
  { id: 'F-003', kind: 'fix', file: 'src/assay_engine/reasoning/seam.py', what: 'is_metered_anthropic_credential uppercases the key before the ANTHROPIC_ check (lowercase anthropic_api_key now scrubbed).', test: 'test_is_metered_credential_matches_shape (lowercase + mixed-case params)' },
  { id: 'F-007', kind: 'fix', file: 'src/assay_engine/orchestration/gatenode.py', what: 'make_gate_node warns when built without a recorder (silent GOVERNANCE-§3 audit gap).', test: 'test_make_gate_node_warns_when_no_recorder, test_make_gate_node_with_recorder_does_not_warn' },
  { id: 'F-023', kind: 'fix', file: 'src/assay_engine/observability/tracking.py', what: 'MlflowExperimentTracker.start_run terminates the created run FAILED if param-logging raises (no orphaned RUNNING run).', test: 'test_start_run_terminates_run_when_param_logging_fails' },
  { id: 'F-044', kind: 'fix', file: 'src/assay_engine/observability/tracing.py', what: 'bootstrap_tracing logs a warning on setup failure (was silent).', test: 'test_bootstrap_logs_warning_on_setup_failure' },
  { id: 'F-045', kind: 'fix', file: 'src/assay_engine/pipeline.py + provenance.py', what: 'StudyResult.persist_trail() writes a re-verifiable JSON; entries_to_records() deep-thaws nested FrozenDicts so to_records() output is JSON-serializable.', test: 'test_persist_trail_writes_a_reverifiable_chain' },
  { id: 'F-048', kind: 'fix', file: 'examples/minimal_study.py', what: 'example uses os.urandom(32) for the HMAC secret (no hardcoded shippable key).', test: 'test_example_uses_no_hardcoded_hmac_secret' },
  { id: 'F-049', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'run_study warns when the trail is unkeyed (secret=None) — tamper-evident but not forgery-resistant.', test: 'test_run_study_warns_when_trail_is_unkeyed' },
  { id: 'F-051', kind: 'fix', file: 'scripts/capture_transcripts.py', what: 'bearer-token scrub regex covers base64 chars + / =.', test: 'test_bearer_token_scrub_covers_base64_chars' },
  { id: 'F-004', kind: 'fix', file: '.github/workflows/ci.yml + requirements-core.lock', what: 'core + integration test lanes install --require-hashes from lockfiles (new requirements-core.lock, dev only) then --no-deps -e .', test: 'test_ci_test_lanes_install_hash_pinned_not_live_pypi, test_core_lockfile_is_pinned_and_hashed_and_extra_free' },
  { id: 'F-012', kind: 'fix', file: '.github/workflows/ci.yml', what: 'SBOM step drops || true; uploads use if-no-files-found: error.', test: 'test_sbom_generation_fails_loud' },
  { id: 'F-013', kind: 'fix', file: '.github/workflows/ci.yml', what: 'license gate scans the hash-pinned lockfile, not pip install -e .[all].', test: 'test_license_gate_scans_pinned_lockfile_not_live_resolution' },
  { id: 'F-014', kind: 'fix', file: '.github/workflows/ci.yml', what: 'all-checks umbrella job needs [core, integration, audit].', test: 'test_ci_has_umbrella_required_check' },
  { id: 'F-015', kind: 'fix', file: 'scripts/license_gate.py', what: 'license deny list includes prose forms SERVER SIDE PUBLIC / EUROPEAN UNION PUBLIC / AFFERO; behavioral test.', test: 'test_license_gate_behavioral_denies_strong_copyleft' },
  { id: 'F-031', kind: 'fix', file: '.github/workflows/ci.yml', what: 'uv pinned (uv==0.11.21) in the lockfile sync check.', test: 'test_ci_pins_uv_version' },
  { id: 'F-037', kind: 'fix', file: '.github/workflows/ci.yml', what: 'all GitHub Actions pinned to 40-char commit SHAs.', test: 'test_github_actions_are_sha_pinned' },
  { id: 'F-050', kind: 'fix', file: 'scripts/license_gate.py', what: 'license report opened via context manager (no leaked fd).', test: '(covered by behavioral license tests)' },
  { id: 'F-020', kind: 'fix', file: 'src/assay_engine/persistence/checkpoint.py', what: '_close_all_pools snapshots _OPEN_POOLS under _init_lock before iterating.', test: 'test_close_all_pools_snapshots_under_lock' },
  { id: 'F-025', kind: 'fix', file: 'src/assay_engine/persistence/checkpoint.py', what: 'removed write-only dead _INITIALIZED_CONN_STRS set.', test: 'test_initialized_conn_strs_dead_state_removed' },
  { id: 'F-033', kind: 'fix', file: 'src/assay_engine/persistence/checkpoint.py', what: '_migration_lock_timeout_ms() re-reads the env each bootstrap; 0 branch tested.', test: 'test_migration_lock_timeout_is_read_fresh_from_env, test_migration_lock_timeout_zero_skips_set_config' },
  { id: 'F-040', kind: 'fix', file: 'src/assay_engine/persistence/checkpoint.py', what: 'pool min/max size + connect_timeout env-tunable.', test: 'test_pool_size_and_connect_timeout_are_env_tunable' },
  { id: 'F-043', kind: 'fix', file: 'src/assay_engine/reasoning/seam.py', what: 'module ThreadPoolExecutor registers atexit shutdown(wait=False).', test: 'test_pool_atexit_shutdown_registered_for_reasoning_pool' },
  { id: 'F-022', kind: 'fix', file: 'src/assay_engine/reasoning/seam.py', what: '_run_with_retries gates retry ENTRY on the deadline (not just backoff sleeps).', test: '(behavior in seam; deadline gate added)' },
  { id: 'F-032', kind: 'fix', file: 'src/assay_engine/reasoning/seam.py', what: 'add_done_callback registration guarded so an interrupt in the attach window releases the _inflight slot.', test: 'test_submit_bounded_releases_slot_if_callback_registration_is_interrupted' },
  { id: 'F-026', kind: 'fix', file: 'tests/test_persistence.py', what: 'tests use monkeypatch.setenv; concurrent test resolves conn_str by thread identity (no env race).', test: 'test_concurrent_init_of_distinct_conn_strs_does_not_serialize' },
  { id: 'F-047', kind: 'fix', file: 'tests/test_persistence.py', what: 'FakeConn records pg_advisory_unlock; the best-effort unlock is asserted.', test: 'test_setup_dedups_sequentially_and_runs_ddl_on_the_locked_connection' },
  { id: 'F-054', kind: 'fix', file: 'tests/test_persistence.py', what: 'renamed the sequential dedup test to state it does NOT exercise the per-conn lock.', test: 'test_setup_dedups_sequentially_and_runs_ddl_on_the_locked_connection' },
  { id: 'F-034', kind: 'fix', file: 'src/assay_engine/_frozen.py', what: 'freeze_mapping returns an already-FrozenDict unchanged (idempotent; preserves cached hash).', test: 'test_freeze_mapping_is_idempotent_and_preserves_cached_hash' },
  { id: 'F-016', kind: 'fix', file: 'src/assay_engine/baseline/determinism.py', what: 'corpus_fingerprint streams JSON via JSONEncoder.iterencode into SHA-256; proven byte-identical (pinned-hash test).', test: 'test_corpus_fingerprint_is_byte_stable_across_the_streaming_change' },
  { id: 'F-017', kind: 'fix', file: 'src/assay_engine/methodology/confirm.py', what: '_resample_stability has a numpy fast-path with pure-Python fallback; verified identical results.', test: 'test_resample_stability_numpy_path_matches_pure_python' },
  { id: 'F-036', kind: 'fix', file: 'src/assay_engine/pipeline.py', what: 'run_study(verify_trail=False) opt-out for end-of-run re-verification; default stays True.', test: 'test_verify_trail_can_be_opted_out, test_verify_trail_default_still_verifies' },
  { id: 'F-038', kind: 'fix', file: 'tests/test_docs_drift.py', what: 'docs-drift guards made two-sided (exact GOVERNANCE off-box phrase, baseline attribution present, all five ADR-0006 extras + no "four extras").', test: 'test_data_sovereignty_is_qualified_for_high_stakes_tier, test_baseline_toolkit_scope_is_honest, test_adr0006_lists_the_baseline_extra' },
  { id: 'F-005', kind: 'reclassified-false-positive', file: 'src/assay_engine/observability/tracing.py + reasoning/seam.py', what: 'CLAIM (span does not set ERROR status) is FALSE: OTel start_as_current_span defaults record_exception=True + set_status_on_exception=True. Removed the redundant manual handling; kept a characterization test. Confirm this reclassification is correct.', test: 'test_otel_span_records_error_status_and_exception_on_raise' },
  { id: 'F-035', kind: 'scoped-decline', file: 'src/assay_engine/contracts/features.py', what: 'numpy fast-path DECLINED: np.asarray upcasts bool->numeric, so it cannot preserve the bool-exclusion contract (#149) nor numpy-float-scalar acceptance. Kept the pure-Python authoritative check (micro-optimized). Confirm the decline rationale is sound.', test: '(existing FeatureMatrix validation tests)' },
  { id: 'F-024', kind: 'deferred-by-mandate', file: '(transcripts/)', what: 'DEFERRED: the campaign mandate requires capturing transcripts into the repo on every commit; gitignoring them would contradict that explicit instruction. Public-release caveat already documented. Confirm this deferral is the right call given the mandate.', test: '(n/a)' },
]

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['fix_id', 'appropriate', 'complete', 'verdict', 'reasoning'],
  properties: {
    fix_id: { type: 'string' },
    appropriate: { type: 'boolean' },
    complete: { type: 'boolean' },
    verdict: { type: 'string', enum: ['CONFIRMED', 'CONCERN'] },
    reasoning: { type: 'string' },
  },
}

const prompt = (f, n) =>
  `You are confirmer #${n}, independent of all others. Confirm a production-hardening fix is BOTH appropriate (correctly addresses the issue, no regression, idiomatic) AND complete (fully closes it, with a discriminating regression test where a code change is involved).

Repo: ${ROOT}
Fix ${f.id} (${f.kind}) in ${f.file}
What was done: ${f.what}
Regression test(s): ${f.test}

Steps:
1. Read the actual changed file(s) at ${ROOT}.
2. Read the named regression test(s) and judge whether they actually discriminate the fix (would fail if the fix were reverted).
3. For a 'reclassified-false-positive', 'scoped-decline', or 'deferred-by-mandate' item: judge whether that JUDGMENT is correct and well-justified, not whether code changed.
4. Decide: appropriate? complete? Overall verdict CONFIRMED (both true) or CONCERN (something missing/wrong/under-tested).

Be skeptical and specific. Return your verdict.`

phase('Confirm')
const results = await pipeline(
  FIXES,
  f => parallel([
    () => agent(prompt(f, 1), { label: 'confirm-A:' + f.id, phase: 'Confirm', schema: VERDICT_SCHEMA }),
    () => agent(prompt(f, 2), { label: 'confirm-B:' + f.id, phase: 'Confirm', schema: VERDICT_SCHEMA }),
  ]),
  (verdicts, f) => {
    const [a, b] = verdicts.filter(Boolean)
    const bothConfirm = a && b && a.verdict === 'CONFIRMED' && b.verdict === 'CONFIRMED'
    return {
      fix_id: f.id,
      kind: f.kind,
      both_confirmed: bothConfirm,
      a: a ? { v: a.verdict, appropriate: a.appropriate, complete: a.complete, why: a.reasoning } : null,
      b: b ? { v: b.verdict, appropriate: b.appropriate, complete: b.complete, why: b.reasoning } : null,
    }
  }
)

phase('Tally')
const confirmed = results.filter(Boolean).filter(r => r.both_confirmed)
const concerns = results.filter(Boolean).filter(r => !r.both_confirmed)
log('CONFIRMED (both agents): ' + confirmed.length + ' / ' + results.length)
log('CONCERNS: ' + concerns.map(c => c.fix_id).join(', '))

return {
  total: results.length,
  confirmed_count: confirmed.length,
  concerns,
  all: results.filter(Boolean),
}
