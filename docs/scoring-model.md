# HC-Assay GRC Scoring Model

**Version:** 1.0.0
**Effective date:** 2026-06-18
**Applies to:** Wave 1 and all subsequent waves unless superseded

---

## 1. Philosophy

Scoring is a by-product of measurement, not its purpose. The HC-Assay instrument is designed to test hypotheses about the relationship between GRC program structure and security outcomes. Aggregate maturity scores are a summary of the measurement — useful for comparing populations and tracking longitudinal change — but they are not the finding. The finding is the verdict rendered on each hypothesis.

This matters because the alternative — designing an instrument around producing a score — produces a fundamentally different instrument. Score-optimizing instruments incentivize respondents to answer in ways that maximize their score rather than in ways that accurately describe their program. They conflate the measure with the thing being measured. And they produce findings that tell you what the instrument measures, not what is happening in security programs.

The HC-Assay scoring model is designed to produce verdicts: **Supported**, **Contradicted**, or **Indeterminate**. Scores are an intermediate output that feeds the verdict logic. The three-verdict system is described fully in §2.

---

## 2. The Three Verdict Types

Every confirmed hypothesis test returns exactly one of three verdicts. There is no fourth option, no partial credit, and no forced binary.

**Supported** — The evidence from the scored survey responses is consistent with the pre-registered hypothesis at the pre-specified threshold. A supported verdict means the data does not contradict the claim and the effect, if present, is large enough and consistent enough to exceed the decision threshold. Supported is not "proven" — it is "the data is consistent with this being true, at the specified confidence level."

**Contradicted** — The evidence is inconsistent with the pre-registered hypothesis at the pre-specified threshold. A contradicted verdict means the data points in the opposite direction with sufficient consistency and magnitude to pass the decision rule. Contradicted is not "disproven" — it is "if this hypothesis were true, we would not expect to see what we see in the data."

**Indeterminate** — The method cannot decide. This verdict is returned when: the effect is present but below the detection threshold given the current N; the construct as operationalized cannot be cleanly distinguished from a confound; or the disagreement between hypothesis and data is small enough that measurement error and sampling variation are plausible explanations. Indeterminate is not a failure mode. It is the honest outcome when the evidence is insufficient to decide. A study that never returns Indeterminate is a study that is not being honest.

The three-verdict system is inherited from the hc-assay engine methodology (see [docs/METHODOLOGY.md](docs/METHODOLOGY.md)). The adaptation here is its application to a survey instrument rather than an ML-derived corpus.

---

## 3. How Survey Responses Map to Hypotheses

Each survey question belongs to exactly one of the five scoring dimensions described in §4. Responses are converted to scored values (0–4) using the dimension-specific scoring rubrics in the pre-registration document. These rubrics are fixed before Wave 1 data collection opens and do not change during a wave.

The mapping process is as follows:

1. **Response ingestion:** Raw survey responses are ingested by the hc-assay engine pipeline and converted to the canonical response schema. No manual scoring occurs at this stage.
2. **Dimension scoring:** The engine applies the dimension scoring rubrics to each response. Each of the five dimensions receives a score from 0 to 4 for each respondent. Rubrics are deterministic: the same response always produces the same score.
3. **Aggregate scoring:** The five dimension scores are averaged to produce an overall maturity score for each respondent (0–4 scale, one decimal place).
4. **Population-level analysis:** Hypothesis tests operate on the distribution of dimension scores and overall scores across the population, using the test statistics and thresholds specified in the pre-registration.
5. **Verdict assignment:** The engine returns a verdict for each pre-registered hypothesis.

The researcher does not touch individual response scores. The pipeline is the only path from raw response to verdict.

---

## 4. The Five Maturity Dimensions

### 4.1 Governance Structure

What it measures: the structural properties of the security governance program — whether the CISO function exists as a distinct role, where it sits in the organizational hierarchy, what authority it has over budget and policy, and whether governance is documented or informal.

Scored on: presence and documentation of governance charter; CISO or equivalent role existence; role independence from IT operations; policy review cadence; governance body composition.

Score 0: No documented security governance structure. Security responsibility is embedded in IT operations with no distinct security leadership role.
Score 1: Named security lead exists but reports into IT; governance is informal or undocumented; no dedicated security budget authority.
Score 2: Distinct security function; formal reporting relationship; some documented policies; security budget exists but is managed within IT cost center.
Score 3: Independent security function reporting to C-suite or above; documented governance charter; dedicated security budget with CISO authority.
Score 4: All of Score 3; governance charter reviewed annually; board-level security committee or equivalent; security function has veto authority over high-risk technology decisions.

### 4.2 Risk Quantification

What it measures: whether the organization uses quantitative methods (dollar-denominated risk analysis) or qualitative methods (high/medium/low ratings) for security risk prioritization, and whether risk analysis outcomes demonstrably influence resource allocation decisions.

Scored on: method used for risk prioritization; whether risk outputs are dollar-denominated; whether risk outputs demonstrably drive budget decisions; cadence of risk assessment; risk assessment scope.

Score 0: No formal risk assessment process. Risk decisions are made ad hoc.
Score 1: Qualitative risk ratings (high/medium/low) produced on an irregular basis; no documented linkage to budget decisions.
Score 2: Formal qualitative risk assessment on a regular cadence; risk outputs documented; some linkage to budget prioritization.
Score 3: Quantitative risk analysis for at least top-risk scenarios; dollar-denominated expected loss used in budget discussions; risk outputs formally reviewed by senior leadership.
Score 4: Full quantitative risk program (FAIR or equivalent); all material risk decisions dollar-denominated; risk analysis outputs formally reported to board; actuarial or insurance linkage.

### 4.3 Compliance-Outcome Linkage

What it measures: whether the organization treats compliance certifications as proxies for security maturity or as one input among several; whether compliance activities are tracked against outcome metrics rather than just certification status; and whether the organization can articulate what its certifications do and do not cover.

Scored on: certifications held; whether compliance status is conflated with security posture; whether security outcomes are tracked independently of compliance status; incident history relative to certification status.

Score 0: No formal compliance program; security activities driven entirely by reactive incident response.
Score 1: One or more certifications pursued or held; compliance status used as primary proxy for security maturity; no independent outcome tracking.
Score 2: Certifications held; compliance activities tracked; some awareness that certifications do not cover all risk; limited independent outcome measurement.
Score 3: Certifications held; explicit documentation of what certifications do and do not cover; independent outcome metrics tracked alongside compliance status.
Score 4: Certifications held; formal gap analysis between certification scope and risk exposure; outcome metrics tracked independently; compliance program explicitly designed to not substitute for risk-based security decisions.

### 4.4 Incident Response Agility

What it measures: the speed, coverage, and cross-functional integration of the organization's incident response capability — how quickly incidents are detected and contained, how frequently response capabilities are tested, and whether response crosses functional boundaries.

Scored on: mean time to detect; mean time to contain; tabletop exercise frequency and scope; cross-functional IR team composition; post-incident review process.

Score 0: No documented incident response plan. Incidents are handled ad hoc.
Score 1: IR plan exists but is untested; response is security-team-only; no formal post-incident review.
Score 2: IR plan tested annually or less; cross-functional team identified but not regularly exercised; post-incident review occurs inconsistently.
Score 3: IR plan tested 2+ times per year including tabletops; cross-functional team regularly exercised; formal post-incident review with documented lessons learned.
Score 4: All of Score 3; documented mean time to detect and contain targets with actual tracking; executive and board notification procedures tested; external IR retainer in place; red team or purple team exercises annually.

### 4.5 Board-Level Integration

What it measures: the depth and quality of security program integration at the board and executive leadership level — not whether a slide deck goes to the board, but whether board engagement translates into resource decisions, strategic alignment, and genuine accountability.

Scored on: CISO reporting line; board reporting cadence; nature of board security discussion (informational vs. decision-making); budget authority at CISO level; whether board members have security expertise.

Score 0: No board-level security reporting. Security is not a board agenda item.
Score 1: Security included in annual board agenda or as-needed incident briefings; no dedicated security budget authority at CISO level.
Score 2: Quarterly board security briefings; CISO or equivalent presents to board; some board engagement on security budget.
Score 3: Regular board security reporting with defined cadence; CISO reports to CEO, COO, or board directly; security budget formally approved at board level.
Score 4: All of Score 3; dedicated board security committee or audit committee sub-agenda; one or more board members with security domain expertise; board-level security KPIs tracked and reported.

---

## 5. Scoring Formula Transparency

There is no hidden weighting. The aggregate maturity score is a simple arithmetic mean of the five dimension scores.

```
Aggregate Score = (D1 + D2 + D3 + D4 + D5) / 5
```

Where D1 through D5 are the dimension scores for Governance Structure, Risk Quantification, Compliance-Outcome Linkage, Incident Response Agility, and Board-Level Integration respectively, each on a 0–4 integer scale.

The five dimensions are equally weighted. This is a deliberate methodological choice: we do not have sufficient prior evidence to claim that any one dimension is more predictive of security outcomes than another. Differential weighting requires justification from prior data. Wave 1 is designed in part to generate the evidence that would justify or refute differential weighting in Wave 2.

The scoring code is published and auditable. Any researcher who disagrees with this formula can apply a different formula to the published raw data and compare results.

---

## 6. What the Score Cannot Tell You

**It cannot tell you whether a specific organization is secure.** It is a population-level measurement instrument. An individual organization's score reflects how that organization's self-reported program structure compares to the Wave 1 sample distribution. It does not measure actual security outcomes for that organization.

**It cannot detect misrepresentation.** The instrument cannot determine whether a respondent accurately described their program. Validation of self-reported data against actual outcomes requires external data sources not available to this study. The best available mitigation is sampling practitioners with direct operational knowledge (see METHODOLOGY.md §3.2) and using behavioral questions rather than self-assessment items.

**It cannot control for confounders not in the instrument.** An organization's score on Incident Response Agility is not adjusted for industry-specific threat environment, prior incident history, or inherited technical debt. These variables affect outcome comparability across organizations.

**It does not measure security outcomes directly.** The instrument measures program structure and decision-making practices that are hypothesized to predict outcomes. The hypothesis tests determine whether those predictions are supported by the population data. Scores are intermediate measurements on the path to verdict, not outcome measurements.

**It is not a certification or an audit.** Nothing in the HC-Assay scoring model should be cited as evidence that an organization meets any compliance standard, regulatory requirement, or security benchmark.

---

## 7. Version History

| Version | Effective Date | Summary of Changes |
|---|---|---|
| 1.0.0 | 2026-06-18 | Initial scoring model for Wave 1 |

Changes to the scoring model between waves are logged here. Changes do not apply retroactively to waves that have already begun data collection. If a material scoring change is introduced before Wave 1 close, the change will be noted as a protocol deviation in the Wave 1 findings document and the Wave 1 data will be re-scored under both models to enable comparison.
