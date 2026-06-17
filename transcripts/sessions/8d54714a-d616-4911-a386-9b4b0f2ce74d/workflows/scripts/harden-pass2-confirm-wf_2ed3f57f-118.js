export const meta = {
  name: 'harden-pass2-confirm',
  description: 'Two-agent independent confirmation of pass-2 fixes #129-#156 (revert-discriminated)',
  phases: [
    { title: 'Confirm', detail: 'two worktree-isolated confirmers per subsystem batch' },
  ],
}

const REPO = '/Users/[REDACTED]/hc-assay'
const FINDINGS = '/tmp/pass2_items.json'

const BATCHES = [
  { key: 'supply-chain', issues: '#130,#131,#132,#145,#146,#147',
    files: '.github/workflows/ci.yml, requirements.lock, tests/test_supply_chain.py' },
  { key: 'persistence', issues: '#129,#143,#144',
    files: 'src/assay_engine/persistence/checkpoint.py, tests/test_persistence.py' },
  { key: 'contracts', issues: '#133,#134,#135,#148,#149',
    files: 'src/assay_engine/methodology/verdict.py, src/assay_engine/pipeline.py, src/assay_engine/contracts/study.py, src/assay_engine/methodology/firewalls.py, src/assay_engine/contracts/features.py, src/assay_engine/observability/{tracing,tracking}.py, src/assay_engine/persistence/{versioning,vectorstore}.py, src/assay_engine/reasoning/seam.py, tests/test_contract.py' },
  { key: 'methodology-integrity', issues: '#137,#138,#139,#140,#141',
    files: 'src/assay_engine/pipeline.py, src/assay_engine/methodology/adjudication.py, src/assay_engine/methodology/confirm.py, src/assay_engine/methodology/fence.py, src/assay_engine/_frozen.py, tests/test_confirm.py, tests/test_contract.py, tests/test_pipeline.py' },
  { key: 'baseline-pipeline', issues: '#155,#156',
    files: 'src/assay_engine/baseline/determinism.py, src/assay_engine/pipeline.py, tests/test_baseline.py, tests/test_pipeline.py' },
  { key: 'docs', issues: '#136,#150,#151,#152,#153,#154',
    files: 'README.md, docs/CHARTER.md, docs/GOVERNANCE.md, docs/METHODOLOGY.md, docs/ARCHITECTURE.md, docs/decisions/ADR-0003-*.md, docs/decisions/ADR-0006-*.md, src/assay_engine/__init__.py, tests/test_docs_drift.py' },
]

const SCHEMA = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['issue', 'fix_addresses_finding', 'test_present', 'test_discriminates', 'no_regression_or_scope_issue', 'verdict', 'notes'],
        properties: {
          issue: { type: 'string' },
          fix_addresses_finding: { type: 'boolean' },
          test_present: { type: 'boolean' },
          test_discriminates: { type: 'boolean', description: 'revert the fix in this worktree; the regression test must then FAIL' },
          no_regression_or_scope_issue: { type: 'boolean' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'CONCERN', 'REJECTED'] },
          notes: { type: 'string', description: 'evidence: what you read, the revert you tried, the observed pass→fail' },
        },
      },
    },
  },
}

function prompt(batch, persona) {
  return `You are an INDEPENDENT confirmer (persona ${persona}) on a production-hardening campaign for the assay-engine repo at ${REPO} (branch harden/pass-2). You are in your OWN git worktree — you may freely revert/mutate to test discrimination; it will not affect anyone else.

Confirm the fixes for these pass-2 findings: ${batch.issues}.

Full finding details (title/desc/fix/verifier-notes, keyed by "issue") are in ${FINDINGS} — read it. Primary files changed for this batch: ${batch.files}.

For EACH issue, verify rigorously:
1. fix_addresses_finding — read the actual current code and confirm the fix genuinely resolves the described defect (not a cosmetic/partial change).
2. test_present — a regression test exists for it.
3. test_discriminates — THE KEY CHECK: actually REVERT the fix in your worktree (undo just that code change, keep the test), run the specific test with ${REPO}/.venv/bin/python -m pytest, and confirm it now FAILS. Then restore. If you cannot make it fail by reverting, test_discriminates=false and explain. For docs/config findings, "revert" = restore the stale string and confirm the guard test fails.
4. no_regression_or_scope_issue — the fix doesn't break the engine's dataset-agnostic rule (ADR-0002), data-sovereignty (ADR-0003), or introduce a new bug; scope is appropriate.

Use ${REPO}/.venv/bin/python for pytest and ${REPO}/.venv/bin/ruff if needed. Be adversarial and concrete — cite the file:line you read and the exact pass→fail you observed. verdict=CONFIRMED only if all four are true; CONCERN if the fix works but the test is weak/non-discriminating or scope is questionable; REJECTED if the fix is wrong or absent. Return one entry per issue.`
}

phase('Confirm')
const results = await parallel(
  BATCHES.flatMap((b) => [
    () => agent(prompt(b, 'A'), { label: `confirm:${b.key}:A`, phase: 'Confirm', schema: SCHEMA, isolation: 'worktree' }),
    () => agent(prompt(b, 'B'), { label: `confirm:${b.key}:B`, phase: 'Confirm', schema: SCHEMA, isolation: 'worktree' }),
  ])
)

const all = results.filter(Boolean).flatMap((r) => r.verdicts || [])
const byIssue = {}
for (const v of all) {
  ;(byIssue[v.issue] ||= []).push(v)
}
const summary = Object.entries(byIssue).map(([issue, vs]) => {
  const confirms = vs.filter((v) => v.verdict === 'CONFIRMED').length
  const concerns = vs.filter((v) => v.verdict === 'CONCERN')
  const rejects = vs.filter((v) => v.verdict === 'REJECTED')
  const nondiscrim = vs.filter((v) => v.test_discriminates === false)
  return {
    issue,
    confirmations: confirms,
    total_reviews: vs.length,
    two_agent_confirmed: confirms >= 2,
    concerns: concerns.map((v) => v.notes),
    rejects: rejects.map((v) => v.notes),
    nondiscriminating: nondiscrim.map((v) => v.notes),
  }
})
return {
  total_issues_reviewed: summary.length,
  fully_confirmed: summary.filter((s) => s.two_agent_confirmed && s.concerns.length === 0 && s.rejects.length === 0).length,
  needs_attention: summary.filter((s) => !s.two_agent_confirmed || s.concerns.length || s.rejects.length),
  all: summary,
}
