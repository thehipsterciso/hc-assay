export const meta = {
  name: 'harden-p4-batch15-review',
  description: 'Adversarially review batch-15 hardening fixes (12 issues) against the working tree',
  phases: [
    { title: 'Review', detail: 'one adversarial reviewer per fix' },
    { title: 'Synthesize', detail: 'aggregate verdicts' },
  ],
}

const VERDICT = {
  type: 'object',
  additionalProperties: false,
  properties: {
    issue: { type: 'string' },
    resolves_issue: { type: 'boolean', description: 'Does the fix actually resolve the cited finding?' },
    introduces_regression: { type: 'boolean', description: 'Does the fix break existing behavior or contracts?' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    severity_if_problem: { type: 'string', enum: ['none', 'low', 'medium', 'high'] },
    findings: { type: 'string', description: 'Concise: what you verified, and any defect/gap found. Cite file:line.' },
    recommended_action: { type: 'string', description: 'empty if the fix is sound as-is; else the concrete change needed' },
  },
  required: ['issue', 'resolves_issue', 'introduces_regression', 'confidence', 'severity_if_problem', 'findings', 'recommended_action'],
}

const REPO = '/Users/thomasjones/hc-grc'

const FIXES = [
  { issue: '#272', file: 'src/reasoning_client.py', intent: 'Bound the shared timeout ThreadPoolExecutor: track in-flight workers and fail fast with a distinct ReasoningError ("saturated") when all slots are leaked to hung backends, instead of silently queueing behind work that never starts. Also gives the T2 outer future timeout margin (T2_TIMEOUT+10) over the inner HTTP timeout so the inner one wins and frees the worker.', verify: 'Confirm _submit_bounded correctly counts in-flight via _inflight + lock, decrements on done-callback (including for leaked/timed-out workers only when they eventually return), raises before incrementing when saturated, and is used by BOTH _with_timeout and _run_sync. Check the done_callback cannot double-decrement or underflow. Check the T2 margin does not defeat the timeout.' },
  { issue: '#274', file: 'src/reasoning_client.py', intent: 'Set permission_mode="dontAsk" on ClaudeAgentOptions (T3) so the headless single-turn no-tools subprocess never waits on an interactive permission prompt.', verify: 'Confirm "dontAsk" is a valid PermissionMode in the installed claude_agent_sdk (check the package), that setting_sources=[] is still present, and that this cannot break the existing T3 path. Run a bash check against the installed SDK.' },
  { issue: '#280', file: 'src/reasoning_client.py', intent: '_record_usage now folds cache_read_input_tokens and cache_creation_input_tokens into the prompt and total token counts and emits the OpenInference cache slots, so llm.token_count.total no longer undercounts cached-prefix T3 runs.', verify: 'Confirm the arithmetic is correct when some fields are absent (None), that prompt/total are only set when at least one component exists, and that the OpenInference attribute names match convention. Check it does not crash on a usage object that is an SDK object (getattr path) vs dict.' },
  { issue: '#275', file: 'src/reasoning_client.py', intent: 'complete_json bumps decoding temperature on each retry (attempt 0 = caller temp, then min(1.0, temp+0.2*attempt)) so a parse-failure regeneration actually differs under deterministic T2 decoding (fixed seed + temp 0).', verify: 'Confirm the temperature is threaded complete_json -> complete -> _attempt -> _t2_complete -> _ollama and that the lru_cache key on _ollama includes temperature so a bump yields a distinct client. Confirm T3 is unaffected (ignores temperature). Confirm attempt 0 preserves caller temperature exactly.' },
  { issue: '#270', file: 'tests/test_reasoning_client.py', intent: 'New test asserts complete_json retries the full budget (MAX_RETRIES+1) on persistent non-JSON replies then raises ReasoningError.', verify: 'Confirm the test actually exercises the give-up branch and the call-count assertion is correct given complete_json/complete control flow (no hidden extra retries in complete()).' },
  { issue: '#276', file: 'src/checkpointer.py', intent: 'PostgresSaver.setup() (advisory lock + DDL + migration SELECT) now runs once per process per conn_str via the _INITIALIZED_CONN_STRS guard, instead of on every get_checkpointer() call.', verify: 'Confirm the guard is added to the set only AFTER a successful setup (so a failed setup retries next time), that the advisory lock still protects the first-time cross-process race, and that skipping setup on later calls is safe (schema already exists; each call still builds a fresh pool). Check for any concurrency hazard on the module-level set.' },
  { issue: '#267', file: 'src/nodes/gates.py', intent: 'gate_2 prerequisite-failure path is now idempotent: it only appends a gate_prerequisite_failure to failure_events when an identical deferred prereq-failure (same rationale) is not already recorded in gate_status[gate_2], avoiding duplicate audit events on re-entry of the non-terminal deferred path.', verify: 'Confirm the guard keys on the right fields (decision==deferred AND rationale match), that gate_coordinator_node actually stores rationale in the gate_status record (so the comparison works on re-entry), that a CHANGED unmet-prereq set still records a new event, and that the gate_status refresh is still returned. Check the new update dict typing.' },
  { issue: '#277', file: 'src/infrastructure/observability/phoenix_setup.py', intent: 'Bound the shutdown flush by setting OTEL_EXPORTER_OTLP_TRACES_TIMEOUT=2 (via setdefault) before register(), because the installed OTel BatchProcessor.force_flush ignores its timeout_millis arg so only the exporter-level timeout caps a downed-server hang at process exit.', verify: 'Confirm setdefault does not clobber an operator override, that the env var is read by the phoenix/OTLP exporter at register() time (set BEFORE register), and that 2s is a sane cap. Verify the claim that force_flush ignores timeout_millis in the installed SDK if feasible.' },
  { issue: '#278', file: 'src/infrastructure/observability/phoenix_setup.py', intent: 'After register(), if opentelemetry.trace.get_tracer_provider() is not the returned provider, log a warning — surfacing a global-provider collision that would silently drop Tier-3 reasoning_client spans (their only record).', verify: 'Confirm the identity check is correct (register returns the provider; global set can no-op), that it only warns (non-fatal), and that it does not itself perturb provider resolution. Check the import of trace is correct after the linter reordered imports.' },
  { issue: '#281', file: 'src/infrastructure/observability/phoenix_setup.py', intent: 'Install a SIGTERM handler (_install_sigterm_flush) that force_flushes + shuts down the provider then sys.exit(0), since atexit does not run on SIGTERM (launchd/kill/container-stop). Guarded to main-thread only.', verify: 'Confirm it only installs on the main thread (signal.signal constraint), that sys.exit(0) in the handler terminates cleanly, that it does not clobber SIGINT/KeyboardInterrupt handling, and that force_flush there is bounded by the #277 exporter timeout. Consider whether clobbering a pre-existing SIGTERM handler is a concern here.' },
  { issue: '#283', file: 'src/infrastructure/observability/phoenix_setup.py + scripts/infra/phoenix-service.sh', intent: 'Extend the ADR-0002 loopback guard from the client export host to the SERVER bind: launch_server_command() now validates via _require_loopback, and phoenix-service.sh write_plist() rejects any non-loopback host before writing the plist.', verify: 'Confirm BOTH code paths are guarded (launch_server_command and the shell write_plist; check launch_server_command in phoenix_setup is the only other server-launch path), that the shell case statement matches exactly localhost/127.0.0.1/::1 and exits non-zero otherwise, and that the existing instrument_langchain export guard still works via the shared _require_loopback helper.' },
  { issue: '#260', file: '.github/workflows/test.yml + requirements-ci.txt + tests/test_phase0/test_postgres_checkpointer.py', intent: 'DEVIATION FROM ISSUE: the issue proposed adding langgraph-checkpoint-sqlite + a SqliteSaver test, but that was proven infeasible (latest sqlite saver targets langgraph-checkpoint 2.x; the project pins postgres saver 3.x needing checkpoint 4.x — SqliteSaver imports but raises JsonPlusSerializer.dumps AttributeError at runtime). Instead: add a Postgres service container to CI, pin langgraph-checkpoint>=4,<5 and psycopg[binary,pool] in requirements-ci.txt, set HCGRC_POSTGRES_URL, and make the durability tests FAIL (not skip) in CI when Postgres is unreachable (GITHUB_ACTIONS guard).', verify: 'CRITICAL: independently validate the deviation rationale — is there truly no langgraph-checkpoint-sqlite version compatible with checkpoint 4.x? (check the installed stack / pip index if possible). Then confirm: the CI service config is correct (postgres:16, health check, port 5432, HCGRC_POSTGRES_URL format psycopg accepts), requirements-ci.txt now has psycopg[binary,pool] AND the checkpoint pin so the resolver cannot downgrade, the test _require_postgres() fails in CI but skips locally, and the in-body guard (vs skipif decorator) is correct. Flag any way CI could still silently skip or break.' },
]

phase('Review')
const verdicts = await pipeline(
  FIXES,
  (f) => agent(
    `You are an adversarial code reviewer for the HC-GRC hardening effort. Repo root: ${REPO} (current git branch has UNCOMMITTED working-tree changes — review the working tree as-is, not HEAD).\n\n` +
    `Review the fix for hardening issue ${f.issue}.\n\nFILE(S): ${f.file}\n\nINTENT OF THE FIX:\n${f.intent}\n\nWHAT TO VERIFY (adversarially — try to find a reason it is WRONG or INCOMPLETE or REGRESSES something):\n${f.verify}\n\n` +
    `Read the actual code in the working tree (use Read/Grep/Bash; you may run read-only bash like grep, python -c against ${REPO}/.venv, pip show — do NOT modify files, do NOT run the test suite in a way that mutates state). Verify the fix mechanically. Default to skepticism: if you cannot confirm it is correct, say so. Be concise and cite file:line. Return the structured verdict.`,
    { label: `review:${f.issue}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
  )
)

phase('Synthesize')
const problems = verdicts.filter(Boolean).filter(v =>
  !v.resolves_issue || v.introduces_regression || v.severity_if_problem === 'high' || v.severity_if_problem === 'medium'
)
log(`${verdicts.filter(Boolean).length} reviewed; ${problems.length} flagged for attention`)
return { total: verdicts.filter(Boolean).length, problems, all: verdicts.filter(Boolean) }
