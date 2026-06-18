# HC-Assay Survey Instrument — Question Design Rationale

**Version:** 1.0.0
**Last updated:** 2026-06-18

This document explains the design rationale for each category of questions in the HC-Assay GRC survey instrument. It is written for the peer researcher or methodologist who will challenge every design decision — because those challenges are the mechanism by which the instrument improves.

Each section describes what the question category is trying to detect, why the specific operationalization was chosen over alternatives, what the known limitations of the approach are, and what we deliberately chose not to ask.

---

## 1. Governance Structure Questions

### What we are trying to detect

Governance structure questions are designed to distinguish between organizations where security governance is a structural property of the organization — something with real authority, a defined perimeter, and documented accountability — and organizations where governance is a label applied to a set of activities that would happen anyway under a different name.

The hypothesis this category serves is RQ4 (CISO reporting line as failure predictor) and contributes to RQ1 (framework inflation). The theoretical model is that governance structure precedes program quality: organizations that have not solved the structural question of who is accountable for security, with what authority, are unlikely to execute sophisticated risk management or compliance programs effectively.

### Why these are not "do you have a CISO" questions

A binary question about CISO role existence captures almost nothing useful. CISO titles are held by individuals whose actual scope ranges from equivalent to a VP of Engineering Security at a Fortune 100 firm to a senior IT manager at a 300-person company who was given a new business card. The title is not the measurement.

The governance structure items ask instead about:

- **Reporting line specificity** — not "does a CISO exist" but "to whom does the CISO report, and is that relationship documented in an org chart." The distinction between reporting to the CTO versus the CEO versus the Board Chair has empirically distinct implications for program authority and budget access. We want the specific relationship, not a self-assessment of whether it is "good."

- **Budget authority specificity** — not "does security have a budget" but "who approves the security budget, and does the CISO have line-item veto or proposal authority." Organizations where the CISO proposes the security budget and a non-security executive revises it downward without consultation have a structurally different governance model from organizations where the CISO owns a dedicated budget line.

- **Policy review documentation** — not "do you have policies" but "when were your policies last reviewed, and by whom." Policies that have not been reviewed since they were written are not governance; they are documentation archaeology.

### Known limitations

The governance structure items rely on self-report by the respondent, who has an obvious incentive to describe their program favorably. The mitigation is specificity: it is easier to misrepresent a qualitative judgment ("we have strong governance") than a specific fact ("our CISO last presented to the board in Q4 2023"). We use factual operationalizations wherever possible and treat Likert-format items in this category as lower-confidence measurements.

---

## 2. Risk Quantification Questions

### What we are trying to detect

Risk quantification questions are designed to distinguish between organizations that use dollar-denominated risk analysis — expected monetary value as the basis for prioritization — and organizations that use qualitative risk ratings (high/medium/low or equivalent). This distinction drives RQ5 (risk quantification gap hypothesis).

The theoretical basis is drawn from the FAIR (Factor Analysis of Information Risk) methodology: the argument that qualitative risk ratings produce systematically different resource allocation decisions than quantitative analysis, and specifically that qualitative ratings tend to produce risk registers full of "high" items with no triage discipline. If this argument is empirically supported across the study population, it surfaces in the data. If it is not, we report that.

### Why we ask about dollar-quantified risk versus qualitative ratings

The practitioner literature contains strong advocacy for quantitative risk methods — FAIR and equivalents — and equally strong practitioner resistance based on the perceived difficulty of the quantification exercise. Almost no published research has tested whether organizations that use quantitative methods produce materially different outcomes.

We operationalize this as a factual question about how risk is communicated to decision-makers: specifically, whether risk outputs are expressed as expected annual loss in dollar terms or as qualitative ratings. This is a cleaner measurement than asking about methodology (many organizations claim to use "a FAIR-like approach" without performing actual quantification) and it directly operationalizes the variable that is theorized to matter — whether executives making budget decisions are presented with dollar amounts or category labels.

### FAIR methodology influence

The FAIR Open FAIR Body of Knowledge provides the theoretical framework for the risk quantification items, specifically the distinction between Loss Event Frequency and Loss Magnitude as the two primary components of risk quantification. Our items do not require respondents to use FAIR terminology, but the underlying construct — whether risk is quantified as probable monetary loss — is derived from the FAIR model.

We are explicit about this influence because it is a potential source of construct bias: if FAIR is correct that quantitative analysis produces better outcomes, and we operationalize risk quantification in a way that tracks whether organizations use FAIR-adjacent methods, we are not testing whether quantitative analysis works — we are testing whether organizations that follow a specific methodology framework have better outcomes. This is a limitation we acknowledge. The Wave 1 items are designed to minimize this conflation by measuring the output (dollar-denominated risk communication) rather than the method label.

### Known limitations

The key limitation is that self-reported use of quantitative risk methods may not reflect actual practice. An organization can truthfully say it uses dollar-denominated risk analysis and produce those numbers through a process that is poorly calibrated. Calibration of the quantification exercise is outside the scope of the survey instrument. We measure whether organizations claim to produce dollar-denominated outputs and whether those outputs demonstrably influence resource allocation, not whether the underlying analysis is epistemically sound.

---

## 3. Compliance-Outcome Linkage Questions

### What we are trying to detect

Compliance-outcome linkage questions test the core contrarian hypothesis of the entire study: RQ2, the claim that compliance certifications do not reliably predict security outcomes. We are trying to detect whether organizations that have invested heavily in certification programs have better actual outcomes than organizations that have not — and whether the organizations themselves believe this is the case.

### Why this is the core contrarian hypothesis

The prevailing market assumption is that compliance certification is a useful proxy for security maturity. Regulators, insurers, and procurement organizations routinely use certification status as a gating criterion for risk assessment. If this proxy is unreliable — if certification status predicts audit outcomes but not breach rates or incident response times — then significant resource allocation decisions in the industry are based on a broken measurement.

The prior literature suggesting this decoupling is real is scattered and largely qualitative. Practitioners know it from direct experience (the most compliant organizations they have worked in have not always been the most secure) but the empirical evidence is thin. HC-Assay is designed specifically to generate that evidence in a form that is reproducible and subject to hostile review.

### Why we do not simply ask "which certifications do you hold"

Certification status alone cannot test the hypothesis. To test whether certifications predict outcomes, we need outcome data. The compliance-outcome linkage items therefore pair certification status questions with outcome questions:

- **Certification scope documentation** — not "do you have SOC 2" but "do you have a documented analysis of what your SOC 2 covers and what it explicitly does not cover." This distinguishes organizations that understand what their certifications mean from organizations that treat the certificate as an unconditional maturity signal.

- **Outcome tracking independent of certification** — specific questions about whether the organization tracks incident rates, breach frequency, detection and containment times as separate metrics from its compliance dashboard. Organizations that cannot answer these questions independently of their compliance status are treating compliance as the measure rather than as one possible predictor.

- **Incident history relative to certification status** — the closest available operationalization of the actual outcome variable. We ask about incidents experienced in the past 24 months and the certification status at the time. This is imprecise; we do not control for threat environment, industry, or targeting probability. But it is the best available self-report proxy for the outcome variable of interest.

### Known limitations

Incident reporting is the most sensitive dimension of the instrument. Respondents have obvious incentives not to disclose significant incidents, particularly those that occurred while certified. The mitigation is that the items ask about incidents "of material consequence" that triggered a formal response — not about all incidents, which would be impossible to enumerate consistently. We expect underreporting and we will note it explicitly in Wave 1 findings. The relevant comparison is not between respondent-reported incident rates and ground truth; it is between reported rates across the certified and non-certified subpopulations, where underreporting biases are likely to be more symmetric.

---

## 4. Incident Response Agility Questions

### What we are trying to detect

IR agility questions are designed to measure whether organizations have operationalized their incident response capability — not whether they have a documented plan, which is close to universal among organizations sophisticated enough to respond to this survey, but whether that plan produces fast, cross-functional, well-practiced responses when activated.

The hypothesis contribution is primarily RQ3 (mid-market agility premium): the prediction that mid-market organizations, constrained by smaller teams and less process bureaucracy, may actually demonstrate better agility-adjusted IR performance than large enterprises with more resources but more coordination overhead.

### Why response time targets and tabletop frequency are not vanity metrics

The industry default for IR measurement is policy existence and tabletop exercise completion. These are vanity metrics: they measure whether an organization has done the minimum required to check the compliance box, not whether the response function works.

The HC-Assay IR items push past policy existence to:

- **Documented time targets** — specifically whether the organization has defined and tracks mean time to detect (MTTD) and mean time to contain (MTTC), and whether actual performance against these targets is reviewed by leadership. Organizations that do not track these numbers cannot learn from them.

- **Tabletop scope and frequency** — not just whether tabletops occur but whether they cross functional lines. A security-team-only tabletop is a drill. A tabletop that includes Legal, Finance, Communications, and operations leadership is a test of the actual response system that would activate during a real incident. The distinction is operationally significant and most self-report surveys do not distinguish between the two.

- **Cross-functional team composition** — whether the people named in the IR plan actually know they are in it, have been introduced to each other, and have practiced working together. A documented cross-functional team that has never met is not a response capability.

### Known limitations

Mean time to detect and contain are the most valuable IR metrics in the instrument and the most difficult to obtain accurate self-report data on. Many organizations do not track these numbers formally. The instrument allows respondents to report a range rather than a precise figure, which improves accuracy at the cost of analytical precision. We will report the distribution of MTTD and MTTC ranges rather than means, because means of self-reported ranges carry false precision.

---

## 5. Board-Level Integration Questions

### What we are trying to detect

Board-level integration questions operationalize the CISO reporting line and board engagement hypothesis (RQ4) and contribute to the governance structure scoring. We are trying to distinguish between security programs that have genuine executive and board-level integration — where security considerations demonstrably influence strategic decisions — and programs that produce security reporting that gets noted and filed without affecting decisions.

### Why CISO reporting line matters and how we ask about it

The reporting line question is the single most charged question in the instrument. CISOs who report to the CTO have strong professional incentives to believe this arrangement is not correlated with program failure. The question design has to produce accurate data despite this incentive.

Our approach is to ask about the formal reporting relationship (who has direct authority over the CISO role: annual review, budget input, role definition) separately from the functional working relationship (who does the CISO actually work most closely with day-to-day). These frequently diverge. The hypothesis is about formal authority, not working relationships, so we measure both and analyze them separately.

The specific distinction the hypothesis turns on — reporting to a non-CxO function versus reporting to CEO, COO, or Board — is operationalized factually: "Select the individual to whom the security leader in your organization has a formal reporting relationship." The response options include specific role types rather than a free-text field. This prevents the rationalization that typically occurs when respondents are asked to characterize their own reporting arrangement in qualitative terms.

### Why board cadence is not the primary measurement

Board reporting frequency is easy to report favorably: almost any security leader who cares about this question can arrange to get on the board agenda quarterly. We include cadence as a lower-weight signal and focus instead on the nature of engagement: specifically, whether board security discussions include decision-making items (budget approval, risk acceptance, strategy input) or are informational only.

A board that receives a security briefing four times a year and takes no decisions based on it has a different relationship to the security program than a board with an active security committee that approves the annual security budget line. Both would report "quarterly board reporting."

### Known limitations

Board-level integration is the dimension where social desirability bias is most likely to affect responses. Senior practitioners are likely to describe board engagement in favorable terms because unfavorable descriptions reflect negatively on their own programs. The factual operationalizations reduce this bias but do not eliminate it. We treat board-level integration scores as the least reliable dimension and weight our confidence in the Compliance-Outcome Linkage and Incident Response Agility findings accordingly.

---

## 6. What We Deliberately Excluded

**Vendor and tool usage questions.** We do not ask what security products the organization uses, which vendors it has contracted with, or what its technology stack looks like. This is the most common category of question in vendor-funded benchmarks and the least useful for the hypotheses we are testing. Tool usage data is useful for vendors making product decisions. It is not useful for testing whether GRC program structure predicts security outcomes.

**Respondent satisfaction and opinion items.** We do not ask respondents whether they are satisfied with their security program, whether they think GRC tools are useful, or whether they believe their executive team understands security risk. Opinion items produce opinion data, which cannot contribute to the factual-outcome hypotheses we are testing.

**Regulatory penalty history.** We considered asking about regulatory enforcement actions and decided against it. The population of respondents who have experienced material regulatory action is too small in Wave 1 to support subgroup analysis. The question would produce a floor effect and raise respondent concern about disclosure without contributing to the primary hypotheses.

**Individual-level performance data.** We do not ask about individual CISO compensation, performance review history, or tenure at current organization. These items would be useful for individual-level career research. They are not useful for program-level GRC analysis and would increase survey abandonment.

**Questions that could identify the respondent's organization.** Any item whose answer, combined with other disclosed fields (industry, size band, region), could narrow identification to fewer than five organizations in our sampling frame is excluded. Privacy-preserving instrument design is not a nice-to-have; it is a precondition for honest response data.
