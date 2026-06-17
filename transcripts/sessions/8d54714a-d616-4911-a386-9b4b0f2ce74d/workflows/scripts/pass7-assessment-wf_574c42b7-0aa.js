
export const meta = {
  name: 'pass7-assessment',
  description: 'Pass-7: per-dimension coverage matrix + fix-regression audit + self-refute + dedup',
  phases: [
    { title: 'Assess', detail: '8 dimension probes + 1 fix-regression audit' },
    { title: 'Refute', detail: 'disprove each finding' },
    { title: 'Dedup', detail: 'synthesize survivors' },
  ],
}

const ROOT = '/Users/[REDACTED]/hc-assay'

// Per-dimension coverage matrix (#pass-7): each assessor OWNS one dimension and must probe it
// explicitly — and, if it finds nothing, state what it checked so coverage is auditable.
const DIMENSIONS = [
  { key: 'methodology', prompt: `Dimension: METHODOLOGY INTEGRITY / pre-registration firewall. Probe ${ROOT}/src/assay_engine/methodology + pipeline.py exhaustively for any remaining firewall gap (discover/confirm leakage, claim-blindness, pre-registration enforcement on every path, verdict mapping, scorecard/identity double-counting, post-hoc/HARKing choices beyond direction+alpha+stability). 5+ passes hardened — expect little. If nothing, state exactly what you checked.` },
  { key: 'concurrency', prompt: `Dimension: CONCURRENCY / RESOURCE LEAKS. Probe ${ROOT} (checkpoint.py pool/locks/atexit, reasoning ThreadPoolExecutor slot accounting, context-manager/connection close on exception paths, unbounded caches). If nothing, state what you checked.` },
  { key: 'security-pii', prompt: `Dimension: SECURITY / DATA-SOVEREIGNTY / PII. Probe ${ROOT} for off-box data paths, credential/PII scrubbing COMPLETENESS (all artifact types, all code paths, all redaction patterns), input validation at trust boundaries. Note: pass-6 found .json transcripts bypassed scrubbing (CV-O-1) — look for any OTHER coverage gap of this class (e.g. the MANIFEST, filenames, other capture paths). If nothing, state what you checked.` },
  { key: 'supply-chain', prompt: `Dimension: SUPPLY-CHAIN / CI. Probe ${ROOT}/.github + scripts + lockfiles for gate completeness/reproducibility, least-privilege, SBOM/license/dependabot, pinning. If nothing, state what you checked.` },
  { key: 'observability', prompt: `Dimension: OBSERVABILITY / PROVENANCE. Probe ${ROOT} for span/run lifecycle on error paths, MLflow run termination, provenance completeness/persistence/keying, metrics. If nothing, state what you checked.` },
  { key: 'error-contracts', prompt: `Dimension: ERROR CONTRACTS / RELIABILITY. Probe ${ROOT} for documented "Raises X" that doesn't hold, exception swallowing, edge cases (empty/NaN/Inf/single), typed-vs-raw exceptions at public boundaries. If nothing, state what you checked.` },
  { key: 'docs-accuracy', prompt: `Dimension: DOCS / ASSERTION-VS-IMPLEMENTATION. Probe ${ROOT} code comments, docstrings, and normative docs for any claim the code doesn't deliver (idempotent/atomic/thread-safe/deterministic/O(1)/always/never/exactly-once) or scope over-claims. If nothing, state what you checked.` },
  { key: 'test-quality', prompt: `Dimension: TEST QUALITY / DISCRIMINATION. Probe ${ROOT}/tests for non-discriminating regression tests (pass even if the fix is reverted), probabilistic/flaky guards (hash-seed/timing/order), over-mocking, vacuous asserts, coverage holes in error paths. If nothing, state what you checked.` },
  { key: 'fix-regression', prompt: `FIX-REGRESSION AUDIT (#pass-7). Read the diff of the immediately-prior pass (pass 6) at ${ROOT}: git commits touching scripts/capture_transcripts.py (CV-O-1, scrub-all-text-files), src/assay_engine/methodology/confirm.py (CV-M-1, stability_threshold None sentinel), src/assay_engine/observability/tracing.py (CV-S-1, _int_env). Every fix is NEW code — does any introduce a follow-on defect (the #H-001→#CV-M-1 class)? E.g.: does scrubbing ALL text files now corrupt a file that must stay verbatim, or change a hash/manifest, or mangle JSON the engine later re-reads? Does the None-sentinel stability_threshold break any caller passing the old 0.9 default, or the digest/exploratory path? Does _int_env change import behavior? Be concrete; cite file:line.` },
]

const FIND = { type: 'object', required: ['findings'], properties: { findings: { type: 'array', items: {
  type: 'object', required: ['id', 'severity', 'file', 'line', 'title', 'description', 'poc', 'suggested_fix'],
  properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
    file: { type: 'string' }, line: { type: ['integer', 'string'] }, title: { type: 'string' },
    description: { type: 'string' }, poc: { type: 'string' }, suggested_fix: { type: 'string' } } } } } }
const REF = { type: 'object', required: ['id', 'survives', 'reasoning'], properties: { id: { type: 'string' }, survives: { type: 'boolean' }, reasoning: { type: 'string' } } }

phase('Assess')
const raw = await parallel(DIMENSIONS.map(d => () =>
  agent(d.prompt + ' Return JSON findings: id (P7-<dim>-N), severity, file, line, title, description, poc, suggested_fix. ONLY genuine reproducible defects — do not manufacture nits.', { label: 'assess:' + d.key, phase: 'Assess', schema: FIND })))
const findings = raw.filter(Boolean).flatMap(r => r.findings)
log('Raw findings: ' + findings.length + ' across ' + DIMENSIONS.length + ' dimension probes.')

phase('Refute')
const refuted = await parallel(findings.map(f => () =>
  agent(`Adversarial refuter: ASSUME this finding is FALSE; disprove it from the code at ${ROOT}. survives=true only if you genuinely cannot.\n${f.id}: ${f.title}\n${f.file}:${f.line}\n${f.description}\nPoC: ${f.poc}`,
    { label: 'refute:' + f.id, phase: 'Refute', schema: REF }).then(v => ({ f, v }))))
const survivors = refuted.filter(Boolean).filter(r => r.v && r.v.survives).map(r => r.f)
const killed = refuted.filter(Boolean).filter(r => r.v && !r.v.survives)
log('Survived: ' + survivors.length + '/' + findings.length + ' (' + killed.length + ' refuted)')

phase('Dedup')
const DEDUP = { type: 'object', required: ['deduplicated_findings'], properties: { deduplicated_findings: { type: 'array', items: {
  type: 'object', required: ['id', 'severity', 'file', 'line', 'title', 'description', 'poc', 'suggested_fix', 'dimension'],
  properties: { id: { type: 'string' }, severity: { type: 'string' }, file: { type: 'string' }, line: { type: ['integer', 'string'] },
    title: { type: 'string' }, description: { type: 'string' }, poc: { type: 'string' }, suggested_fix: { type: 'string' }, dimension: { type: 'string' } } } } } }
const deduped = survivors.length
  ? await agent('Synthesize these self-refutation-surviving findings for hc-assay (6 passes hardened — expect very few). Deduplicate, rank by severity, assign IDs J-001.., record dimension, drop already-fixed/speculative.\n\n' + JSON.stringify(survivors, null, 2), { label: 'dedup', phase: 'Dedup', schema: DEDUP })
  : { deduplicated_findings: [] }

return {
  raw_count: findings.length, refuted_count: killed.length, survivor_count: survivors.length,
  refuted: killed.map(k => ({ id: k.f.id, title: k.f.title, why: k.v.reasoning })),
  total_deduped: deduped.deduplicated_findings.length, findings: deduped.deduplicated_findings,
}
