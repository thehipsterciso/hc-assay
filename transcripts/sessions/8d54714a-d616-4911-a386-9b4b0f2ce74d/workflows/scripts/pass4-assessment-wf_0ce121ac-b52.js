
export const meta = {
  name: 'pass4-assessment',
  description: 'Pass-4 adversarial assessment of hc-assay + self-refutation + dedup',
  phases: [
    { title: 'Assess', detail: '8 assessors incl. pass-3 retrospective dimensions' },
    { title: 'Refute', detail: 'one agent tries to DISPROVE each finding' },
    { title: 'Dedup', detail: 'synthesize surviving findings' },
  ],
}

const ROOT = '/Users/thomasjones/hc-assay'

const DIMENSIONS = [
  {
    key: 'test-discrimination-audit',
    prompt: `You are a test-discrimination auditor (pass-4 priority dimension). The hc-assay repo at ${ROOT} has ~500 tests added across 3 hardening passes. Many are "regression tests" that may NOT actually discriminate their fix.

Your job: find tests that PASS even when the code they supposedly guard is broken/reverted.
- Read tests/ and the src they target. For each suspicious regression test, reason about whether reverting the targeted fix would make it fail. If NOT, it's a finding.
- Focus on: tests asserting only return codes/types when the fix is about side effects (fd close, logging, ordering); tests that mock the very thing under test; tests with vacuous assertions (assert truthy on possibly-empty); concurrency tests that pass without the lock; artifact tests (YAML/docs) asserting presence but not stale-absence.
- Also flag any prior-pass regression test whose target fix, if reverted, leaves the test green.

Return JSON findings: id (T-N), severity (critical/high/medium/low), file, line, title, description, poc (the revert that leaves the test green), suggested_fix. Only concrete, file:line-grounded findings.`,
  },
  {
    key: 'assertion-vs-implementation',
    prompt: `You are an assertion-vs-implementation auditor (pass-4 priority dimension). Audit ${ROOT} for load-bearing code COMMENTS and invariant-stating DOCSTRINGS that claim a property the code does not actually guarantee.

- Read src/assay_engine/ and compare each strong claim ("idempotent", "thread-safe", "atomic", "deterministic", "validated", "always/never", "exactly once", "O(1)") against what the code does.
- Flag mismatches (the pass-3 F-032 class: a comment claimed _release idempotent but it wasn't).
- Include docstrings that promise behavior the implementation doesn't deliver.

Return JSON findings: id (A-N), severity, file, line, title, description, poc (the counterexample), suggested_fix.`,
  },
  {
    key: 'security-sovereignty',
    prompt: `Adversarial security & data-sovereignty audit of ${ROOT}. Focus: any off-box data path (ADR-0003), credential handling/scrubbing gaps, input validation at trust boundaries, supply-chain (lockfiles, hashes, CI gates), HMAC preregistration integrity, transcript PII scrubbing completeness. The repo is 3 passes hardened — look for what remains. Be concrete; reject speculation. Return JSON: id (S-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'concurrency-resource',
    prompt: `Adversarial concurrency & resource-leak audit of ${ROOT}. Focus: races in checkpoint.py (pool cache, per-conn locks, atexit), the reasoning ThreadPoolExecutor (_inflight accounting, slot release, shutdown), context-manager/handle/connection close on exception paths, unbounded caches. 3 passes hardened — find residual issues. Return JSON: id (C-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'methodology-integrity',
    prompt: `Adversarial methodology-integrity audit of ${ROOT}/src/assay_engine/methodology and pipeline.py. Focus: discover/confirm firewall leaks, claim-blindness, pre-registration timestamp enforcement on EVERY confirm path, verdict mapping edge cases, scorecard double-counting, claim/hypothesis identity uniqueness, stability scoring correctness, HARKing paths. Also finding-completeness: diff prior fixes' intent vs implementation. Return JSON: id (M-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'reliability-errors',
    prompt: `Adversarial reliability/error-handling audit of ${ROOT}. Focus: exception swallowing, error propagation from seams, typed-exception contracts (does every documented "Raises X" hold?), edge cases (empty/single/NaN/Inf inputs), partial-failure recovery, timeout/retry bounds. 3 passes hardened. Return JSON: id (R-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'observability-ops',
    prompt: `Adversarial observability + ops/packaging/supply-chain audit of ${ROOT}. Focus: span/run lifecycle on error paths, MLflow run termination, provenance completeness + persistence, CI gate completeness (.github/workflows/ci.yml — are all gates blocking? lockfile sync? SHA pins? SBOM?), pyproject/extras correctness, dependabot. 3 passes hardened. Return JSON: id (O-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'performance-meta',
    prompt: `Adversarial performance + residual test-quality audit of ${ROOT}. Focus: algorithmic complexity on corpus-scale data, peak memory, redundant computation; AND test-quality gaps not covered by the dedicated discrimination auditor (missing negative tests, over-mocking, coverage holes in error paths). Be realistic: this is a blueprint with no real corpus yet, so flag scale issues only where cheap to fix or genuinely risky. Return JSON: id (P-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
]

const FINDING_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'severity', 'file', 'line', 'title', 'description', 'poc', 'suggested_fix'],
        properties: {
          id: { type: 'string' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          file: { type: 'string' },
          line: { type: ['integer', 'string'] },
          title: { type: 'string' },
          description: { type: 'string' },
          poc: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
      },
    },
  },
}

const REFUTE_SCHEMA = {
  type: 'object',
  required: ['id', 'survives', 'reasoning'],
  properties: {
    id: { type: 'string' },
    survives: { type: 'boolean' },
    reasoning: { type: 'string' },
  },
}

phase('Assess')
const raw = await parallel(DIMENSIONS.map(d => () =>
  agent(d.prompt, { label: 'assess:' + d.key, phase: 'Assess', schema: FINDING_SCHEMA })
))
const findings = raw.filter(Boolean).flatMap(r => r.findings)
log('Raw findings: ' + findings.length + '. Self-refuting each...')

phase('Refute')
// Adversarial self-refutation: one agent per finding tasked SOLELY with disproving it.
const refuted = await parallel(findings.map(f => () =>
  agent(
    `You are an adversarial refuter. ASSUME this finding is FALSE and try to prove it. Read the actual code at ${ROOT} and find the code path / contract / test that makes the PoC impossible or the concern moot. Only conclude survives=true if you genuinely cannot disprove it.\n\nFinding ${f.id}: ${f.title}\nFile: ${f.file}:${f.line}\nDescription: ${f.description}\nPoC: ${f.poc}\n\nReturn survives=false if you can refute it (with the specific reason), survives=true if it withstands a genuine disproof attempt.`,
    { label: 'refute:' + f.id, phase: 'Refute', schema: REFUTE_SCHEMA }
  ).then(v => ({ finding: f, refutation: v }))
))
const survivors = refuted.filter(Boolean).filter(r => r.refutation && r.refutation.survives).map(r => r.finding)
const killed = refuted.filter(Boolean).filter(r => r.refutation && !r.refutation.survives)
log('Survived self-refutation: ' + survivors.length + ' / ' + findings.length + ' (' + killed.length + ' refuted)')

phase('Dedup')
const DEDUP_SCHEMA = {
  type: 'object',
  required: ['deduplicated_findings'],
  properties: {
    deduplicated_findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'severity', 'file', 'line', 'title', 'description', 'poc', 'suggested_fix', 'dimension'],
        properties: {
          id: { type: 'string' }, severity: { type: 'string' }, file: { type: 'string' },
          line: { type: ['integer', 'string'] }, title: { type: 'string' },
          description: { type: 'string' }, poc: { type: 'string' },
          suggested_fix: { type: 'string' }, dimension: { type: 'string' },
        },
      },
    },
  },
}
const deduped = survivors.length
  ? await agent(
      'Synthesize these self-refutation-surviving findings for hc-assay (already 3 passes hardened). Deduplicate (merge same-root), rank by severity, assign sequential IDs G-001.., record the source dimension, and drop any that are clearly already-fixed or speculative.\n\n' + JSON.stringify(survivors, null, 2),
      { label: 'dedup:synthesis', phase: 'Dedup', schema: DEDUP_SCHEMA }
    )
  : { deduplicated_findings: [] }

return {
  raw_count: findings.length,
  refuted_count: killed.length,
  survivor_count: survivors.length,
  refuted: killed.map(k => ({ id: k.finding.id, title: k.finding.title, why: k.refutation.reasoning })),
  total_deduped: deduped.deduplicated_findings.length,
  findings: deduped.deduplicated_findings,
}
