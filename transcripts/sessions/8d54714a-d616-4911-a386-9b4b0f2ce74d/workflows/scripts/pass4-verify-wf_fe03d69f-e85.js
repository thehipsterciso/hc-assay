
export const meta = {
  name: 'pass4-verify',
  description: 'Pass-4: 2-agent blind verification of 24 findings',
  phases: [{ title: 'Verify', detail: '2 agents per finding' }, { title: 'Triage', detail: 'collect verdicts' }],
}
const ROOT = '/Users/[REDACTED]/hc-assay'
const FINDINGS = args

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['finding_id', 'confirmed', 'reasoning', 'severity_assessment'],
  properties: {
    finding_id: { type: 'string' },
    confirmed: { type: 'boolean' },
    reasoning: { type: 'string' },
    severity_assessment: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'false_positive'] },
  },
}

const vprompt = (f, n) =>
  `You are verifier #${n}, independent. Do NOT optimistically confirm. Read the ACTUAL code at ${ROOT} and independently determine whether this is a TRUE production-readiness problem in the CURRENT code (3 hardening passes already applied).

Finding ${f.id}: ${f.title}
File: ${f.file}:${f.line}
Description: ${f.description}
PoC: ${f.poc}
Suggested fix: ${f.suggested_fix}

Confirmed=true ONLY if: the problem exists as described in current code, the PoC is reproducible, and it is a genuine concern (not speculative, not already-handled elsewhere, not intended design). Set confirmed=false for speculative/already-fixed/by-design/PoC-doesn't-match-code. Be concrete and cite file:line.`

phase('Verify')
const results = await pipeline(
  FINDINGS,
  f => parallel([
    () => agent(vprompt(f, 1), { label: 'vA:' + f.id, phase: 'Verify', schema: VERDICT_SCHEMA }),
    () => agent(vprompt(f, 2), { label: 'vB:' + f.id, phase: 'Verify', schema: VERDICT_SCHEMA }),
  ]),
  (vs, f) => {
    const [a, b] = vs.filter(Boolean)
    const both = a && b && a.confirmed && b.confirmed
    const neither = (!a || !a.confirmed) && (!b || !b.confirmed)
    return {
      id: f.id, severity: f.severity, file: f.file, line: f.line, title: f.title,
      description: f.description, poc: f.poc, suggested_fix: f.suggested_fix, dimension: f.dimension,
      both_confirmed: both, neither_confirmed: neither, split: !both && !neither,
      a: a ? { c: a.confirmed, s: a.severity_assessment, why: a.reasoning } : null,
      b: b ? { c: b.confirmed, s: b.severity_assessment, why: b.reasoning } : null,
    }
  }
)
phase('Triage')
const confirmed = results.filter(Boolean).filter(r => r.both_confirmed)
const rejected = results.filter(Boolean).filter(r => r.neither_confirmed)
const split = results.filter(Boolean).filter(r => r.split)
log('confirmed=' + confirmed.length + ' rejected=' + rejected.length + ' split=' + split.length)
return { confirmed, rejected, split, all: results.filter(Boolean) }
