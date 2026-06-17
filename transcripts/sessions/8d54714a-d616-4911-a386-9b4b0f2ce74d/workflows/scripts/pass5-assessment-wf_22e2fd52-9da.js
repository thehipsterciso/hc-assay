
export const meta = {
  name: 'pass5-assessment',
  description: 'Pass-5 adversarial assessment of hc-assay (convergence-focused) + self-refute + dedup',
  phases: [
    { title: 'Assess', detail: '7 assessors incl. pass-5 dimensions' },
    { title: 'Refute', detail: 'disprove each finding' },
    { title: 'Dedup', detail: 'synthesize survivors' },
  ],
}

const ROOT = '/Users/thomasjones/hc-assay'

const DIMENSIONS = [
  {
    key: 'probabilistic-tests',
    prompt: `You are a flaky/probabilistic-test auditor (pass-5 priority). The hc-assay repo at ${ROOT} has ~520 tests over 4 hardening passes. Find tests whose pass/fail depends on UNCONTROLLED nondeterminism, so they pass or fail by luck rather than asserting the property:
- reliance on dict/set/frozenset iteration order, hash seed (PYTHONHASHSEED), or float/dict ordering without pinning;
- wall-clock / timing-threshold assertions (assert elapsed < X) that depend on machine speed;
- randomness without a fixed seed; ordering of concurrently-produced results;
- tests that assert on a value that is only SOMETIMES the buggy one (the G-004 class).
For each, show the nondeterministic dependency and how often it could mis-pass. Return JSON findings: id (PT-N), severity (critical/high/medium/low), file, line, title, description, poc, suggested_fix. Concrete file:line only.`,
  },
  {
    key: 'cross-tier-symmetry',
    prompt: `You are a cross-tier-symmetry auditor (pass-5 priority). Audit ${ROOT} for pairs of PARALLEL mechanisms that implement the same concern but were hardened ASYMMETRICALLY (one got a guard the other lacks). Examples to check: BULK vs HIGH_STAKES reasoning tiers (timeouts, cancellation, retry, error classification); bootstrap vs pooled DB connection (GUC/session state); pipeline vs standalone runners (discover_and_confirm vs run_study; adjudicate vs adjudicate_with_baseline) — type guards, empty checks, uniqueness guards; confirm_whole_corpus vs confirm_unit_level; the unkeyed vs keyed provenance trail. For each asymmetry, name what one side has that the other lacks and why it matters. Return JSON: id (X-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'methodology-integrity',
    prompt: `Adversarial methodology-integrity audit of ${ROOT}/src/assay_engine/methodology + pipeline.py (4 passes hardened). Look for any REMAINING firewall gap: discover/confirm leakage, claim-blindness, pre-registration enforcement on every path, verdict-mapping edge cases, scorecard/identity double-counting, stability scoring, post-hoc choices (HARKing) beyond direction (e.g. alpha, stability_threshold, test choice chosen after seeing data). Be concrete; reject speculation. Return JSON: id (M-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'security-concurrency',
    prompt: `Adversarial security + concurrency audit of ${ROOT} (4 passes hardened). Focus on what remains: off-box data paths, credential/PII scrubbing completeness, input validation at trust boundaries, races in checkpoint.py / reasoning pool, resource leaks on exception paths, context-manager/connection close. Return JSON: id (SC-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'reliability-errors',
    prompt: `Adversarial reliability/error-contract audit of ${ROOT} (4 passes hardened). Focus: any documented "Raises X" that doesn't hold; exception swallowing; edge cases (empty/NaN/Inf/single-element); partial-failure recovery; timeout/retry bounds; typed-vs-raw exceptions at public boundaries. Return JSON: id (R-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'ops-observability',
    prompt: `Adversarial ops/supply-chain + observability audit of ${ROOT} (4 passes hardened). Focus: CI gate completeness + reproducibility (.github/workflows/ci.yml), lockfile/SBOM/license/dependabot, span/run lifecycle on error paths, provenance completeness + persistence, metrics. Return JSON: id (O-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'docs-assertion-accuracy',
    prompt: `Adversarial assertion-vs-implementation + docs-accuracy audit of ${ROOT} (4 passes hardened). Find load-bearing code comments / docstrings / normative docs (README, CHARTER, GOVERNANCE, METHODOLOGY, ARCHITECTURE, ADRs) that claim a property the code does not deliver (idempotent/atomic/thread-safe/deterministic/O(1)/always/never/exactly-once), or over-claim capability/scope. Return JSON: id (A-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
]

const FINDING_SCHEMA = {
  type: 'object', required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object',
    required: ['id', 'severity', 'file', 'line', 'title', 'description', 'poc', 'suggested_fix'],
    properties: {
      id: { type: 'string' }, severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
      file: { type: 'string' }, line: { type: ['integer', 'string'] }, title: { type: 'string' },
      description: { type: 'string' }, poc: { type: 'string' }, suggested_fix: { type: 'string' },
    } } } },
}
const REFUTE_SCHEMA = {
  type: 'object', required: ['id', 'survives', 'reasoning'],
  properties: { id: { type: 'string' }, survives: { type: 'boolean' }, reasoning: { type: 'string' } },
}

phase('Assess')
const raw = await parallel(DIMENSIONS.map(d => () =>
  agent(d.prompt, { label: 'assess:' + d.key, phase: 'Assess', schema: FINDING_SCHEMA })))
const findings = raw.filter(Boolean).flatMap(r => r.findings)
log('Raw findings: ' + findings.length + '. Self-refuting...')

phase('Refute')
const refuted = await parallel(findings.map(f => () =>
  agent(
    `You are an adversarial refuter. ASSUME this finding is FALSE and try to prove it from the actual code at ${ROOT}. Find the code path/contract/test that makes the PoC impossible or moot. Only survives=true if you genuinely cannot disprove it.\n\n${f.id}: ${f.title}\nFile: ${f.file}:${f.line}\nDescription: ${f.description}\nPoC: ${f.poc}`,
    { label: 'refute:' + f.id, phase: 'Refute', schema: REFUTE_SCHEMA }
  ).then(v => ({ finding: f, refutation: v }))))
const survivors = refuted.filter(Boolean).filter(r => r.refutation && r.refutation.survives).map(r => r.finding)
const killed = refuted.filter(Boolean).filter(r => r.refutation && !r.refutation.survives)
log('Survived: ' + survivors.length + '/' + findings.length + ' (' + killed.length + ' refuted)')

phase('Dedup')
const DEDUP_SCHEMA = {
  type: 'object', required: ['deduplicated_findings'],
  properties: { deduplicated_findings: { type: 'array', items: {
    type: 'object',
    required: ['id', 'severity', 'file', 'line', 'title', 'description', 'poc', 'suggested_fix', 'dimension'],
    properties: {
      id: { type: 'string' }, severity: { type: 'string' }, file: { type: 'string' },
      line: { type: ['integer', 'string'] }, title: { type: 'string' }, description: { type: 'string' },
      poc: { type: 'string' }, suggested_fix: { type: 'string' }, dimension: { type: 'string' },
    } } } },
}
const deduped = survivors.length
  ? await agent(
      'Synthesize these self-refutation-surviving findings for hc-assay (4 passes hardened — expect few/low-severity, this is a convergence check). Deduplicate, rank by severity, assign IDs H-001.., record dimension, drop already-fixed/speculative.\n\n' + JSON.stringify(survivors, null, 2),
      { label: 'dedup:synthesis', phase: 'Dedup', schema: DEDUP_SCHEMA })
  : { deduplicated_findings: [] }

return {
  raw_count: findings.length, refuted_count: killed.length, survivor_count: survivors.length,
  refuted: killed.map(k => ({ id: k.finding.id, title: k.finding.title, why: k.refutation.reasoning })),
  total_deduped: deduped.deduplicated_findings.length, findings: deduped.deduplicated_findings,
}
