# HC-Assay Findings Directory

This directory contains the output of the HC-Assay GRC Maturity Benchmarking Study — the scored, adjudicated results of applying the HC-Assay methodology to collected survey data. It is not a repository of opinion or analysis; it is the structured output of a pre-registered, reproducible measurement process.

---

## What "Findings" Means Here

A finding in this context is a verdict — **Supported**, **Contradicted**, or **Indeterminate** — rendered on a pre-registered hypothesis by the HC-Assay analysis pipeline, accompanied by the evidence that produced it. Findings are not conclusions in the conventional sense. They are the output of a decision rule applied to data, where both the rule and the threshold were specified before the data was collected.

This distinction matters. It means:

- A finding labeled **Supported** does not mean the hypothesis is true. It means the data is consistent with the hypothesis at the pre-specified threshold. Replication is required before "supported" becomes a strong claim.
- A finding labeled **Contradicted** does not mean the hypothesis is false. It means the data is inconsistent with the hypothesis at the pre-specified threshold, given this population and this instrument.
- A finding labeled **Indeterminate** is not a null result to be ignored. It means the method cannot decide — the effect is below detection threshold, or the instrument's reach does not extend to the construct as operationalized. Indeterminate findings constrain the literature just as positive findings do.

All three verdicts are published with equal prominence. Studies that publish only supported findings are not reporting findings; they are reporting selection artifacts.

---

## Wave 1 Status

Wave 1 data collection opened 2026-06-18. Preliminary findings will be published to `wave-01-preliminary.md` when N ≥ 50 complete eligible responses have been received. Final Wave 1 findings will be published at wave close (target N = 150).

Current collection status: see [wave-01-preliminary.md](wave-01-preliminary.md).

---

## File Naming Convention

| File | Contents |
|---|---|
| `wave-01-preliminary.md` | Wave 1 preliminary findings (published at N ≥ 50, updated as collection continues) |
| `wave-01-final.md` | Wave 1 final findings (published at wave close) |
| `wave-02-preliminary.md` | Wave 2 preliminary findings |
| `wave-02-final.md` | Wave 2 final findings |

Findings documents are not deleted or superseded when a wave closes; both preliminary and final documents are retained as a record of how findings evolved during collection.

---

## How Findings Relate to White Papers

The files in this directory are the **raw methodology output**: hypotheses, verdicts, evidence summaries, limitations, and replication instructions. They are written for a technical audience — practitioners and researchers who want to evaluate the underlying analysis.

White papers synthesize findings for specific audiences:

- A white paper for CISOs and vCISOs may draw on Wave 1 findings to make program design recommendations, contextualized for the practitioner decisions those findings bear on.
- A white paper for boards and CROs may draw on the same findings to frame the governance and investment implications.
- An academic-format paper may present the methodology and findings in standard research paper structure.

White papers are downstream of findings. They cannot include claims not supported by a finding in this directory. If a white paper makes a claim that does not trace to a specific finding here, that is an error in the white paper.

White papers are published separately and linked from the repository README. They are not stored in this directory.

---

## How to Challenge a Finding

If you believe a published finding is wrong — that the data does not support the verdict, that the analysis has an error, that the instrument is measuring the wrong construct, or that the population is unrepresentative in a way that invalidates the conclusion — open a GitHub Issue with the label `finding-challenge`.

A valid challenge includes:

- The specific finding being challenged (wave, hypothesis number, verdict)
- The specific objection (methodological, statistical, population, instrument)
- Where available: your alternative analysis, your code, and your result

Challenges that meet this bar will be reviewed and responded to in writing. If a challenge identifies a genuine error, the finding will be corrected and the correction will be noted in the relevant findings document with a version stamp. Corrected findings are not deleted; the correction history is part of the record.

Challenges that are vendor advocacy or competitive positioning will be noted as such in the response.
