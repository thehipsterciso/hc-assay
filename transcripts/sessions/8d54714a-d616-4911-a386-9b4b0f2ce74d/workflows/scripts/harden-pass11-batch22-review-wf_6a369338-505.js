export const meta = {
  name: 'harden-pass11-batch22-review',
  description: 'Adversarially review batch-22 fixes (pass-11 findings) before commit',
  phases: [{ title: 'Review' }, { title: 'Synthesize' }],
}
const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    unit: { type: 'string' }, resolves: { type: 'boolean' }, introduces_regression: { type: 'boolean' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    severity_if_problem: { type: 'string', enum: ['none', 'low', 'medium', 'high'] },
    findings: { type: 'string' }, recommended_action: { type: 'string' },
  },
  required: ['unit', 'resolves', 'introduces_regression', 'confidence', 'severity_if_problem', 'findings', 'recommended_action'],
}
const REPO = '/Users/[REDACTED]/hc-grc'
const UNITS = [
  { unit: 'ANTHROPIC_AUTH_TOKEN scrub (HIGH, ADR-0016)', files: 'src/reasoning_client.py (_scrubbed_env, _METERED_CREDENTIAL_ENV)', intent: '_scrubbed_env now strips BOTH ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN (both are metered SDK auth) while keeping CLAUDE_CODE_OAUTH_TOKEN (subscription auth).', verify: 'Confirm via the installed anthropic SDK source that ANTHROPIC_AUTH_TOKEN is indeed read for auth; confirm CLAUDE_CODE_OAUTH_TOKEN is NOT scrubbed (it must remain for the CLI); check there is no OTHER metered-credential env var the SDK reads that is still missed (e.g. ANTHROPIC_BASE_URL is not a credential). Confirm _scrubbed_env is actually used in the T3 subprocess path. Check the test covers both tokens + OAuth retention.' },
  { unit: 'timeout clamp (medium)', files: 'src/reasoning_client.py:95-96', intent: 'T2_TIMEOUT/T3_TIMEOUT clamped to max(1.0, float(...)) so a negative/zero override cannot raise "Timeout value out of range" at result()/wait_for().', verify: 'Confirm both clamped; defaults unchanged (120/300); 1.0 floor is sane; subprocess test sets negative env before import and asserts >=1.0. Any other unclamped numeric env that feeds a timeout/sleep?' },
  { unit: 'requirements.txt pytest parity (medium)', files: 'requirements.txt', intent: 'pytest/pytest-cov changed from exact == to >=,<9 / >=,<6 to match requirements-ci.txt and pyproject [dev]; honors the file header "floors not exact".', verify: 'Confirm the three files now agree for pytest/pytest-cov; no conflict; lint-tooling exact pins intentionally left.' },
  { unit: 'llm.temperature span (low) + tests', files: 'src/reasoning_client.py complete(), tests', intent: 'complete() span records llm.temperature; tests for scrub/timeout/temperature.', verify: 'Confirm temperature set unconditionally on the span; tests are meaningful and would fail if reverted (FakeTracer temp assert, subprocess timeout assert).' },
]
phase('Review')
const verdicts = await pipeline(UNITS, (u) => agent(
  `Adversarial reviewer, HC-GRC hardening batch 22 (pass-11 fixes). Repo ${REPO}, branch hardening/pass-11, UNCOMMITTED working tree. UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\nRead the real code read-only (inspect ${REPO}/.venv anthropic SDK source for the credential question). Cite file:line. resolves=false / introduces_regression=true on a real problem.`,
  { label: `review:${u.unit.slice(0, 28)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
))
phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || ['high', 'medium'].includes(v.severity_if_problem))
log(`${all.length} reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
