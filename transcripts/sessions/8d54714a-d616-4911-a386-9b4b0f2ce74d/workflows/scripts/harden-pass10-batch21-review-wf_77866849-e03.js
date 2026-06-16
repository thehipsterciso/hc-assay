export const meta = {
  name: 'harden-pass10-batch21-review',
  description: 'Adversarially review batch-21 fixes (pass-10 findings) before commit',
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
const REPO = '/Users/thomasjones/hc-grc'
const UNITS = [
  { unit: 'checkpointer connection-string credential leak', files: 'src/checkpointer.py (_sanitize_conn_str + error message)', intent: 'The RuntimeError on connection failure interpolated the full conn_str (can contain user:password). Now it interpolates _sanitize_conn_str(conn_str) = scheme://host:port/db with userinfo stripped.', verify: 'Confirm _sanitize_conn_str strips user:password for postgresql://u:p@host:port/db, handles odd/empty inputs without raising, and the error no longer contains credentials. Check whether the trailing `Error: {e}` could still leak creds (does psycopg include the password in its exception text?). Verify the new tests prove no leak.' },
  { unit: 'complete_json parse_attempts on failure', files: 'src/reasoning_client.py (complete_json)', intent: 'json.parse_attempts now set on the failure path (MAX_RETRIES+1) too, mirroring the success path.', verify: 'Confirm it is set before record_exception, equals the actual attempt count, and the new FakeTracer test asserts it. No behavior change beyond the span attribute.' },
]
phase('Review')
const verdicts = await pipeline(UNITS, (u) => agent(
  `Adversarial reviewer, HC-GRC hardening batch 21 (pass-10 fixes). Repo ${REPO}, branch hardening/pass-10, UNCOMMITTED working tree. UNIT: ${u.unit}\nFILES: ${u.files}\nINTENT: ${u.intent}\nVERIFY (try to refute): ${u.verify}\n\nRead the real code read-only. Cite file:line. resolves=false / introduces_regression=true on a real problem.`,
  { label: `review:${u.unit.slice(0, 28)}`, phase: 'Review', schema: VERDICT, agentType: 'Explore' }
))
phase('Synthesize')
const all = verdicts.filter(Boolean)
const problems = all.filter(v => !v.resolves || v.introduces_regression || ['high', 'medium'].includes(v.severity_if_problem))
log(`${all.length} reviewed; ${problems.length} flagged`)
return { total: all.length, problems, all }
