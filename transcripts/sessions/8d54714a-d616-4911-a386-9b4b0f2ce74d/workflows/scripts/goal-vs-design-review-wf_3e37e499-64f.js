export const meta = {
  name: 'goal-vs-design-review',
  description: 'First-principles review: can the architecture/frameworks/implementation/specs actually achieve the project GOAL (empirically test SCF STRM mappings, Tier 1 of 3)? Treats specs as fallible.',
  phases: [
    { title: 'Critique', detail: 'expert lenses evaluate sufficiency against the goal' },
    { title: 'Adjudicate', detail: 'devil’s-advocate dedupe + reality-check' },
  ],
}

const REPO = '/Users/[REDACTED]/hc-grc'

const FINDING = {
  type: 'object', additionalProperties: false,
  properties: {
    lens: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          title: { type: 'string' },
          kind: { type: 'string', enum: ['methodology-flaw', 'architecture-gap', 'framework-mismatch', 'spec-incorrect', 'spec-insufficient', 'goal-blocker', 'missing-capability'] },
          severity: { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
          where: { type: 'string', description: 'doc/file/section it concerns' },
          problem: { type: 'string', description: 'why this threatens achieving the GOAL (not just spec compliance)' },
          evidence: { type: 'string', description: 'what in the goal docs + design/impl supports this' },
          recommendation: { type: 'string' },
        },
        required: ['title', 'kind', 'severity', 'where', 'problem', 'evidence', 'recommendation'],
      },
    },
  },
  required: ['lens', 'findings'],
}

const GOAL =
  `THE GOAL (from docs/charter/PROJECT_CHARTER.md + docs/protocol/00_research_questions.md + 02_contribution.md + docs/charter/RESEARCH_DESIGN.md): ` +
  `Conduct the FIRST large-scale EMPIRICAL test of the Secure Controls Framework's ~280,000 expert-derived STRM mappings — does Expert-Derived Content actually produce better crosswalk mappings than NLP/ML? Five analytical modules: P1 STRM calibration (correlation/classification of strength vs embedding similarity), P2 control-space topology (graph community detection), P3 regulatory convergence (clustering/coverage), P4 risk-blindspot (coverage/set-cover over the 39 risk categories), P5 AI-governance cross-domain clustering. ` +
  `Hard requirements: a STRICT exploratory/confirmatory firewall (exploration on train+val, confirmation on a held-out TEST split, the two phases "share no data"); pre-registration with single-operator structural independence (code gates, append-only PROV-DM, RFC-3161 timestamps); null results are first-class; this is TIER 1 of 3 — outputs (framework-agnostic ARA knowledge-graph schema, confidence scores on every finding, structured null results, multi-graph-composable P2 topology) must feed Tier 2 comparative + Tier 3 causal-impact projects.\n\n` +
  `THE TASK: treat the specs (charter, ADRs, AGENT.md, SAP) as FALLIBLE. Judge whether the actual architecture (a LangGraph agent system with 5 governance gates, tiered reasoning_client, Phoenix/MLflow/Postgres/Qdrant), the framework choices, the methodology, and the current implementation are SUFFICIENT and CORRECT to ACHIEVE THE GOAL — or whether the design itself is flawed/insufficient/internally inconsistent. Report goal-level problems, not spec-compliance nits. Read the goal docs, the ADRs (docs/decisions/), the SAP (docs/protocol/03_statistical_analysis_plan.md, 04_methods_scaffolding.md), and the real implementation (src/). Cite specifics. Honest severity: 'critical'/'high' = would invalidate the science or block the goal.`

const LENSES = [
  { lens: 'methodology-split-validity', prompt: `You are a research methodologist. ${GOAL}\n\nFOCUS: Is the single train/val/test split firewall methodologically VALID for all five modules? A random held-out test split supports P1's correlation/classification hypotheses, but interrogate hard: can you hold out a "test split" of STRM mappings for P2 graph community detection (splitting a graph destroys topology), for P3/P4 whole-framework coverage questions (coverage is a property of the WHOLE corpus, not a sample), or for P5 clustering? Does "the two phases share no data" even make sense for graph/coverage analysis? If the firewall is invalid for some modules, the confirmatory claims for those modules are invalid. Examine data_split.py and how splits are consumed. Also assess: is the exploratory→confirmatory separation airtight, or can exploratory effect sizes leak into confirmatory calibration (the docs forbid it — is it enforceable)?` },
  { lens: 'statistical-rigor-power', prompt: `You are a statistician. ${GOAL}\n\nFOCUS: Is the statistical design sufficient for a PUBLISHABLE empirical claim at ~280,000-mapping scale? Read docs/protocol/03_statistical_analysis_plan.md and 04_methods_scaffolding.md. Assess: statistical power / sample-size justification; multiple-comparisons control across many hypotheses × algorithms × frameworks (Bonferroni/BH adequacy and whether the "algorithm inventory" of dozens of methods creates a garden-of-forking-paths / researcher-degrees-of-freedom problem that the pre-registration must but may not constrain); appropriate null models (e.g., for graph modularity, permutation nulls); effect-size pre-specification; whether "test EVERY algorithm in the inventory" is compatible with pre-registration. Is the SAP itself sufficient/correct?` },
  { lens: 'architecture-fit', prompt: `You are a systems architect. ${GOAL}\n\nFOCUS: Does the BUILT architecture match and serve the goal? The charter §3 describes src/schema (canonical PYDANTIC models Control/STRMMapping/Framework/EmbeddingRecord), src/ingestion, src/embeddings, src/graph, src/stats, src/clustering, research/ design files, experiments/. Compare to what actually exists in src/ (a LangGraph agent/gate system; the schema types in src/agents/base.py are placeholder __slots__ classes, NOT Pydantic). Assess: (a) is the canonical data schema contract actually built? (b) is there ANY research engine (ingestion/embeddings/stats/graph) or only governance scaffolding? (c) is the LangGraph-gate governance proportionate/sufficient, or elaborate process around absent science? (d) charter↔ADR↔implementation drift (charter never mentions LangGraph/Phoenix/3.14). Is the architecture sufficient to actually produce the P1-P5 findings?` },
  { lens: 'framework-sufficiency', prompt: `You are an ML-platform engineer. ${GOAL}\n\nFOCUS: Are the chosen frameworks (LangChain/LangGraph, the tiered reasoning_client with local Ollama + Claude-Max, Phoenix/OTel, MLflow, Postgres checkpointer, Qdrant) the RIGHT and SUFFICIENT substrate to execute the actual research (embedding 1,400+ controls × 200+ LRF sets across dozens of models; graph algorithms; statistical testing at scale; GPU/compute)? What is fundamentally MISSING or mismatched: is DVC data-versioning actually wired? is Qdrant actually used? where does embedding compute run (the charter flags GPU need; the node is a Mac mini)? Does routing reasoning through an LLM seam fit work that is mostly deterministic numerical/statistical computation? Identify framework mismatches and missing capabilities that block the goal.` },
  { lens: 'downstream-tier-readiness', prompt: `You are the architect of the downstream Tier 2/Tier 3 projects. ${GOAL}\n\nFOCUS: The charter §1.5 mandates Tier-1 design requirements so Tier 2 (comparative) and Tier 3 (causal impact) can consume outputs: (1) framework-AGNOSTIC ARA knowledge-graph schema (works identically for NIST/CIS/SCF); (2) null results structured IDENTICALLY to positive findings; (3) CONFIDENCE SCORES on all findings (Tier 3 ML features); (4) P2 topology graphs designed for MULTI-GRAPH COMPOSITION (cross-framework blast-radius diffusion). Inspect src/state.py (HCGRCState: hypotheses/findings/eda_artifacts) and any schema/artifact code. Are these four requirements actually realizable in the current data model, or will Tier-1 outputs foreclose Tier 2/3? This is a goal requirement, not optional.` },
  { lens: 'independence-and-integrity', prompt: `You are a research-integrity / pre-registration reviewer. ${GOAL}\n\nFOCUS: The program is SINGLE-OPERATOR (charter §8.5) — the same person forms hypotheses AND approves Gate 2, with independence claimed via "structural transparency" (code gates, append-only PROV, RFC-3161 timestamps). Interrogate whether this actually yields a CREDIBLE confirmatory claim a journal/reviewer would accept: where can operator bias still leak (the operator sees exploratory results before approving the hypothesis lock at Gate 2 — can that shape the hypotheses? is the RFC-3161 timestamping actually implemented? is the Gate-2 "cryptographically logged" claim real in code?). Is the independence model sufficient for the goal of a publishable, credible empirical result, or a methodological weakness reviewers will reject?` },
  { lens: 'gaps-critic', prompt: `You are a skeptical principal investigator doing a pre-mortem. ${GOAL}\n\nFOCUS: Assume the project FAILS to achieve its goal. What in the design/architecture/specs/implementation is the most likely cause that the other lenses might miss? Look for: capabilities the goal REQUIRES but nothing provides; internal contradictions between charter, ADRs, SAP, and code; sequencing risks (governance built before science); anything that would make the eventual P1-P5 findings un-publishable or the platform unable to actually run an end-to-end study. Be concrete and cite evidence. Do not repeat obvious stub-not-implemented-yet observations unless they reveal a deeper design problem.` },
]

phase('Critique')
const lensResults = await parallel(LENSES.map((l) => () =>
  agent(l.prompt, { label: `lens:${l.lens}`, phase: 'Critique', schema: FINDING, agentType: 'Explore' })
    .then((r) => ({ ...r, lens: l.lens }))
))

const allFindings = lensResults.filter(Boolean).flatMap((r) => (r.findings || []).map((f) => ({ ...f, lens: r.lens })))

phase('Adjudicate')
// One adjudicator dedupes, reality-checks against the actual code/docs, and ranks —
// guards against architectural-critique inflation (the loose-prompt failure mode).
const ADJ_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    summary: { type: 'string', description: '3-5 sentence honest verdict: can the design achieve the goal as-is? what are the load-bearing problems?' },
    confirmed: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          title: { type: 'string' },
          kind: { type: 'string' },
          severity: { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
          rationale: { type: 'string' },
          recommendation: { type: 'string' },
        },
        required: ['title', 'kind', 'severity', 'rationale', 'recommendation'],
      },
    },
    rejected_or_inflated: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'confirmed', 'rejected_or_inflated'],
}
const adjudication = await agent(
  `You are the adjudicating principal investigator. ${GOAL}\n\n` +
  `Below are raw goal-level findings from 7 expert lenses. DEDUPE them, REALITY-CHECK each against the actual docs/code (read ${REPO} as needed — do not take a lens's word for it), DROP anything that is just "not implemented yet (expected Phase-0 stub)" unless it reveals a deeper DESIGN problem, and DROP architectural-critique inflation. Keep only goal-level problems that genuinely threaten achieving the objective or that mean the specs/architecture are actually wrong/insufficient. Rank by how load-bearing they are. Give an honest top-line verdict: as designed, can this platform achieve its goal, and what are the real blockers?\n\n` +
  `RAW FINDINGS:\n${JSON.stringify(allFindings, null, 1).slice(0, 60000)}`,
  { label: 'adjudicate', phase: 'Adjudicate', schema: ADJ_SCHEMA, agentType: 'Explore' }
)

log(`Goal-vs-design: ${allFindings.length} raw lens findings -> ${adjudication.confirmed.length} confirmed goal-level problems`)
return { raw_count: allFindings.length, adjudication, raw: allFindings }
