
export const meta = {
  name: 'pass3-assessment',
  description: 'Pass-3 adversarial production-readiness assessment of hc-assay (8 dimensions)',
  phases: [
    { title: 'Assess', detail: '8 independent adversarial agents across distinct dimensions' },
    { title: 'Dedup', detail: 'Synthesis agent deduplicates and ranks findings' },
  ],
}

const ROOT = '/Users/thomasjones/hc-assay'

const DIMENSIONS = [
  {
    key: 'security-sovereignty',
    prompt: `You are an adversarial security auditor. Audit the hc-assay project at ${ROOT} for production-readiness issues in SECURITY and DATA SOVEREIGNTY.

Focus areas:
- Any code path that could send data off-box contrary to the local-first mandate (ADR-0003)
- Hardcoded secrets, credentials, or API keys in source or config
- Input validation gaps at trust boundaries (CLI args, external parsers, network)
- Dependency vulnerabilities or unpinned versions in pyproject.toml / requirements.lock
- Supply chain: lockfile integrity, hash verification, allowlist enforcement in CI
- File permissions, temp file handling, path traversal risks
- HMAC preregistration integrity: can the proof be forged or bypassed?
- Session token or auth credential handling

Read the source files carefully. Return a JSON list of findings, each with id (S-N), severity (critical/high/medium/low), file, line, title, description, poc (proof-of-concept), suggested_fix.

Only report TRUE production-readiness problems with specific file:line evidence.`,
  },
  {
    key: 'concurrency-resource',
    prompt: `You are an adversarial concurrency and resource-leak auditor. Audit ${ROOT} for CONCURRENCY, THREAD SAFETY, and RESOURCE MANAGEMENT issues.

Focus areas (pass-3 extra: concurrency-guard discrimination):
- Race conditions in checkpoint.py pool/lock management (_CONN_INIT_LOCKS, _POOLS_BY_CONN, _acquire_migration_lock)
- Are threading guards actually tested? Remove synchronization mentally — does the test STILL PASS? If yes, the guard is untested.
- Context managers / file handles / DB connections that may not be closed on exception paths
- asyncio event loop misuse (mixing sync/async, blocking calls in async context)
- Thread-local vs module-level state assumptions
- Memory leaks: unbounded caches, growing collections, circular references
- Signal handling and graceful shutdown paths
- LangGraph graph node re-entrancy

Read tests/test_persistence.py concurrency tests closely. Are the mocks realistic enough to catch real races?

Return findings as JSON with id (C-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'methodology-integrity',
    prompt: `You are an adversarial methodology integrity auditor. Audit ${ROOT} for METHODOLOGY INTEGRITY issues.

Focus areas (pass-3 extra: finding-completeness audit):
- Discover/confirm firewall: can a discovery-set ID leak into the confirmation step?
- Claim-blindness firewall: can baseline construction observe claims?
- Pre-registration timestamp proof: is locked_at / timestamp_proof validated strictly on every confirm path?
- Verdict mapping: direction, boundary conditions, three-outcome completeness
- Adjudication claim uniqueness: is the duplicate-claim guard actually enforced?
- Engine fingerprint: is it computed over ALL scored claims or just a subset?
- Stability scoring: does the resample-vs-null check reproduce actual effect magnitude or just sign?
- Are there any paths that allow retroactive hypothesis creation (post-hoc HARKing)?
- Pass-2 finding-completeness: compare ADR/doc Suggested fix text against what was actually implemented - flag partial closures

Read src/assay_engine/methodology/ and src/assay_engine/pipeline.py carefully.

Return findings as JSON with id (M-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'reliability-errors',
    prompt: `You are an adversarial reliability auditor. Audit ${ROOT} for RELIABILITY, ERROR HANDLING, and ROBUSTNESS issues.

Focus areas:
- Bare except clauses or exception swallowing that hides failures
- Missing error propagation: do exceptions from seams surface to the caller?
- Retry logic: are transient failures retried? Are permanent failures retried forever?
- Timeout enforcement: DB migrations, network calls, LLM calls - all need bounds
- Type validation gaps: can None/wrong-type inputs reach deep into the pipeline?
- Corpus/FeatureMatrix edge cases: empty corpus, single-element, NaN/Inf values
- Null distribution edge cases: empty list, single value, all-identical values
- Baseline hash collision or mismatch handling
- Recovery from partial pipeline failure (which phases are idempotent?)
- Pipeline ADJUDICATE/SCORE/REPORT error paths

Read src/assay_engine/pipeline.py, src/assay_engine/contracts/, src/assay_engine/methodology/ carefully.

Return findings as JSON with id (R-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'performance-scale',
    prompt: `You are an adversarial performance and scale auditor. Audit ${ROOT} for PERFORMANCE and SCALABILITY issues.

Focus areas:
- O(n^2) or worse algorithms on corpus-sized data
- Memory: loading entire corpus into RAM; no streaming path for large datasets
- Null distribution computation: is it O(corpus_size * iterations)?
- FrozenDict / freeze() performance on large nested structures
- Hash computation: is corpus_fingerprint() called multiple times on the same data?
- LangGraph graph execution: node overhead, state serialization cost
- Checkpoint DB: connection pool sizing, migration cost at startup
- Provenance trail: is the append-only chain O(n) to verify?

Read src/assay_engine/ carefully and look for algorithmic complexity issues.

Return findings as JSON with id (P-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'ops-supplychain',
    prompt: `You are an adversarial ops and supply-chain auditor. Audit ${ROOT} for OPS, PACKAGING, and SUPPLY CHAIN issues.

Focus areas (pass-3 extra: artifact-vs-test fidelity):
- CI workflow (.github/workflows/ci.yml): are all jobs actually blocking the merge gate?
- Lockfile: is requirements.lock committed and kept in sync? Does the CI check prove sync?
- pip-audit: is --strict --require-hashes actually enforced? Can the allowlist be abused?
- Dependabot: is it actually enabled and watching the right ecosystems?
- License gate: does scripts/license_gate.py cover EUPL/SSPL edge cases?
- SBOM: is it generated and attached on every CI run or only sometimes?
- Tests targeting YAML/TOML/docs must read THAT FILE and assert both corrected-content presence AND stale-content absence

Read .github/workflows/ci.yml, pyproject.toml, requirements.lock, scripts/ carefully.

Return findings as JSON with id (O-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'observability-provenance',
    prompt: `You are an adversarial observability and provenance auditor. Audit ${ROOT} for OBSERVABILITY and PROVENANCE issues.

Focus areas:
- OpenTelemetry: are spans started for every pipeline phase? Are they closed on error?
- MLflow: is every run ended even on exception? Are nested runs handled correctly?
- Phoenix: is tracing initialised before the first span is created?
- Provenance trail: is every pipeline action recorded with enough context?
- Hash chain: is the chain integrity verifiable end-to-end? Is there a verify() path?
- Transcript capture: is the pre-commit hook robust? Can it fail silently?
- Structured logging: are errors logged with enough context?
- Metrics: are there any SLO-relevant metrics?

Read src/assay_engine/observability/, src/assay_engine/provenance.py, scripts/, .githooks/ carefully.

Return findings as JSON with id (OB-N), severity, file, line, title, description, poc, suggested_fix.`,
  },
  {
    key: 'meta-test-quality',
    prompt: `You are an adversarial test quality auditor. Audit ${ROOT} for TEST QUALITY and TEST COVERAGE issues.

Focus areas (all three pass-3 dimensions):
1. ARTIFACT-VS-TEST FIDELITY: Every test targeting a non-Python artifact (YAML/TOML/docs) must read THAT FILE and assert both corrected-content presence AND stale-content absence. Check test_docs_drift.py, test_supply_chain.py.
2. FINDING-COMPLETENESS: For each issue fixed in pass-1 (#101-#122) and pass-2 (#124-#156), compare the Suggested fix in PASS-1.md/PASS-2.md against what was committed. Flag partial closures.
3. CONCURRENCY-GUARD DISCRIMINATION: For each concurrency test in test_persistence.py, mentally remove the synchronization (locks) and ask: would the test still pass? If yes, the guard is not actually tested.

Additional:
- Tests that mock too aggressively (mock the thing being tested)
- Missing negative tests (only happy paths tested)
- Tests that pass vacuously

Read tests/ and docs/hardening/PASS-1.md, PASS-2.md carefully.

Return findings as JSON with id (T-N), severity, file, line, title, description, poc, suggested_fix.`,
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
        }
      }
    }
  }
}

phase('Assess')
const rawResults = await parallel(DIMENSIONS.map(d => () =>
  agent(d.prompt, { label: 'assess:' + d.key, phase: 'Assess', schema: FINDING_SCHEMA })
))

phase('Dedup')
const allFindings = rawResults.filter(Boolean).flatMap(r => r.findings)
log('Total raw findings: ' + allFindings.length + '. Deduplicating...')

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
          id: { type: 'string' },
          severity: { type: 'string' },
          file: { type: 'string' },
          line: { type: ['integer', 'string'] },
          title: { type: 'string' },
          description: { type: 'string' },
          poc: { type: 'string' },
          suggested_fix: { type: 'string' },
          dimension: { type: 'string' },
        }
      }
    }
  }
}

const deduped = await agent(
  'You are a senior engineer synthesizing adversarial findings from 8 independent assessors of the hc-assay project.\n\nHere are all raw findings (' + allFindings.length + ' total):\n' + JSON.stringify(allFindings, null, 2) + '\n\nTasks:\n1. Deduplicate: merge findings that describe the same root problem (keep most detailed description)\n2. Rank by severity: critical > high > medium > low\n3. Assign sequential IDs: F-001, F-002, ...\n4. For each finding, record which dimension it came from\n5. Filter out clear false positives (speculative, no concrete evidence, already fixed in pass-1/pass-2)\n\nReturn the deduplicated list ranked by severity.',
  { label: 'dedup:synthesis', phase: 'Dedup', schema: DEDUP_SCHEMA }
)

return {
  total_raw: allFindings.length,
  total_deduped: deduped ? deduped.deduplicated_findings.length : 0,
  findings: deduped ? deduped.deduplicated_findings : [],
}
