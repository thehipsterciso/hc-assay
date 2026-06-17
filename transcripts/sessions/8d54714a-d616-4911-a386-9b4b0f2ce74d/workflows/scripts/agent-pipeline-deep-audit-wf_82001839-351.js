export const meta = {
  name: 'agent-pipeline-deep-audit',
  description: 'Deep audit of the HC-GRC agent + pipeline code against their AGENT.md/SAP/protocol specs and research-integrity invariants (honest bar, adversarially verified)',
  phases: [
    { title: 'Audit', detail: 'one deep reviewer per agent/module + cross-cutting checks' },
    { title: 'Verify', detail: 'adversarially verify each finding' },
    { title: 'Synthesize', detail: 'collect confirmed findings' },
  ],
}

const REPO = '/Users/[REDACTED]/hc-grc'

const FINDINGS = {
  type: 'object', additionalProperties: false,
  properties: {
    unit: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          title: { type: 'string' },
          severity: { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
          location: { type: 'string' },
          problem: { type: 'string' },
          spec_or_invariant: { type: 'string', description: 'the AGENT.md/SAP/protocol clause or integrity invariant violated' },
          proposed_fix: { type: 'string' },
        },
        required: ['title', 'severity', 'location', 'problem', 'spec_or_invariant', 'proposed_fix'],
      },
    },
  },
  required: ['unit', 'findings'],
}

const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    title: { type: 'string' },
    confirmed: { type: 'boolean' },
    adjusted_severity: { type: 'string', enum: ['none', 'low', 'medium', 'high', 'critical'] },
    is_stub_by_design: { type: 'boolean', description: 'true if this is just an intentional Phase-0/1 NotImplementedError stub (IMPLEMENTED=False) and NOT a real defect' },
    verification: { type: 'string' },
    recommended_action: { type: 'string' },
  },
  required: ['title', 'confirmed', 'adjusted_severity', 'is_stub_by_design', 'verification', 'recommended_action'],
}

// Shared context every auditor gets.
const CONTEXT =
  `Repo ${REPO}. This is the HC-GRC research-governance platform: a LangGraph agency that empirically tests the Secure Controls Framework's STRM mappings under a 5-gate human-in-the-loop topology.\n\n` +
  `CRITICAL FRAMING — most agents are INTENTIONAL Phase-0/1 STUBS: their run()/run_exploratory()/run_confirmatory() raise NotImplementedError with class flag IMPLEMENTED=False. That is BY DESIGN (the real ML pipeline isn't live yet) and is NOT a defect — do NOT report "agent doesn't do the work yet". \n\n` +
  `Report GENUINE defects only, in these categories:\n` +
  `1. CORRECTNESS of logic that IS actually implemented (e.g. the test-split access checks in data_steward.get_split_paths run real gate-checking BEFORE the NotImplementedError; base.assert_gate2_approved; data_split seeding; any helper/dataclass logic; __init__ registries).\n` +
  `2. RESEARCH-INTEGRITY invariants (the highest stakes): the test-split firewall (no test access before the required gate(s)); EXP_ artifact prefix; NO p-value/decision language in exploratory outputs; SAP header on confirmatory; HARKing prevention; split-seed immutability after Gate 2.\n` +
  `3. SPEC MISALIGNMENT: where the code contradicts its own agents/<area>/<name>/AGENT.md role doc, docs/protocol/03_statistical_analysis_plan.md, docs/protocol/04_methods_scaffolding.md, docs/charter/, or the base.py contract. Find the AGENT.md via grep/find.\n` +
  `4. CONTRACT adherence: PROTECTED / IMPLEMENTED / AGENT_ID flags set correctly and consistently with base.py and the AGENT.md; return value is a partial-state dict (never mutates state in place); correct base class.\n` +
  `5. INCONSISTENCIES between modules (e.g. does base.assert_gate2_approved's Gate-2-only check contradict data_steward's Gate-2-AND-Gate-3 requirement? could a P-agent's run_confirmatory reach the test split through a weaker check?).\n\n` +
  `Read the REAL code and the REAL spec docs (Read/Grep/Bash read-only). Be precise with file:line, cite the exact spec clause. Honest severity: 'critical'/'high' only for real integrity/correctness defects reachable in practice; a doc/stub mismatch is usually low/medium. Return [] if the unit is genuinely sound. Do NOT invent issues.`

const AGENT_UNITS = [
  { key: 'base-contract', path: 'src/agents/base.py + src/agents/__init__.py', focus: 'the agent contract: SAPViolationError/assert_gate2_approved correctness, phase dispatch, PROTECTED/IMPLEMENTED semantics, the agent registry exports. Does assert_gate2_approved (Gate-2 only) under-enforce vs data_steward (Gate 2 AND Gate 3)?' },
  { key: 'data-acquisition', path: 'src/agents/data_acquisition/agent.py', focus: 'real logic vs stub; AGENT.md alignment; provenance; corpus-integrity claims' },
  { key: 'data-curation', path: 'src/agents/data_curation/agent.py', focus: 'real logic vs stub; AGENT.md alignment; anomaly/codebook handling' },
  { key: 'data-steward', path: 'src/agents/data_steward/agent.py', focus: 'THE test-split firewall — get_split_paths gate checks (Gate2 AND Gate3), _assert_seed_unchanged, seed immutability; AGENT.md behavioral constraints; any way to get test paths without both gates' },
  { key: 'embedding-agent', path: 'src/agents/embedding_agent/agent.py', focus: 'real logic vs stub; model/version provenance; data-sovereignty (embeddings never leave host); AGENT.md alignment' },
  { key: 'hypothesis-formalizer', path: 'src/agents/hypothesis_formalizer/agent.py', focus: 'PROTECTED; HARKing prevention; FormalHypothesis shape (hypothesis_id), EXP-vs-confirmatory separation; produces the Gate-2 hypothesis_set; SAP §1 alignment' },
  { key: 'p1-strm-nlp', path: 'src/agents/p1_strm_nlp/agent.py', focus: 'PROTECTED; EXP_ prefix; no p-value language; run_confirmatory test-split access guard; SAP/AGENT.md alignment' },
  { key: 'p2-control-topology', path: 'src/agents/p2_control_topology/agent.py', focus: 'PROTECTED; EXP_ prefix; NIST-cluster constraint (NIST 800-53/CSF/800-171 as ONE source); no p-value language; test-split guard' },
  { key: 'p3-regulatory-convergence', path: 'src/agents/p3_regulatory_convergence/agent.py', focus: 'PROTECTED; EXP_ prefix; no p-value language; test-split guard; AGENT.md/SAP alignment' },
  { key: 'p4-risk-blindspot', path: 'src/agents/p4_risk_blindspot/agent.py', focus: 'PROTECTED; false-coverage exclusion (controls without STRM mappings excluded from blindspot claims); EXP_ prefix; no p-value language; test-split guard' },
  { key: 'p5-ai-governance', path: 'src/agents/p5_ai_governance/agent.py', focus: 'PROTECTED; UMAP params pre-registered; EXP_ prefix; no p-value language; test-split guard' },
  { key: 'statistical-analyst', path: 'src/agents/statistical_analyst/agent.py', focus: 'PROTECTED; confirmatory only; multiple-comparison correction per SAP §6; SAP header; decision rules; null-result integrity; test-split firewall' },
  { key: 'repo-documentation', path: 'src/agents/repo_documentation/agent.py', focus: 'executive-mode gating (only after Gate 4); branding compliance; no SCF-derived data leaves machine (CC BY-ND); AGENT.md alignment' },
]

const NODE_UNITS = [
  { key: 'data-split-node', path: 'src/nodes/data_split.py', focus: 'SHA-256 seeded determinism, ratio correctness (70/15/15), stratification, idempotency (data_split_verified), no leakage between splits, seed provenance' },
  { key: 'gate-coordinator', path: 'src/nodes/gate_coordinator.py', focus: 'single-writer for gate_status; record completeness; merge-reducer safety' },
]

const CROSS_UNITS = [
  { key: 'xc-firewall-consistency', path: 'cross-cutting: base.assert_gate2_approved vs data_steward.get_split_paths vs every P-agent run_confirmatory vs statistical_analyst', focus: 'Is the test-split firewall enforced CONSISTENTLY and completely across ALL access paths? Can any agent reach test data with only Gate 2 when Gate 3 is also required (or vice versa)? Is assert_gate2_approved sufficient, or a weaker guard than the data steward? Trace every path that could read test_ids/test split.' },
  { key: 'xc-protected-flags', path: 'cross-cutting: PROTECTED/IMPLEMENTED/AGENT_ID across all 13 agents', focus: 'Per base.py + ADR-0015 §77, P1-P5 + statistical-analyst + hypothesis-formalizer MUST be PROTECTED=True; pipeline agents MUST be PROTECTED=False. Verify each agent sets the right flags, IMPLEMENTED matches reality (all stubs => False), AGENT_ID matches the AGENT.md name. Report any wrong/missing flag (Agent Evolution could then modify a protected agent).' },
  { key: 'xc-research-integrity', path: 'cross-cutting: EXP_ prefix, no-p-value-in-exploratory, SAP header on confirmatory, HARKing', focus: 'Across all exploratory agents and the hypothesis formalizer: are the documented integrity rules actually enforceable/enforced in the code paths that exist, or only asserted in docstrings? Any place exploratory output could carry decision language, or confirmatory could run without a SAP header, or hypotheses could be added post-EDA (HARKing)?' },
]

const ALL = [...AGENT_UNITS, ...NODE_UNITS, ...CROSS_UNITS]

phase('Audit')
const confirmed = await pipeline(
  ALL,
  (u) => agent(
    `${CONTEXT}\n\n=== YOUR UNIT: ${u.key} ===\nTarget: ${u.path}\nFocus: ${u.focus}\n\nAudit it deeply now. Locate and read the relevant AGENT.md and SAP/protocol sections too, not just the code.`,
    { label: `audit:${u.key}`, phase: 'Audit', schema: FINDINGS, agentType: 'Explore' }
  ),
  (audit) => parallel((audit?.findings || []).map((f) => () =>
    agent(
      `Adversarial verifier, HC-GRC agent/pipeline deep audit. Repo ${REPO}. REFUTE this candidate by reading the real code AND the cited spec. Remember: an intentional Phase-0/1 stub (NotImplementedError + IMPLEMENTED=False) is NOT a defect — set is_stub_by_design=true and confirmed=false for those. Default confirmed=false unless it is a genuine defect in implemented logic, a real research-integrity hole, or a real code-vs-spec contradiction.\n\n` +
      `CANDIDATE (unit ${audit.unit}):\ntitle: ${f.title}\nseverity: ${f.severity}\nlocation: ${f.location}\nproblem: ${f.problem}\nspec_or_invariant: ${f.spec_or_invariant}\nproposed_fix: ${f.proposed_fix}\n\n` +
      `Verify against actual code + spec (read-only). Cite file:line and the exact spec clause. Be honest about severity.`,
      { label: `verify:${f.title.slice(0, 36)}`, phase: 'Verify', schema: VERDICT, agentType: 'Explore' }
    ).then((v) => ({ ...v, unit: audit.unit, original_severity: f.severity, location: f.location, proposed_fix: f.proposed_fix }))
  ))
)

phase('Synthesize')
const all = confirmed.flat().filter(Boolean)
const real = all.filter((v) => v.confirmed && !v.is_stub_by_design && v.adjusted_severity !== 'none')
const bySev = (s) => real.filter((v) => v.adjusted_severity === s).length
log(`Agent/pipeline deep audit: ${all.length} candidates verified; ${real.length} genuine ` +
    `(${bySev('critical')}C/${bySev('high')}H/${bySev('medium')}M/${bySev('low')}L); ` +
    `${all.filter(v => v.is_stub_by_design).length} were stub-by-design (not defects)`)
return {
  candidates_verified: all.length,
  genuine_count: real.length,
  breakdown: { critical: bySev('critical'), high: bySev('high'), medium: bySev('medium'), low: bySev('low') },
  genuine: real,
  stub_by_design: all.filter((v) => v.is_stub_by_design).map((v) => v.title),
  rejected: all.filter((v) => !v.confirmed && !v.is_stub_by_design).map((v) => ({ title: v.title, why: v.verification.slice(0, 200) })),
}
