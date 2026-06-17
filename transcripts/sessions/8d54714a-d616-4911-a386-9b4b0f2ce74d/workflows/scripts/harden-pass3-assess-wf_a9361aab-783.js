export const meta = {
  name: 'harden-pass3-assess',
  description: 'Pass-3 adversarial production-readiness assessment (8 dimensions, read-only) + dedup',
  phases: [
    { title: 'Assess', detail: '8 independent assessors across distinct dimensions' },
    { title: 'Dedup', detail: 'merge + de-duplicate into a single ranked finding list' },
  ],
}

const REPO = '/Users/[REDACTED]/hc-assay'

const COMMON = `Repo: ${REPO} (branch harden/pass-3). It is a dataset-agnostic BLUEPRINT engine for rigorous empirical ML/NLP. Hard rules: the engine imports NO dataset/adapter specifics (ADR-0002); all engine computation/storage/observability + the bulk reasoning tier run on-box (ADR-0003) while the optional high-stakes tier is off-box by design; optional heavy backends are lazy-imported behind extras (ADR-0006).

This is the THIRD hardening pass. Passes 1 and 2 already fixed findings #101-#156 — read docs/hardening/PASS-1.md and docs/hardening/PASS-2.md and DO NOT re-report anything already fixed there. Use ${REPO}/.venv/bin/python and ${REPO}/.venv/bin/ruff if you want to run a PoC (read-only; do not commit). Be adversarial, precise, and concrete: every finding needs a real file:line, a crisp statement of the production-readiness defect, a PoC or mutation demonstrating it where possible, and a specific suggested fix. Prefer a few HIGH-confidence real defects over many speculative nits. If the area is genuinely clean, say so and return few/no findings.`

const DIMENSIONS = [
  { key: 'security-sovereignty', focus: 'Security & data-sovereignty: credential handling/scrubbing, loopback enforcement, any path that could send data off-box outside the documented high-stakes tier, subprocess sandboxing, injection, unsafe deserialization, secret leakage in logs/traces/exceptions.' },
  { key: 'concurrency-resource', focus: 'Concurrency, resource leaks, and lifecycle: thread/async safety, pool/connection/file-handle/subprocess leaks, lock scope, cancellation, atexit/cleanup ordering, re-entrancy, deadlock/livelock under load.' },
  { key: 'methodology-integrity', focus: 'Methodology integrity (the scientific core): the two firewalls, pre-registration content-binding + timestamp ordering, the measurement↔interpretation fence, the three-verdict mapping and its statistics (empirical p, stability, tails), scorecard accounting, provenance hash-chain integrity. Look for ways a misimplemented adapter or adversarial input corrupts a verdict or the provenance.' },
  { key: 'reliability-errors', focus: 'Reliability & error-handling: unnormalized exceptions across the engine↔adapter boundary, partial-failure states, silent error-swallowing that hides real failures, missing validation a misimplemented adapter would trip, error messages that leak secrets or mislead.' },
  { key: 'performance-scale', focus: 'Performance & scale: O(n^2)/quadratic or accidentally-materialized structures at corpus scale, unbounded memory, redundant recomputation, pathological inputs (huge corpora, many claims, deep nesting) that degrade or OOM.' },
  { key: 'ops-supplychain', focus: 'Ops, packaging & supply-chain: pyproject/extras correctness, lazy-import discipline (ADR-0006), CI workflow correctness, the lockfile/SBOM/license/dependabot machinery added in pass 2, version pinning, reproducibility, anything that breaks a clean install or a public release.' },
  { key: 'observability-provenance', focus: 'Observability & provenance: tracing/span/baggage correctness, experiment-tracker run lifecycle (start/end, leaks), provenance entry completeness/ordering, that the recorded trail actually lets an auditor reconstruct the run, MLflow/OTel wiring correctness vs best practice.' },
  { key: 'meta-test-quality', focus: 'META / test-quality (the pass-2 retrospective dimensions): (1) Artifact-vs-test fidelity — find any test targeting a config/doc artifact (YAML/TOML/markdown) that asserts against a COPY or loose substring instead of reading the shipped file (the #131/#145/#152 class). (2) Finding-completeness — pick prior fixes and check whether the finding\'s full Suggested fix was implemented or only partially (the #146/#147 class). (3) Concurrency-guard discrimination — find threaded tests whose assertion would pass even with the synchronization removed (the #143 class). Also: non-discriminating tests generally (pass with and without the code under test).' },
]

const FINDING_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'severity', 'location', 'defect', 'poc', 'suggested_fix'],
        properties: {
          title: { type: 'string' },
          severity: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
          location: { type: 'string', description: 'file:line(s)' },
          defect: { type: 'string', description: 'the concrete production-readiness defect' },
          poc: { type: 'string', description: 'PoC / mutation observed, or why not reproduced' },
          suggested_fix: { type: 'string' },
        },
      },
    },
  },
}

phase('Assess')
const raw = await parallel(
  DIMENSIONS.map((d) => () =>
    agent(`${COMMON}\n\nYOUR DIMENSION: ${d.focus}`, {
      label: `assess:${d.key}`,
      phase: 'Assess',
      schema: FINDING_SCHEMA,
    })
  )
)

const allFindings = raw
  .map((r, i) => ({ dim: DIMENSIONS[i].key, findings: (r && r.findings) || [] }))
  .flatMap((x) => x.findings.map((f) => ({ ...f, dimension: x.dim })))

phase('Dedup')
const DEDUP_SCHEMA = {
  type: 'object',
  required: ['deduped'],
  properties: {
    deduped: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'severity', 'location', 'defect', 'suggested_fix', 'dimensions'],
        properties: {
          title: { type: 'string' },
          severity: { type: 'string', enum: ['HIGH', 'MEDIUM', 'LOW'] },
          location: { type: 'string' },
          defect: { type: 'string' },
          poc: { type: 'string' },
          suggested_fix: { type: 'string' },
          dimensions: { type: 'array', items: { type: 'string' }, description: 'assessor(s) that raised it' },
        },
      },
    },
  },
}

const deduped = await agent(
  `${COMMON}\n\nYou are the synthesis/dedup step for pass-3 assessment. Here are the raw findings from 8 assessors as JSON:\n\n${JSON.stringify(allFindings)}\n\nMerge duplicates (same root defect reported by multiple assessors → one entry listing all dimensions), DROP anything already fixed in PASS-1.md/PASS-2.md (read them), DROP speculative nits with no real defect, and recalibrate severity conservatively. Return a single ranked list (HIGH first). Each entry must remain concrete (file:line, defect, suggested_fix).`,
  { label: 'dedup', phase: 'Dedup', schema: DEDUP_SCHEMA }
)

const list = (deduped && deduped.deduped) || []
return {
  raw_count: allFindings.length,
  deduped_count: list.length,
  by_severity: {
    HIGH: list.filter((f) => f.severity === 'HIGH').length,
    MEDIUM: list.filter((f) => f.severity === 'MEDIUM').length,
    LOW: list.filter((f) => f.severity === 'LOW').length,
  },
  findings: list,
}
