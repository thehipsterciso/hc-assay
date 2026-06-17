export const meta = {
  name: 'hardening-pass-8-audit',
  description: 'Pass-8 re-audit of LangChain/LangGraph/Phoenix code: audit per layer×dimension, adversarially verify each finding, synthesize confirmed set',
  phases: [
    { title: 'Audit', detail: 'auditors per layer×dimension read the real code' },
    { title: 'Verify', detail: 'adversarially refute each candidate finding' },
    { title: 'Synthesize', detail: 'collect confirmed findings' },
  ],
}

const REPO = '/Users/[REDACTED]/hc-grc'

const FINDINGS = {
  type: 'object', additionalProperties: false,
  properties: {
    dimension: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          title: { type: 'string' },
          severity: { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
          location: { type: 'string', description: 'file:line' },
          problem: { type: 'string' },
          best_practice_violated: { type: 'string' },
          proposed_fix: { type: 'string' },
        },
        required: ['title', 'severity', 'location', 'problem', 'best_practice_violated', 'proposed_fix'],
      },
    },
  },
  required: ['dimension', 'findings'],
}

const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    title: { type: 'string' },
    confirmed: { type: 'boolean', description: 'true only if the defect is real, reachable, and not already mitigated elsewhere in the code' },
    adjusted_severity: { type: 'string', enum: ['none', 'low', 'medium', 'high', 'critical'] },
    verification: { type: 'string', description: 'what you checked in the actual code; cite file:line. State explicitly if it is a false positive or already-mitigated.' },
    recommended_action: { type: 'string' },
  },
  required: ['title', 'confirmed', 'adjusted_severity', 'verification', 'recommended_action'],
}

// Layer × dimension auditors — mirrors the documented pass method. Each reads the
// REAL code on the hardening/pass-5 branch (post-merge main + batch 15).
const DIMENSIONS = [
  { key: 'lc-reliability', layer: 'langchain', focus: 'reasoning_client timeouts, retry/backoff budgets, rate-limit backpressure, the bounded timeout pool (_submit_bounded), error classification (transient vs permanent vs rate-limit)' },
  { key: 'lc-correctness', layer: 'langchain', focus: 'reasoning_client tier routing, JSON extraction/balanced-brace parser, complete_json retry+temperature logic, empty-reply handling, T1 misuse guard, kill-switch' },
  { key: 'lc-t3-sdk', layer: 'langchain', focus: 'Tier-3 claude-agent-sdk path: ClaudeAgentOptions (permission_mode, setting_sources, allowed_tools, env scrub), ResultMessage error/rate handling, asyncio.wait_for + _run_sync backstop, metered-API isolation (ADR-0016)' },
  { key: 'lg-graph', layer: 'langgraph', focus: 'graph.py build/compile, RetryPolicy, recursion/loop guards, run/resume entrypoints, run_id propagation' },
  { key: 'lg-gates', layer: 'langgraph', focus: 'gates.py + gate_coordinator: interrupt/resume safety, idempotency (_already_decided, terminal decisions), gate-id correlation, operator-response validation, Gate-2 prerequisite + deferred path idempotency' },
  { key: 'lg-checkpointer', layer: 'langgraph', focus: 'checkpointer.py: pooled PostgresSaver self-healing, advisory-locked migration, setup()-once guard, connection-string precedence/config, atexit pool cleanup' },
  { key: 'lg-state', layer: 'langgraph', focus: 'state.py reducers (append vs merge vs last-write-wins), dedup reducers, concurrent-write safety, schema correctness' },
  { key: 'obs-wiring', layer: 'phoenix', focus: 'phoenix_setup: provider registration/idempotency, global-provider collision warning, BatchSpanProcessor, exporter timeout bound, atexit + SIGTERM flush, loopback guards (client + server bind)' },
  { key: 'obs-completeness', layer: 'phoenix', focus: 'span attributes/token accounting (incl. cache tokens), run_id/baggage propagation across the timeout thread, T2/T3 span coverage, MLflow wiring' },
  { key: 'xc-config', layer: 'cross', focus: 'config.py schema validation, platform.yaml consumption, requirements*.txt bounds/consistency (py3.14 floors, CI vs prod parity), pyproject build' },
  { key: 'xc-tests', layer: 'cross', focus: 'test coverage gaps on failure/recovery branches, non-deterministic tests, CI-vs-local skip behavior, whether new batch-15 behaviors are actually covered' },
  { key: 'xc-security', layer: 'cross', focus: 'data sovereignty (ADR-0002 SCF-derived content never leaves host), secret/key handling, subprocess sandboxing, no metered-API spill, loopback enforcement completeness' },
]

phase('Audit')
const confirmed = await pipeline(
  DIMENSIONS,
  // Stage 1: audit this dimension against the real code
  (d) => agent(
    `You are a meticulous code auditor for HC-GRC hardening PASS 8. Repo root: ${REPO}, branch hardening/pass-8 (this already includes passes 1–7 (through batch 18) fixes — do NOT re-report anything already fixed; find what REMAINS or was newly introduced).\n\n` +
    `Dimension: ${d.key} (layer: ${d.layer}). Focus: ${d.focus}.\n\n` +
    `This codebase has been through SEVEN hardening passes; it is mature. The goal now is CONVERGENCE — an empty findings array is the SUCCESS outcome, not a failure. Only report a GENUINE, LIVE defect a competent reviewer would actually fix: a real bug, a reachable correctness/reliability/security hole, or a data-sovereignty violation. STRICT BARS:\n` +
    `- Missing-test-coverage is NOT 'high' (at most 'low', and only if it hides a real untested bug).\n` +
    `- Do NOT report style, naming, type-annotation polish, or speculative 'could in theory' items.\n` +
    `- Do NOT re-report anything fixed in passes 1–7, nor any of these deliberate WONTFIX items (HARDENING_LOG pass 7): (1) Phoenix exporter 2s flush timeout; (2) SIGTERM handler swallowing flush exceptions; (3) MLflow run_id tagging being caller responsibility; (4) defensive guards for SDK message fields already getattr-None-safe; (5) loopback set not accepting all of 127.0.0.0/8.\n` +
    `- Reserve 'high' for serious reachable defects (data loss, sovereignty breach, crash/hang on a real path, silent wrong result).\n\n` +
    `Read the ACTUAL code (Read/Grep/Bash read-only; python -c against ${REPO}/.venv; inspect installed package source). Be precise with file:line. Returning [] when the dimension is sound is the desired result. A false finding is worse than none.`,
    { label: `audit:${d.key}`, phase: 'Audit', schema: FINDINGS, agentType: 'Explore' }
  ),
  // Stage 2: adversarially verify each finding from this dimension (no barrier — runs as each audit completes)
  (audit) => parallel((audit?.findings || []).map((f) => () =>
    agent(
      `You are an ADVERSARIAL verifier for HC-GRC hardening PASS 8. Repo root: ${REPO}, branch hardening/pass-8. Your job is to REFUTE the following candidate finding by reading the real code. Default to confirmed=false unless you can mechanically prove the defect is real, reachable in practice, and NOT already mitigated elsewhere.\n\n` +
      `CANDIDATE (dimension ${audit.dimension}):\n` +
      `title: ${f.title}\nseverity: ${f.severity}\nlocation: ${f.location}\nproblem: ${f.problem}\nbest_practice_violated: ${f.best_practice_violated}\nproposed_fix: ${f.proposed_fix}\n\n` +
      `Verify against the actual code (Read/Grep/Bash read-only, inspect installed deps if needed). Check: is the cited code really as described? Is the failure path reachable IN PRACTICE? Is it already guarded/mitigated elsewhere (timeouts, validation, reducers, idempotency guards)? Is it one of the 5 documented WONTFIX items (if so, confirmed=false)? Is the severity HONEST — downgrade test-coverage/defensive/style items to low or none, and reserve high for serious reachable defects? Default to confirmed=false unless it is a genuine live defect worth a fix. Set adjusted_severity='none' for anything that is really just polish/coverage.`,
      { label: `verify:${f.title.slice(0, 40)}`, phase: 'Verify', schema: VERDICT, agentType: 'Explore' }
    ).then((v) => ({ ...v, dimension: audit.dimension, original_severity: f.severity, location: f.location, proposed_fix: f.proposed_fix }))
  ))
)

phase('Synthesize')
const all = confirmed.flat().filter(Boolean)
const real = all.filter((v) => v.confirmed && v.adjusted_severity !== 'none')
const bySev = (s) => real.filter((v) => v.adjusted_severity === s).length
log(`Pass 8: ${all.length} candidates verified; ${real.length} confirmed (` +
    `${bySev('critical')}C/${bySev('high')}H/${bySev('medium')}M/${bySev('low')}L)`)
return {
  candidates_verified: all.length,
  confirmed_count: real.length,
  breakdown: { critical: bySev('critical'), high: bySev('high'), medium: bySev('medium'), low: bySev('low') },
  confirmed: real,
  rejected: all.filter((v) => !v.confirmed || v.adjusted_severity === 'none').map((v) => ({ title: v.title, dimension: v.dimension, why: v.verification.slice(0, 240) })),
}
