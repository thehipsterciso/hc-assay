export const meta = {
  name: 'harden-assess-verify',
  description: 'Production-readiness pass: 7 adversarial assessors -> dedup -> 2 independent verifiers per finding',
  phases: [
    { title: 'Assess' },
    { title: 'Verify' },
  ],
}

const REPO = '/Users/[REDACTED]/hc-assay'
const VENV = '/Users/[REDACTED]/hc-assay/.venv/bin/python'

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          title: { type: 'string' },
          dimension: { type: 'string' },
          severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
          file: { type: 'string' },
          line: { type: 'string' },
          description: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
        required: ['title', 'dimension', 'severity', 'file', 'description', 'suggested_fix'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    is_real: { type: 'boolean' },
    severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NOT_A_BUG'] },
    reasoning: { type: 'string' },
    evidence: { type: 'string' },
  },
  required: ['is_real', 'severity', 'reasoning', 'evidence'],
}

const COMMON = `Repo: ${REPO} (branch harden/pass-1). Venv (run PoCs): ${VENV}.
This is a dataset-agnostic ML/methodology engine being hardened for PRODUCTION. Hard constraints (do NOT flag as bugs): local-first/data-sovereign (loopback only, nothing leaves the box), no metered API (subscription OAuth only), engine never imports adapters/datasets (ADR-0002), optional heavy backends are lazy-imported (ADR-0006). Read real code; prefer findings you can back with a concrete repro/PoC against the venv. Report ONLY genuine production-readiness defects (not style/nits). Each finding needs a real file path and, where possible, a line.`

const DIMENSIONS = [
  { key: 'security-sovereignty', prompt: `${COMMON}\n\nDIMENSION: security & data-sovereignty. Hunt for: ways data could leave the box, a metered credential reaching a subprocess, loopback-guard bypasses (_local.py), injection (DSN/URL/path/JSON), unsafe deserialization, secret leakage in logs/errors/provenance, path traversal in the data versioner, SSRF via configurable endpoints, unsafe temp files. Try to actually break _local.require_local_uri / require_loopback_url and the credential scrubber.` },
  { key: 'correctness-concurrency', prompt: `${COMMON}\n\nDIMENSION: correctness & concurrency. Hunt for: race conditions / thread-safety bugs (reasoning ThreadPoolExecutor + _inflight counter, persistence ConnectionPool self-heal, registry lock, provenance trail if shared), non-atomic check-then-act, mutable shared state, idempotency holes in gate resume, off-by-one, incorrect comparisons, frozen-dataclass escapes. Probe under real threads where feasible.` },
  { key: 'methodology-integrity', prompt: `${COMMON}\n\nDIMENSION: methodology integrity (the product's whole value). Hunt for: any way to defeat Firewall A (claims reaching the blind baseline), Firewall B (discovery/confirm leakage), pre-registration (forge/replay a lock, content/id swap), the provenance trail (forge/reorder undetected, esp. unkeyed default), the measurement<->interpretation fence, the phase-order invariant, claim<->hypothesis<->verdict identity. Try concrete PoCs through run_study and the methodology primitives.` },
  { key: 'reliability-resources', prompt: `${COMMON}\n\nDIMENSION: reliability, error handling & resource management. Hunt for: resource leaks (threads, DB connections, file handles, the module-global ThreadPoolExecutor with no atexit shutdown), unbounded growth, missing/again-too-broad exception handling, raw exceptions escaping public APIs, missing timeouts, no graceful degradation, partial-failure inconsistency, retry storms, lack of backpressure. Trace shutdown/cleanup paths.` },
  { key: 'performance-scale', prompt: `${COMMON}\n\nDIMENSION: performance & scale. Hunt for: superlinear algorithms on corpus size (O(n^2)+), full-materialization of large data in memory, repeated recomputation, missing batching/streaming (qdrant upsert, baseline similarity matrix at scale, provenance canonicalization of huge payloads), pathological inputs that blow up CPU/memory. Estimate the breaking corpus size.` },
  { key: 'ops-packaging-supplychain', prompt: `${COMMON}\n\nDIMENSION: ops, packaging & supply chain. Hunt for: pyproject correctness (build, extras, metadata, license), dependency version ranges that admit known-bad/CVE versions, unpinned transitive risk, reproducible-install problems, CI gaps (lanes, the 3.14 matrix, format check actually run), py.typed shipping, missing runtime version guards, anything that breaks 'pip install' on a clean machine or a fresh Python. Try a clean install in a throwaway venv.` },
  { key: 'observability-provenance', prompt: `${COMMON}\n\nDIMENSION: observability & provenance completeness for production operation. Hunt for: actions that mutate state but are NOT recorded in the provenance trail (audit holes), tracing gaps (spans missing on real failure paths), no way to diagnose a failed/blocked run (partial trail lost on raise), metrics not emitted, log levels/PII in logs, inability to correlate a run end-to-end. Distinguish real audit gaps from already-documented scope.` },
]

phase('Assess')
log(`Pass 1 assessment: ${DIMENSIONS.length} adversarial assessors`)
const assessed = await parallel(
  DIMENSIONS.map((d) => () =>
    agent(d.prompt, { label: `assess:${d.key}`, phase: 'Assess', schema: FINDINGS_SCHEMA })
  )
)
const all = assessed.filter(Boolean).flatMap((r, i) =>
  (r.findings || []).map((f) => ({ ...f, _assessor: DIMENSIONS[i] ? DIMENSIONS[i].key : 'unknown' }))
)
const seen = new Map()
for (const f of all) {
  const k = `${(f.title || '').toLowerCase().trim()}::${(f.file || '').toLowerCase().trim()}`
  if (!seen.has(k)) seen.set(k, f)
}
const deduped = [...seen.values()]
log(`Assessors returned ${all.length} findings; ${deduped.length} after dedup`)

phase('Verify')
const verified = await parallel(
  deduped.map((f, idx) => () =>
    parallel(
      [1, 2].map((n) => () =>
        agent(
          `${COMMON}\n\nYou are independent VERIFIER #${n} of 2. A prior adversarial assessor reported this production-readiness finding:\n\nTITLE: ${f.title}\nDIMENSION: ${f.dimension}\nCLAIMED SEVERITY: ${f.severity}\nFILE: ${f.file} ${f.line || ''}\nDESCRIPTION: ${f.description}\nSUGGESTED FIX: ${f.suggested_fix}\n\nIndependently determine whether this is a TRUE production-readiness problem. Read the actual code; attempt a concrete PoC against the venv if applicable. Set is_real=false if it is a false positive, already-handled, or merely a documented/justified design choice given the hard constraints. Recalibrate severity. Provide your evidence (what you read/ran).`,
          { label: `verify:${idx}:${n}`, phase: 'Verify', schema: VERDICT_SCHEMA }
        )
      )
    ).then((vs) => ({ finding: f, verdicts: vs.filter(Boolean) }))
  )
)
const confirmed = verified.filter((v) => v.verdicts.length === 2 && v.verdicts.every((x) => x.is_real))
const rejected = verified.filter((v) => !(v.verdicts.length === 2 && v.verdicts.every((x) => x.is_real)))
log(`Verified: ${confirmed.length} confirmed (both agents), ${rejected.length} rejected/split`)
return { confirmed, rejected, total_findings: all.length, deduped: deduped.length }