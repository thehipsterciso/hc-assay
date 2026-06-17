export const meta = {
  name: 'harden-reconfirm-fixes',
  description: 'Re-confirm the 10 strengthened pass-1 fixes: 2 independent agents each (appropriate AND complete)',
  phases: [{ title: 'Reconfirm' }],
}
const REPO = '/Users/[REDACTED]/hc-assay'
const VENV = '/Users/[REDACTED]/hc-assay/.venv/bin/python'
const N = 10
const ITEMS = '/tmp/pass1_reconfirm.json'
const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    issue: { type: 'string' }, appropriate: { type: 'boolean' }, complete: { type: 'boolean' },
    reasoning: { type: 'string' }, evidence: { type: 'string' },
  },
  required: ['issue', 'appropriate', 'complete', 'reasoning', 'evidence'],
}
const COMMON = `Repo: ${REPO} (branch harden/pass-1). Venv: ${VENV}.
${ITEMS} is a JSON array of 10 pass-1 findings that were strengthened after a first confirmation pass found them 'appropriate but incomplete'. Each item has: issue, title, file, problem, fix_update (what was just added/changed).
Constraints (NOT bugs): local-first/data-sovereign, no metered API, engine imports no adapter, lazy optional backends.`
phase('Reconfirm')
log(`Re-confirming ${N} strengthened fixes with 2 independent agents each`)
const results = await parallel(
  Array.from({ length: N }, (_, i) => () =>
    parallel(
      [1, 2].map((n) => () =>
        agent(
          `${COMMON}\n\nYou are independent CONFIRMER #${n} of 2 for INDEX ${i} (0-based) in ${ITEMS}.\nRead that item (issue, problem, fix_update). Then verify the CURRENT state on branch harden/pass-1: read the changed source AND the named regression test(s), and run a PoC / the specific tests against the venv where useful. Decide: appropriate = the fix soundly addresses the root cause (no hack/over-claim); complete = it fully resolves the finding AND has a regression test that would actually catch a regression (a test that passes equally with/without the fix does NOT count). If the item documents a deliberately-deferred scope (e.g. #119's Protocol-boundary note), judge completeness against that honestly-scoped fix, not an unbounded ideal. Set either false with specifics if not met. Echo the issue number.`,
          { label: `reconfirm:${i}:${n}`, phase: 'Reconfirm', schema: VERDICT }
        )
      )
    ).then((vs) => ({ index: i, verdicts: vs.filter(Boolean) }))
  )
)
const ok = results.filter((r) => r.verdicts.length === 2 && r.verdicts.every((v) => v.appropriate && v.complete))
log(`Re-confirmed: ${ok.length}/${N}`)
return { reconfirmed: ok.length, total: N, results }