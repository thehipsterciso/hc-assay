export const meta = {
  name: 'harden-pass7-batch18-review',
  description: 'Adversarially review batch-18 fixes (genuine pass-7 findings) before commit',
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
const REPO = '/Users/[REDACTED]/hc-grc'
const UNITS = [
  { unit: '#27 CI runs full suite', files: '.github/workflows/test.yml', intent: 'CI now runs pytest tests/ (was tests/test_phase0/ only), so reasoning_client/observability/infrastructure tests gate merges. Backend-dependent tests are importorskip-guarded; Postgres service is provisioned.', verify: 'Confirm no test would HARD-FAIL in the lean CI env (requirements-ci.txt has no langchain-ollama/claude-agent-sdk/mlflow/phoenix). Check every test file under tests/ that lacks an importorskip guard imports only CI-available deps. Flag any that would error at collection/run in CI.' },
  { unit: '#7/#9/#8/#10 hypothesis_id dedup', files: 'src/state.py (_merge_hypotheses, _hypothesis_key)', intent: 'Reducer now keys on hypothesis_id then id, robust to None/non-dict.', verify: 'Confirm canonical field really is hypothesis_id (check src/agents), dedup now fires, non-dict/None entries preserved, latest-wins + order kept. Check the walrus usage is valid.' },
  { unit: '#3 rate-limit overwrite guard', files: 'src/reasoning_client.py (_t3_async)', intent: 'An is_error ResultMessage must not overwrite an already-captured 429 RateLimitEvent signal.', verify: 'Confirm the guard preserves 429, still captures non-rate errors when no prior 429, and the ordering logic is correct. Check the new tests construct real ResultMessage.' },
  { unit: '#1 saturation permanent', files: 'src/reasoning_client.py (_submit_bounded)', intent: 'Pool saturation now raises PermanentReasoningError so complete() does not retry it.', verify: 'Confirm PermanentReasoningError propagates through _with_timeout/_run_sync and _t2/_t3 (their except ReasoningError: raise preserves subtype) and complete() breaks immediately. Confirm slot-leak fix from pass-6 still intact.' },
  { unit: '#28 T2_BASE_URL loopback', files: 'src/reasoning_client.py (_t2_complete)', intent: 'Validate T2_BASE_URL is loopback before sending prompts to Ollama.', verify: 'Confirm require_local_uri handles http://host:port correctly, fires before the network call, and the default localhost passes. Check no circular import from the lazy config import.' },
  { unit: '#16/#17 config null + backend enum', files: 'src/infrastructure/config.py', intent: 'Reject null required values and invalid checkpointing.backend at load.', verify: 'Confirm null detection is correct (only required paths), backend enum is memory|postgres, real platform.yaml still validates, and the loopback/uri checks still run.' },
  { unit: '#6 advisory-lock unlock masking', files: 'src/checkpointer.py', intent: 'Wrap pg_advisory_unlock in try/except so it cannot mask a setup() exception.', verify: 'Confirm a setup() exception now propagates (not masked), unlock still attempted, and the advisory lock auto-release claim is sound.' },
  { unit: '#13 complete_json baggage fallback + #2/#14 llm.retries on failure + #18 psycopg<4', files: 'src/reasoning_client.py, requirements.txt', intent: 'complete_json reads run_id from baggage like complete(); failure span records llm.retries; psycopg pinned <4 in prod to match CI.', verify: 'Confirm baggage fallback mirrors complete() and is exception-safe; llm.retries on failure equals transient+rate attempts; psycopg bound now symmetric with requirements-ci.txt.' },
  { unit: 'new tests correctness', files: 'tests/test_reasoning_client.py, tests/test_phase0/test_state_reducers.py, tests/test_infrastructure/test_config_validation.py', intent: 'Tests for saturation-permanent, T2_BASE_URL, ResultMessage error/overwrite, llm.retries-on-failure, hypothesis_id dedup, config null/backend.', verify: 'Confirm assertions would fail if the fix were reverted; ResultMessage construction is valid; no tautologies; importorskip guards correct.' },
]
phase('Review')
const verdicts = await pipeline(UNITS, (u) => agent(
  `Adversarial reviewer, HC-GRC hardening batch 18 (pass-7 fixes). Repo ${REPO}, branch hardening/pass-7, UNCOMMITTED working tree. UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\nRead the real code (read-only). Cite file:line. resolves=false or introduces_regression=true on a real problem.`,
  { label: `review:${u.unit.slice(0, 28)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
))
phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || ['high', 'medium'].includes(v.severity_if_problem))
log(`${all.length} reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
