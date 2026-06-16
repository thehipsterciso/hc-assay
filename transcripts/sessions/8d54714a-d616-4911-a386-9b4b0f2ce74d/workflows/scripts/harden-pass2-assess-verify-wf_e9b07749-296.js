export const meta = {
  name: 'harden-pass2-assess-verify',
  description: 'Pass 2: 7 retrospective-informed adversarial assessors -> dedup -> 2 independent verifiers per finding',
  phases: [{ title: 'Assess' }, { title: 'Verify' }],
}
const REPO = '/Users/thomasjones/hc-assay'
const VENV = '/Users/thomasjones/hc-assay/.venv/bin/python'
const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      properties: {
        title: { type: 'string' }, dimension: { type: 'string' },
        severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
        file: { type: 'string' }, line: { type: 'string' },
        description: { type: 'string' }, suggested_fix: { type: 'string' },
      },
      required: ['title', 'dimension', 'severity', 'file', 'description', 'suggested_fix'],
    } },
  },
  required: ['findings'],
}
const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    is_real: { type: 'boolean' },
    severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NOT_A_BUG'] },
    reasoning: { type: 'string' }, evidence: { type: 'string' },
  },
  required: ['is_real', 'severity', 'reasoning', 'evidence'],
}
const COMMON = `Repo: ${REPO} (branch harden/pass-2; pass 1 already merged 22 fixes). Venv (run PoCs): ${VENV}.
Dataset-agnostic ML/methodology engine being hardened for PRODUCTION. Hard constraints (NOT bugs): local-first/data-sovereign (loopback only), no metered API (subscription OAuth), engine imports no adapter/dataset (ADR-0002), optional heavy backends lazy-imported (ADR-0006). Read real code; back findings with a concrete repro/PoC. Report ONLY genuine production-readiness defects, not style. Pass-1 findings #101-#122 are already FIXED — do not re-report them; DO report anything they missed or any regression they introduced.`
const DIMENSIONS = [
  { key: 'test-quality-fix-guarding', prompt: `${COMMON}\n\nDIMENSION: test quality / do tests actually guard behavior. Audit the test suite (tests/) for NON-DISCRIMINATING tests (pass whether or not the code is correct — verify by reverting the implementation and checking the test still passes), over-mocked tests that never exercise real logic, assertions weaker than the docstring/guarantee they claim to cover, and untested error/edge branches. Prioritize security/methodology/concurrency guards. For each, name the exact test and what it fails to catch.` },
  { key: 'concurrency-load', prompt: `${COMMON}\n\nDIMENSION: concurrency & load. Force real interleaving (slow injected clocks, setswitchinterval, barriers, many threads) to find races the GIL normally hides: the reasoning ThreadPoolExecutor/_inflight, the persistence ConnectionPool self-heal, the new provenance lock, registry, run_study under concurrent runs sharing a trail/tracker. Look for deadlocks, lock-ordering, unbounded growth, and resource exhaustion under load. PoCs required.` },
  { key: 'dependency-supplychain', prompt: `${COMMON}\n\nDIMENSION: dependency & supply chain. Actually run pip-audit against the venv and report any advisory. Assess version ranges in pyproject (too-wide ranges admitting bad versions), transitive risk, missing upper bounds, reproducibility (no lockfile), and whether the new pip-audit CI job + .pip-audit-ignore mechanism actually works. SBOM/license-of-deps gaps.` },
  { key: 'api-backcompat-protocol', prompt: `${COMMON}\n\nDIMENSION: public API & adapter-Protocol stability. A clone depends on the contracts (parser/claims/features/study Protocols, BaselineBuilder, run_study/StudyPlan/StudyResult signatures, the top-level public API). Find: breaking inconsistencies, Protocols that can't be implemented as documented, missing runtime checks that a misimplemented adapter would need, signature/return-type surprises, things that would silently break a study on a minor engine change. Check the @runtime_checkable usage and isinstance behavior.` },
  { key: 'docs-code-drift', prompt: `${COMMON}\n\nDIMENSION: docs vs code drift / over-claims. Compare every normative claim in README, docs/*.md (CHARTER/METHODOLOGY/GOVERNANCE/ARCHITECTURE/GLOSSARY), and ADRs against the actual code. Find over-claims (a guarantee stated more strongly than enforced), stale statements, wrong examples, and undocumented honest-scope limits. The README quickstart and examples/minimal_study.py must actually run — verify.` },
  { key: 'methodology-integrity-deep', prompt: `${COMMON}\n\nDIMENSION: methodology integrity (deep, NEW angles). Re-attack with approaches pass 1 did not try: defeat Firewall A/B, pre-registration (forge/replay/content-or-id swap, clock manipulation), the provenance chain (keyed AND unkeyed — collisions, length-extension, canonicalization ambiguities, the as_recorder path), the measurement<->interpretation fence (new smuggling vectors), phase-order, claim<->hypothesis<->verdict identity, scorecard math. Concrete PoCs through run_study and the primitives.` },
  { key: 'regression-from-pass1', prompt: `${COMMON}\n\nDIMENSION: regressions introduced by the 22 pass-1 fixes. Scrutinize the pass-1 changes for new defects: scrubbed_env overwrite-to-empty breaking legitimate CLI operation or wiping a needed var; run_json deadline/seed/parse-only-reroll edge cases; the provenance lock causing contention/deadlock or breaking determinism; pg-pool close-on-failure double-close; vectorstore close() on a shared client; corpus_hash param mis-binding the determinism record; dynamic version build breakage; mypy-unpinned new errors on 3.12-3.14. Use git log/diff of pass 1 + PoCs.` },
]
phase('Assess')
log(`Pass 2: ${DIMENSIONS.length} retrospective-informed assessors`)
const assessed = await parallel(DIMENSIONS.map((d) => () =>
  agent(d.prompt, { label: `assess:${d.key}`, phase: 'Assess', schema: FINDINGS_SCHEMA })))
const all = assessed.filter(Boolean).flatMap((r, i) =>
  (r.findings || []).map((f) => ({ ...f, _assessor: DIMENSIONS[i] ? DIMENSIONS[i].key : '?' })))
const seen = new Map()
for (const f of all) {
  const k = `${(f.title || '').toLowerCase().trim()}::${(f.file || '').toLowerCase().trim()}`
  if (!seen.has(k)) seen.set(k, f)
}
const deduped = [...seen.values()]
log(`${all.length} findings; ${deduped.length} after dedup`)
phase('Verify')
const verified = await parallel(deduped.map((f, idx) => () =>
  parallel([1, 2].map((n) => () =>
    agent(`${COMMON}\n\nIndependent VERIFIER #${n} of 2. A pass-2 assessor reported:\nTITLE: ${f.title}\nDIMENSION: ${f.dimension}\nSEVERITY: ${f.severity}\nFILE: ${f.file} ${f.line || ''}\nDESCRIPTION: ${f.description}\nSUGGESTED FIX: ${f.suggested_fix}\nIndependently determine if this is a TRUE production-readiness problem. Read the code; PoC where applicable. is_real=false if false positive / already handled / documented-justified scope. Recalibrate severity. Give evidence.`,
      { label: `verify:${idx}:${n}`, phase: 'Verify', schema: VERDICT_SCHEMA })))
    .then((vs) => ({ finding: f, verdicts: vs.filter(Boolean) }))))
const confirmed = verified.filter((v) => v.verdicts.length === 2 && v.verdicts.every((x) => x.is_real))
const rejected = verified.filter((v) => !(v.verdicts.length === 2 && v.verdicts.every((x) => x.is_real)))
log(`Confirmed ${confirmed.length}; rejected/split ${rejected.length}`)
return { confirmed, rejected, total_findings: all.length, deduped: deduped.length }