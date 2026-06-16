export const meta = {
  name: 'harden-pass6-batch17-review',
  description: 'Adversarially review batch-17 fixes (pass-6 findings) against the working tree before commit',
  phases: [{ title: 'Review' }, { title: 'Synthesize' }],
}

const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    unit: { type: 'string' },
    resolves: { type: 'boolean' },
    introduces_regression: { type: 'boolean' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    severity_if_problem: { type: 'string', enum: ['none', 'low', 'medium', 'high'] },
    findings: { type: 'string' },
    recommended_action: { type: 'string' },
  },
  required: ['unit', 'resolves', 'introduces_regression', 'confidence', 'severity_if_problem', 'findings', 'recommended_action'],
}

const REPO = '/Users/thomasjones/hc-grc'

const UNITS = [
  { unit: '#1 RateLimitEvent status discrimination', files: 'src/reasoning_client.py (_t3_async _drain)', intent: 'Only treat a RateLimitEvent as a fatal 429 when rate_limit_info.status == "rejected"; allowed/allowed_warning are ignored. Keep a generic status=="rejected" fallback for other message shapes.', verify: 'Confirm allowed/allowed_warning do NOT set result_error (no false backpressure), rejected DOES, the generic fallback still works, and the getattr chain is None-safe. Check the new/updated tests actually distinguish the statuses (class name must be RateLimitEvent for the type-name match).' },
  { unit: '#5 session.id on complete_json span', files: 'src/reasoning_client.py (complete_json)', intent: 'Set session.id = run_id on the complete_json span, mirroring complete().', verify: 'Confirm only set when run_id present; matches complete()s pattern; new test asserts it.' },
  { unit: '#3 atexit _safe_close', files: 'src/checkpointer.py', intent: 'Wrap each pool.close() in _safe_close so one failing close does not abort cleanup of the rest at exit.', verify: 'Confirm the registered handler now uses _safe_close, exceptions are swallowed, all pools still attempted. Check the new test proves the good pool closes despite a bad one.' },
  { unit: '#6/#11 checkpointer connection-string loopback', files: 'src/checkpointer.py (get_postgres_connection_string)', intent: 'Validate the resolved connection URI via require_local_uri — both the HCGRC_POSTGRES_URL env path and the config-built URL — so a remote host is rejected (ADR-0002). Validation of the built URL is OUTSIDE the try so it is not masked by the localhost fallback.', verify: 'Confirm a remote env URL raises ConfigError, a remote config host raises (not silently falls back to localhost), loopback passes unchanged, and the localhost default fallback on config-load failure still works. Check new tests.' },
  { unit: '#4 eda_artifacts within-batch dedup', files: 'src/state.py (_merge_artifacts)', intent: 'Reducer now dedups within the incoming batch as well as against existing, order-preserving, O(n+m).', verify: 'Confirm dups within b are dropped, cross-list dedup preserved, order preserved, and the Annotated field references the function. Check new test.' },
  { unit: '#2 remove pending from GateDecision', files: 'src/state.py', intent: "Removed unused 'pending' from the GateDecision Literal.", verify: "Confirm 'pending' is genuinely unused anywhere (grep), nothing initializes a gate to 'pending', and no type now references it. No runtime effect." },
  { unit: '#7 requirements.txt checkpoint pin', files: 'requirements.txt', intent: 'Added explicit langgraph-checkpoint>=4.1,<5 to match the postgres saver requirement and CI.', verify: 'Confirm the bound matches the installed postgres saver (needs >=4.1,<5) and is consistent with requirements-ci.txt; no conflict.' },
  { unit: 'new test correctness', files: 'tests/test_reasoning_client.py, tests/test_observability.py, tests/test_phase0/test_postgres_checkpointer.py, tests/test_phase0/test_state_reducers.py', intent: 'Tests for rate-limit status, session.id, safe-close, connection-string loopback, eda within-batch dedup, is_available network errors, bootstrap error recovery, concurrent setup-once.', verify: 'Confirm assertions are meaningful and would fail if the fix were reverted; the concurrency test genuinely exercises _init_lock; importorskip/Postgres gates correct; no tautologies.' },
]

phase('Review')
const verdicts = await pipeline(
  UNITS,
  (u) => agent(
    `Adversarial reviewer, HC-GRC hardening batch 17 (pass-6 fixes). Repo ${REPO}, branch hardening/pass-6, UNCOMMITTED working tree. UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\nRead the real code (read-only Read/Grep/Bash; python -c against ${REPO}/.venv ok). Default to skepticism, cite file:line. Return the verdict; resolves=false or introduces_regression=true if you find a real problem.`,
    { label: `review:${u.unit.slice(0, 30)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
  )
)

phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || ['high', 'medium'].includes(v.severity_if_problem))
log(`${all.length} units reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
