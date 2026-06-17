export const meta = {
  name: 'harden-pass5-batch16-review',
  description: 'Adversarially review batch-16 fixes (pass-5 findings) against the working tree before commit',
  phases: [
    { title: 'Review', detail: 'one adversarial reviewer per fix group' },
    { title: 'Synthesize', detail: 'aggregate verdicts' },
  ],
}

const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    unit: { type: 'string' },
    resolves: { type: 'boolean', description: 'fix correctly resolves the finding(s)' },
    introduces_regression: { type: 'boolean' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    severity_if_problem: { type: 'string', enum: ['none', 'low', 'medium', 'high'] },
    findings: { type: 'string', description: 'what you verified in the working tree; cite file:line; state any real defect' },
    recommended_action: { type: 'string', description: 'empty if sound as-is' },
  },
  required: ['unit', 'resolves', 'introduces_regression', 'confidence', 'severity_if_problem', 'findings', 'recommended_action'],
}

const REPO = '/Users/[REDACTED]/hc-grc'

const UNITS = [
  { unit: '#1 timeout-pool leak on submit() failure', files: 'src/reasoning_client.py (_submit_bounded)', intent: 'Increment _inflight, then submit() inside try/except that decrements on failure (and the done_callback decrements on normal completion). Prevents a leaked slot when pool.submit raises (e.g. after shutdown).', verify: 'Confirm no double-decrement (submit-failure path vs done-callback are mutually exclusive — callback only attached after successful submit), no underflow, lock held correctly, and BaseException (not just Exception) is caught. Check the new test test_submit_bounded_decrements_on_submit_failure actually proves it.' },
  { unit: '#2 complete_json records+propagates inner complete() errors', files: 'src/reasoning_client.py (complete_json)', intent: 'Wrap the complete() call in try/except ReasoningError that records on the complete_json span and re-raises, so backend errors (RateLimit/Permanent) are NOT retried as JSON-parse failures and ARE recorded on the parent span.', verify: 'Confirm a backend error propagates on first failure (call count 1), is distinct from the _extract_json parse-failure retry path below it, and the span records it. Confirm no behavior change for the happy path or the parse-retry path.' },
  { unit: '#6 temperature retry variation at high input', files: 'src/reasoning_client.py (complete_json temp formula)', intent: 'Replace min(1.0, temp+bump) with: attempt 0 = caller temp; else bump up unless >1.0, then bump down. Guarantees distinct in-range temps even at temperature=1.0.', verify: 'Mathematically check distinctness for temperature in {0.0,0.8,0.9,1.0} across MAX_RETRIES+1 attempts; confirm all stay in [0,1] and attempt 0 == caller temp. Check the new high-input test.' },
  { unit: '#9/#10 T3 stop_reason + agent_id on spans', files: 'src/reasoning_client.py (_t3_async, complete, complete_json)', intent: 'Capture stop_reason on successful ResultMessage into meta; record as llm.finish_reason in complete(); add hcgrc.agent_id to the complete_json parent span.', verify: 'Confirm stop_reason captured only when present, finish_reason set only when present, agent_id mirrors complete()s child-span pattern, no crash when fields absent.' },
  { unit: '#7/#8 checkpointer thread-safety', files: 'src/checkpointer.py (_init_lock, _register_pool_cleanup, setup-once guard)', intent: 'Add a module threading.Lock guarding the in-process check-and-set of _atexit_registered and _INITIALIZED_CONN_STRS so concurrent threads do not double-register atexit or double-run setup().', verify: 'Confirm both check-and-sets are inside the lock, the PG advisory lock still serializes cross-process, no deadlock (lock not held across unrelated blocking I/O beyond the intended setup), and setup still added to the set only after success.' },
  { unit: '#11 build_graph return annotation', files: 'src/graph.py', intent: 'Annotation changed StateGraph -> CompiledStateGraph, imported from langgraph.graph.state (verified importable there, not langgraph.graph).', verify: 'Confirm the import path is correct for the installed langgraph and matches the actual compile() return type; no runtime effect.' },
  { unit: '#15 eda_artifacts O(n+m) dedup', files: 'src/state.py', intent: 'Reducer now builds set(a) once for membership instead of x not in a per element; preserves order and dedup semantics.', verify: 'Confirm identical results to the old reducer (order preserved, dups dropped) and that the lambda is valid. Check the new reducer tests.' },
  { unit: '#3 phoenix loopback consolidation + phoenix_endpoint guard', files: 'src/infrastructure/observability/phoenix_setup.py, src/infrastructure/config.py', intent: 'phoenix_setup now imports the canonical require_loopback/LOOPBACK_HOSTS from config (removing its local copy) and phoenix_endpoint() validates loopback itself. config.require_loopback raises ConfigError (a ValueError subclass).', verify: 'Confirm exception type change ValueError->ConfigError does not break callers (bootstrap_observability catches broadly; ConfigError IS-A ValueError). Confirm launch_server_command + instrument_langchain still validate, phoenix_endpoint validates at source, and the _LOOPBACK_HOSTS alias import is fine. Check the new tests.' },
  { unit: '#4/#13 qdrant loopback guard', files: 'src/infrastructure/vector_store/qdrant_setup.py', intent: 'get_qdrant_client validates require_loopback(host) BEFORE importing qdrant_client, so the guard fires even without the package.', verify: 'Confirm guard precedes the optional import and the client construction, host passed correctly, no behavior change for loopback config. Check the new test that needs no qdrant_client.' },
  { unit: '#5/#14 mlflow loopback + config validation', files: 'src/infrastructure/tracking/mlflow_setup.py, src/infrastructure/config.py', intent: 'configure_mlflow calls require_local_uri(uri) before set_tracking_uri; config _validate_config rejects remote mlflow tracking_uri and non-loopback vector_store/phoenix/checkpointing hosts at load time.', verify: 'Confirm require_local_uri logic: sqlite:/// and bare paths pass, networked schemes require loopback host, file:// (no host) passes. Confirm config-load validation does not break the real platform.yaml (all localhost). Check the new tests.' },
  { unit: '#12 docker-compose loopback bind', files: 'docker-compose.yml', intent: 'Qdrant ports bind 127.0.0.1 only instead of 0.0.0.0.', verify: 'Confirm the compose syntax "127.0.0.1:6333:6333" is valid and matches the documented Qdrant ports; no other service exposed.' },
  { unit: 'version-bound parity', files: 'requirements-ci.txt', intent: 'psycopg floor raised to >=3.2,<4 (match prod); pytest>=8.2.2,<9 and pytest-cov>=5.0.0,<6 ceilings added so CI does not drift to pytest 9.x.', verify: 'Confirm the bounds match production majors and do not conflict with the langgraph-checkpoint / postgres pins already present; no impossible resolution.' },
  { unit: 'new test suite correctness (reasoning_client + observability)', files: 'tests/test_reasoning_client.py, tests/test_observability.py', intent: 'New tests for #1,#2,#6,#9,#274,T3-rate-event,_run_sync,sigterm,collision-warning,launch-server loopback.', verify: 'Read the new tests and confirm they genuinely exercise the intended behavior (not tautological/over-mocked), assertions are meaningful, and importorskip guards are correct. Flag any test that would pass even if the fix were reverted.' },
  { unit: 'new test suite correctness (config/checkpointer/state)', files: 'tests/test_infrastructure/test_config_validation.py, tests/test_infrastructure/test_config_and_tracking.py, tests/test_phase0/test_postgres_checkpointer.py, tests/test_phase0/test_state_reducers.py', intent: 'New tests for loopback config validation, qdrant/phoenix/mlflow runtime guards, checkpointer setup-once + connection-failure, state reducers.', verify: 'Confirm assertions are meaningful and would fail if the corresponding fix were reverted; confirm the typing.get_type_hints reducer-extraction approach is robust; confirm Postgres-gated tests are correctly gated.' },
]

phase('Review')
const verdicts = await pipeline(
  UNITS,
  (u) => agent(
    `Adversarial reviewer, HC-GRC hardening batch 16 (pass-5 fixes). Repo ${REPO}, branch hardening/pass-5, UNCOMMITTED working-tree changes — review the working tree.\n\n` +
    `UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\n` +
    `Read the real code (Read/Grep/Bash read-only; you may run python -c against ${REPO}/.venv). Default to skepticism. Cite file:line. Return the verdict; set resolves=false or introduces_regression=true if you find a real problem and describe it.`,
    { label: `review:${u.unit.slice(0, 32)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
  )
)

phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || v.severity_if_problem === 'high' || v.severity_if_problem === 'medium')
log(`${all.length} units reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
