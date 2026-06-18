# Prior Art: GRC Benchmarking Landscape and the HC-Assay Positioning

**Version:** 1.0.0
**Last updated:** 2026-06-18

---

## 1. The Existing Landscape

The GRC and cybersecurity benchmarking space is not empty. It is crowded with annual reports, maturity surveys, and state-of-the-industry studies produced by vendors, analysts, and consulting firms. Understanding what they measure — and what they systematically avoid measuring — is prerequisite to understanding why HC-Assay exists.

**Hyperproof and RegScale** publish benchmark data anchored to their customer bases. Because both are GRC platform vendors, their surveys are distributed to organizations that have already purchased a structured GRC workflow tool. This produces a selection bias that is fundamental, not incidental: the population studied is the population that has already invested in formal GRC tooling. The benchmark reflects how organizations with GRC tools use them, not whether GRC programs produce security outcomes. Findings that GRC platform adoption correlates with maturity are circular by construction.

**Splunk's State of Security** and **Fortinet's Global Threat Landscape Report** are capability benchmarks primarily motivated by product marketing. They measure threats detected, incidents investigated, and operational workload in ways that implicitly validate the detection and response product categories their authors sell. Neither attempts to measure the gap between compliance posture and breach frequency. Neither publishes methodology at a level of detail that would allow replication. Neither makes its raw data available.

**PwC's Global Digital Trust Insights** and comparable Big Four annual surveys are produced by consulting practices whose revenue depends on the GRC advisory engagements those surveys validate. They routinely find that organizations that have engaged senior advisory partners have more mature programs — an unsurprising result when the survey is distributed through client relationships. Structural conflict is embedded in the sampling design.

**Gartner's Magic Quadrant** and associated benchmark research evaluates vendor capabilities, not practitioner outcomes. It is explicitly a purchasing-decision tool. It provides no empirical data on whether any of the evaluated vendor categories produce measurable security improvements.

What none of these studies attempts, in any systematic way, is the central question of this research: do the specific decisions that GRC programs make — which frameworks to follow, how to structure the CISO reporting line, whether to use quantitative or qualitative risk analysis — predict actual security outcomes in a causally coherent direction?

---

## 2. The Structural Bias Problem

Vendor-funded research does not produce wrong findings because the people conducting it are dishonest. It produces systematically biased findings because the selection of questions, the operationalization of constructs, and the framing of conclusions are all subject to pressures that point in the same direction: validating the product categories the sponsor sells.

This is not a corruption argument. It is a structural observation. A GRC platform vendor that funds a study finding "GRC tools don't improve outcomes" has wasted its marketing budget. A consulting firm that publishes "senior advisory engagements don't move the needle" has undermined its pipeline. These outcomes are structurally unlikely regardless of the researchers' intentions, which is why the structural incentive is the relevant variable — not the integrity of any individual researcher.

The consequence for the field is a literature that is substantially agreement with whatever the sponsors were already selling. Framework adoption is measured as a proxy for maturity because the sponsors sell framework-adoption tooling. Board engagement is treated as a leading indicator because the sponsors sell programs positioned as elevating the CISO to board level. Quantitative risk analysis is underrepresented because the sponsors do not have quantitative risk products.

HC-Assay studies the questions the vendor literature cannot study: whether framework adoption predicts outcomes, whether board engagement improves program performance, whether quantitative risk analysis changes resource allocation in ways that matter. It can study these questions because no sponsor has a stake in the answer.

---

## 3. The Academic Research Gap

Academic security research exists and is growing, but the practitioner GRC domain remains underserved. A pattern consistently identified in systematic reviews of CISO and GRC research is that the empirical foundation is thin: most published work is either theoretical (frameworks, models, taxonomies) or qualitative (case studies, interviews, expert panels). Rigorous quantitative empirical work on security outcomes at the program level is scarce.

The academic literature on CISO effectiveness has been characterized as "nascent" — a domain where a handful of qualitative studies and non-representative surveys constitute the evidentiary base for consequential professional and organizational decisions. This is not a criticism of academic researchers; it reflects the genuine difficulty of obtaining outcome data from organizations with strong disclosure-aversion. But it means the practitioner community has been making program design decisions based on weak evidence, vendor assertions, and tribal knowledge.

HC-Assay operates in the gap between vendor-funded practitioner surveys (broad reach, structural bias) and academic research (methodological rigor, narrow scope and difficult-to-access populations). It brings practitioner access — the author's direct network in the CISO and GRC community — together with a methodology designed for hostile review.

---

## 4. How HC-Assay Is Different

**Independence as a structural property, not a claim.** HC-Assay accepts no vendor funding, no co-branding, no panel access in exchange for data sharing, and no consulting revenue from the organizations it studies. This is not a preference that could be walked back under financial pressure; it is the operating model. If it ceases to be true, the project's findings should be discounted accordingly, and this document would be the first place to update.

**Practitioner-led, not analyst-led.** The research questions are derived from operational experience running security and GRC programs in environments where the gap between maturity theater and actual resilience is directly observable. This is not a virtue claim — academic detachment has its own advantages. It is a claim about the source of the hypotheses, which are drawn from practitioner observation rather than from analyst frameworks.

**Reproducible by a hostile reviewer.** The anonymized response dataset is published to this repository at wave close. The scoring code is public. The methodology is versioned. The pre-registration is cryptographically timestamped before data collection opens. A researcher who disagrees with the findings can check the work — not just critique the conclusions.

**Three verdicts, not two.** The analysis engine returns supported, contradicted, or indeterminate — never a forced binary. Indeterminate is a first-class outcome that appears in the findings with the same prominence as positive results. This matters because most vendor benchmarks suppress indeterminate and null results. The absence of a finding is a finding.

**The instrument measures behavior, not self-assessment.** Survey items are designed to elicit specific, observable facts about program structure and decision-making — not to ask respondents whether they think their program is mature. Self-assessed maturity scores are a dependent variable of interest, not a measurement instrument.

---

## 5. What HC-Assay Is Not a Replacement For

HC-Assay is a research engine. It is not a GRC platform, a compliance tool, a risk management framework, or a consulting methodology. It does not produce recommendations for individual organizations. It does not certify anything. It does not help organizations pass audits.

It is also not a replacement for the vendor benchmarks it critiques. Hyperproof's dataset on GRC tool adoption among its customer base is genuinely useful for organizations trying to understand how other GRC teams use workflow tools. Gartner's vendor evaluation is genuinely useful for organizations making purchasing decisions. The limitation is not that those studies exist — it is that they are frequently cited as evidence about practitioner outcomes when they are evidence about something narrower.

HC-Assay produces findings about program-level decisions and security outcomes across a mid-market population. That is all it does. Users who need a GRC platform evaluation, a compliance maturity model, or a vendor selection guide should look elsewhere.
