export const meta = {
  name: 'harden-pass9-batch20-review',
  description: 'Adversarially review batch-20 fixes (pass-9 findings) before commit',
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
  { unit: 'resume_run gate_id required', files: 'src/graph.py, tests/test_phase0/test_gates_hardening.py', intent: 'gate_id is now a REQUIRED keyword arg (was optional default None, which silently disabled the gate-correlation guard). resume_value always carries gate_id. Tests updated to pass gate_id="gate_1"; new test asserts TypeError when omitted.', verify: 'Confirm omitting gate_id now raises TypeError (kw-only no default); the guard at gates.py _run_gate is now always reachable; auto-deriving was correctly NOT done (would make the guard a no-op); all call sites (only tests) updated; no other src caller of resume_run exists.' },
  { unit: 'setuptools src-layout packaging', files: 'pyproject.toml', intent: 'Added [tool.setuptools.packages.find] where=["."] include=["src*"] so the wheel ships `src` as the package (its modules use relative imports requiring src as root); flat auto-discovery previously flattened src/ contents to top-level, breaking `from ...state` in a wheel and shipping tests/.', verify: 'Confirm the config ships `src` + subpackages (not flattened) and excludes tests; confirm it does not break the editable/dev or CI workflow (CI runs pytest from source via conftest path injection, does not pip-install the package). The author already built a wheel and imported it in a clean venv — deep relative imports resolved (only a missing numpy dep stopped it). Sanity-check the reasoning and flag any way this breaks dev/CI.' },
]
phase('Review')
const verdicts = await pipeline(UNITS, (u) => agent(
  `Adversarial reviewer, HC-GRC hardening batch 20 (pass-9 fixes). Repo ${REPO}, branch hardening/pass-9, UNCOMMITTED working tree. UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\nRead the real code read-only (you may run python -c / build checks against ${REPO}/.venv but do NOT mutate the repo). Cite file:line. resolves=false / introduces_regression=true on a real problem.`,
  { label: `review:${u.unit.slice(0, 26)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
))
phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || ['high', 'medium'].includes(v.severity_if_problem))
log(`${all.length} reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
