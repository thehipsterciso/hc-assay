export const meta = {
  name: 'harden-confirm-fixes',
  description: 'Pass-1 fix confirmation: 2 independent agents confirm each of 22 fixes is appropriate AND complete',
  phases: [{ title: 'Confirm' }],
}

const REPO = '/Users/[REDACTED]/hc-assay'
const VENV = '/Users/[REDACTED]/hc-assay/.venv/bin/python'
const N = 22
const ITEMS = '/tmp/pass1_confirm.json'

const VERDICT = {
  type: 'object',
  additionalProperties: false,
  properties: {
    issue: { type: 'string' },
    appropriate: { type: 'boolean' },
    complete: { type: 'boolean' },
    reasoning: { type: 'string' },
    evidence: { type: 'string' },
  },
  required: ['issue', 'appropriate', 'complete', 'reasoning', 'evidence'],
}

const COMMON = `Repo: ${REPO} (branch harden/pass-1, fixes applied vs main). Venv: ${VENV}.
The file ${ITEMS} is a JSON array of 22 pass-1 findings (each: issue, title, file, sev, problem, suggested_fix).
Constraints (NOT bugs): local-first/data-sovereign, no metered API, engine imports no adapter, lazy optional backends.`

phase('Confirm')
log(`Confirming ${N} fixes with 2 independent agents each`)
const results = await parallel(
  Array.from({ length: N }, (_, i) => () =>
    parallel(
      [1, 2].map((n) => () =>
        agent(
          `${COMMON}\n\nYou are independent CONFIRMER #${n} of 2 for finding INDEX ${i} (0-based) in ${ITEMS}.\nRead that item (its issue number, problem, suggested_fix, file). Then VERIFY THE APPLIED FIX on the current branch: read the changed source AND its regression test (git diff vs main, or just read the file + tests), and where useful run a PoC against the venv to confirm the original problem is actually resolved.\nReturn: appropriate = the fix correctly addresses the root cause in a sound way (not a hack/incomplete patch/over-claim); complete = the fix fully resolves the finding AND has a regression test that would catch a regression. Set either false if not, and say exactly what is missing. Echo the issue number in 'issue'.`,
          { label: `confirm:${i}:${n}`, phase: 'Confirm', schema: VERDICT }
        )
      )
    ).then((vs) => ({ index: i, verdicts: vs.filter(Boolean) }))
  )
)
const confirmed = results.filter(
  (r) => r.verdicts.length === 2 && r.verdicts.every((v) => v.appropriate && v.complete)
)
const problems = results.filter(
  (r) => !(r.verdicts.length === 2 && r.verdicts.every((v) => v.appropriate && v.complete))
)
log(`Confirmed: ${confirmed.length}/${N}; needs-attention: ${problems.length}`)
return { confirmed_count: confirmed.length, total: N, results }