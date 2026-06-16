export const meta = {
  name: 'harden-pass2-confirm-lean',
  description: 'Independent confirmation of pass-2 fixes #129-#156, one worktree confirmer per batch',
  phases: [{ title: 'Confirm', detail: 'one worktree-isolated confirmer per subsystem batch' }],
}

const REPO = '/Users/thomasjones/hc-assay'
const FINDINGS = '/tmp/pass2_items.json'

const BATCHES = [
  { key: 'supply-chain', issues: '#130,#131,#132,#145,#146,#147' },
  { key: 'persistence', issues: '#129,#143,#144' },
  { key: 'contracts', issues: '#133,#134,#135,#148,#149' },
  { key: 'methodology-integrity', issues: '#137,#138,#139,#140,#141' },
  { key: 'baseline-pipeline', issues: '#155,#156' },
  { key: 'docs', issues: '#136,#150,#151,#152,#153,#154' },
]

const SCHEMA = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['issue', 'fix_addresses_finding', 'test_discriminates', 'no_regression_or_scope_issue', 'verdict', 'notes'],
        properties: {
          issue: { type: 'string' },
          fix_addresses_finding: { type: 'boolean' },
          test_discriminates: { type: 'boolean' },
          no_regression_or_scope_issue: { type: 'boolean' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'CONCERN', 'REJECTED'] },
          notes: { type: 'string' },
        },
      },
    },
  },
}

function prompt(batch) {
  return `Independent confirmer on a production-hardening campaign. Repo: ${REPO} (branch harden/pass-2). You are in your OWN git worktree — revert/mutate freely to test discrimination.

Confirm the fixes for pass-2 findings: ${batch.issues}. Full details (title/desc/fix per "issue") are in ${FINDINGS} — read it; the fixes are already committed on this branch.

For EACH issue verify:
1. fix_addresses_finding — read the current code; confirm it genuinely resolves the described defect.
2. test_discriminates — REVERT just that fix in your worktree (keep the test), run the specific test via ${REPO}/.venv/bin/python -m pytest -q, confirm it FAILS, then restore. For docs/config findings, restore the stale string and confirm the guard fails.
3. no_regression_or_scope_issue — no broken dataset-agnosticism (ADR-0002), data-sovereignty (ADR-0003), or new bug.

Be adversarial and concrete: cite file:line and the exact pass→fail you observed. verdict=CONFIRMED only if all three hold; CONCERN if the test is weak/non-discriminating or scope is off; REJECTED if wrong/absent. One entry per issue.`
}

phase('Confirm')
const results = await parallel(
  BATCHES.map((b) => () =>
    agent(prompt(b), { label: `confirm:${b.key}`, phase: 'Confirm', schema: SCHEMA, isolation: 'worktree' })
  )
)

const all = results.filter(Boolean).flatMap((r) => r.verdicts || [])
return {
  reviewed: all.length,
  confirmed: all.filter((v) => v.verdict === 'CONFIRMED').map((v) => v.issue),
  concerns: all.filter((v) => v.verdict === 'CONCERN').map((v) => ({ issue: v.issue, notes: v.notes })),
  rejected: all.filter((v) => v.verdict === 'REJECTED').map((v) => ({ issue: v.issue, notes: v.notes })),
  nondiscriminating: all.filter((v) => v.test_discriminates === false).map((v) => ({ issue: v.issue, notes: v.notes })),
}
