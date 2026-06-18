# Wave 1 Preliminary Findings — HC-Assay GRC Maturity Benchmarking Study

**Document status:** Living document — updated as data collection progresses
**Wave 1 collection opened:** 2026-06-18
**Target close:** N = 150 complete eligible responses, or 90 days from open (whichever comes first)
**Preliminary release threshold:** N ≥ 50
**Current N:** 0 (collection open; no responses yet received)

This document will be updated as collection progresses. Sections marked **[PENDING DATA]** will be populated when the collection threshold is met. The document structure and hypothesis register are published at collection open to establish the pre-registered analysis plan as part of the public record.

---

## Methodology Reminder

All findings in this document are verdicts produced by the HC-Assay analysis pipeline applied to scored survey responses. Verdicts are one of three types: **Supported**, **Contradicted**, or **Indeterminate**. No finding is published here that was not specified in the pre-registration before data collection opened.

For the full survey research methodology, see [METHODOLOGY.md](../METHODOLOGY.md).
For the scoring model, see [docs/scoring-model.md](../docs/scoring-model.md).
For the question design rationale, see [docs/question-rationale.md](../docs/question-rationale.md).
For the prior art context, see [docs/prior-art.md](../docs/prior-art.md).

---

## Wave 1 Pre-Registered Hypothesis Register

The following five hypotheses were pre-registered and cryptographically timestamped on 2026-06-18, before any Wave 1 responses were received. The pre-registration record is stored at `study_runner/wave-01-preregistration.json`.

Each hypothesis maps to one of the five scoring dimensions and one of the five research questions.

---

### H1 — Governance Structure: CISO Reporting Line and Program Score

**Hypothesis:** Organizations where the security leader (CISO or equivalent) reports to a non-CxO function (e.g., CTO, VP Engineering, VP IT) will score materially lower on the Governance Structure dimension (D1) than organizations where the security leader reports to the CEO, COO, CFO, General Counsel, or Board, controlling for organization size band.

**Operationalization:** D1 score comparison across reporting line categories; two-tailed independent samples; effect size threshold d ≥ 0.3.

**Decision rule:** Supported if d ≥ 0.3 and p ≤ 0.05 with N ≥ 80 in the analysis subgroup; Contradicted if d < 0.1 with N ≥ 80; Indeterminate otherwise.

**Corresponds to:** RQ4 (CISO reporting line as failure predictor), D1 (Governance Structure).

**Current verdict:** [PENDING DATA]

---

### H2 — Risk Quantification: Quantitative vs. Qualitative and Aggregate Score

**Hypothesis:** Organizations that use dollar-denominated risk quantification as the primary method for communicating risk to leadership will score higher on the aggregate maturity score than organizations using qualitative risk ratings (high/medium/low), with the difference concentrated in the Risk Quantification dimension (D2) and the Board-Level Integration dimension (D5).

**Operationalization:** Aggregate score and D2/D5 comparison between quantitative and qualitative subgroups; effect size threshold d ≥ 0.35.

**Decision rule:** Supported if d ≥ 0.35 on aggregate score and d ≥ 0.4 on D2, both at p ≤ 0.05; Contradicted if d < 0.1 on both; Indeterminate otherwise.

**Corresponds to:** RQ5 (risk quantification gap), D2 (Risk Quantification).

**Current verdict:** [PENDING DATA]

---

### H3 — Compliance-Outcome Linkage: Certification Count Does Not Predict Incident Experience

**Hypothesis:** The number of formal compliance certifications held (SOC 2, ISO 27001, PCI DSS, CMMC, or equivalent) will not demonstrate a statistically significant negative correlation with self-reported material incident frequency in the past 24 months, after controlling for organization size band and industry sector.

**Operationalization:** Point-biserial correlation between certification count (continuous) and incident indicator (binary: 0 = no material incident in 24 months, 1 = one or more material incidents); partial correlation controlling for size band and sector.

**Decision rule:** Supported (i.e., the null hypothesis of no meaningful negative correlation is supported) if |r| < 0.15 with N ≥ 100; Contradicted (i.e., certifications do predict lower incident rates) if r ≤ −0.25 at p ≤ 0.05; Indeterminate otherwise.

**Corresponds to:** RQ2 (compliance-resilience decoupling), D3 (Compliance-Outcome Linkage).

**Note:** H3 is directionally contrarian — the predicted outcome is the absence of a meaningful negative correlation. "Supported" for H3 means the data is consistent with certifications not predicting lower incident rates.

**Current verdict:** [PENDING DATA]

---

### H4 — Incident Response Agility: Mid-Market vs. Enterprise Agility

**Hypothesis:** Mid-market organizations (250–2,500 employees) will demonstrate higher Incident Response Agility dimension scores (D4) than organizations at the upper end of the study's size range (2,501–5,000 employees), after controlling for industry sector.

**Operationalization:** D4 score comparison between lower and upper size bands; two-tailed independent samples; effect size threshold d ≥ 0.25.

**Decision rule:** Supported if smaller band mean D4 > larger band mean D4 at d ≥ 0.25 and p ≤ 0.05; Contradicted if effect runs in the opposite direction at d ≥ 0.25 and p ≤ 0.05; Indeterminate otherwise.

**Corresponds to:** RQ3 (mid-market agility premium), D4 (Incident Response Agility).

**Current verdict:** [PENDING DATA]

---

### H5 — Board-Level Integration: Board Reporting Quality Predicts D5 Score Independent of Company Size

**Hypothesis:** The quality of board-level security engagement — operationalized as whether board security discussions include decision items (budget approval, risk acceptance) versus information items only — will predict Board-Level Integration dimension scores (D5) independently of organization size band. Specifically, organizations with decision-item board engagement will score at least 0.75 points higher on D5 on average than organizations with information-only board engagement, within the same size band.

**Operationalization:** D5 score comparison by board engagement type within size band strata; effect threshold of 0.75 points on the 0–4 scale; Welch's t-test within each size band stratum.

**Decision rule:** Supported if mean D5 difference ≥ 0.75 in two or more size band strata at p ≤ 0.05 each; Contradicted if mean D5 difference < 0.25 in all strata; Indeterminate otherwise.

**Corresponds to:** RQ4 (CISO reporting line and board integration), D5 (Board-Level Integration).

**Current verdict:** [PENDING DATA]

---

## Collection Status

| Metric | Value |
|---|---|
| Collection opened | 2026-06-18 |
| Target close | TBD (N = 150 or 90 days) |
| Complete eligible responses received | 0 |
| Responses excluded (ineligible) | 0 |
| Preliminary threshold (N ≥ 50) reached | No |
| Subgroup distribution available | No |

This table is updated as data collection progresses. It will be replaced with the full response distribution table once the preliminary threshold is reached.

---

## Preliminary Findings

**[PENDING DATA — will be populated when N ≥ 50]**

At N ≥ 50, this section will contain:

- Aggregate score distribution (mean, median, standard deviation, quartile breakdown)
- Dimension score distributions for all five dimensions
- Preliminary verdicts for hypotheses with sufficient subgroup N
- Power caveats for hypotheses where the preliminary N is insufficient for the planned test
- Early non-response patterns (if any significant differences between early and late respondents are apparent)

---

## Known Limitations of Wave 1

The following limitations are pre-committed — they were documented before data collection began, not added after the fact to explain inconvenient results.

**Population representativeness.** Wave 1 respondents are recruited through practitioner networks. This produces a sample that is likely to over-represent practitioners who are engaged in professional communities, have awareness of GRC benchmarking research, and have sufficient security program maturity to have opinions about their own governance. The lowest-maturity segment of the mid-market population — organizations with no formal security program at all — will be underrepresented. Findings about the low end of the maturity distribution are likely to reflect the low end of the practitioner-engaged population, not the overall mid-market.

**Self-report limitations.** All dimension scores are derived from self-reported survey data. The instrument uses behavioral and factual operationalizations to reduce self-assessment bias, but it cannot prevent deliberate misrepresentation or unconscious favorability bias. Incident reporting is the dimension most susceptible to underreporting.

**Cross-sectional design.** Wave 1 is a cross-sectional study. It can identify correlations between program structure variables and reported outcomes; it cannot establish causal direction. Longitudinal replication in Wave 2+ is required before causal claims can be made.

**Power limitations at preliminary N.** At N = 50, the study is adequately powered only for large effects (d ≥ 0.5). Preliminary verdicts for hypotheses requiring medium-effect detection (H1, H2, H4, H5) are likely to return Indeterminate at the preliminary stage even if the effect is present. This is expected and will be stated explicitly in the preliminary findings section.

**Single-operator study.** The HC-Assay study is produced by a single practitioner-researcher. The structural independence guarantees described in [METHODOLOGY.md](../METHODOLOGY.md) are real, but a multi-researcher team with independent analysis streams would provide stronger independence. This is a limitation of the operating model, not a defect in the methodology.

---

## How to Participate

Survey participation is open to security and GRC practitioners in mid-market organizations (250–5,000 employees). Eligible respondents are practitioners with direct operational knowledge of their organization's GRC program: CISO, VP/Director of Security, GRC Lead, vCISO, Head of Compliance, or equivalent.

Survey link: [SURVEY LINK — to be published at collection open]

All participation is voluntary and anonymous. See [METHODOLOGY.md](../METHODOLOGY.md) §7 for full ethical commitments and data handling practices.

---

## Version History

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-06-18 | Initial document published at collection open; hypothesis register and structure established |
