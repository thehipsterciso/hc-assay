export const meta = {
  name: 'harden-pass8-batch19-review',
  description: 'Adversarially review batch-19 fixes (pass-8 findings) before commit',
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
  { unit: 'negative-backoff clamp', files: 'src/reasoning_client.py:107-111', intent: 'BACKOFF_BASE and RATE_LIMIT_BACKOFF clamped to max(0.0, float(...)) at config load, like MAX_RETRIES, so a negative env override cannot feed time.sleep() a negative value (uncaught ValueError).', verify: 'Confirm both are clamped, defaults unchanged (1.5 / 30), and the subprocess test genuinely sets negative env before import and asserts >=0. No other negative-arithmetic path remains (e.g. sleep call sites).' },
  { unit: 'is_available T2 loopback guard', files: 'src/reasoning_client.py is_available(Tier.T2)', intent: 'is_available probes T2_BASE_URL/api/tags; now require_local_uri(T2_BASE_URL) runs before the urlopen, mirroring _t2_complete (ADR-0002).', verify: 'Confirm the guard precedes the network call, raises on a remote host (not silently swallowed by the try/except around urlopen — it is OUTSIDE that try), and loopback default still returns normally. Check the new test.' },
  { unit: 'pyproject dev bounds', files: 'pyproject.toml', intent: 'pytest/pytest-cov dev extras get <9 / <6 ceilings to match requirements-ci.txt; ruff/black/pre-commit left floor-only (tooling, not in requirements-ci.txt).', verify: 'Confirm only pytest/pytest-cov were bounded, bounds match requirements-ci.txt, and nothing else regressed.' },
  { unit: 'new tests correctness', files: 'tests/test_reasoning_client.py', intent: 'Subprocess clamp test + is_available remote-rejection test.', verify: 'Confirm the subprocess test would FAIL if the clamp were removed (env set before import, asserts >=0), the is_available test asserts ConfigError, and neither leaks module state into other tests (no importlib.reload).' },
]
phase('Review')
const verdicts = await pipeline(UNITS, (u) => agent(
  `Adversarial reviewer, HC-GRC hardening batch 19 (pass-8 fixes). Repo ${REPO}, branch hardening/pass-8, UNCOMMITTED working tree. UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\nRead the real code read-only. Cite file:line. resolves=false / introduces_regression=true on a real problem.`,
  { label: `review:${u.unit.slice(0, 28)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
))
phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || ['high', 'medium'].includes(v.severity_if_problem))
log(`${all.length} reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
