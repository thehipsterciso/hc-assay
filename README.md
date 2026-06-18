# HC-Assay

**HC-Assay is an independent, practitioner-led research effort measuring the gap between stated
GRC maturity and actual security outcomes across mid-market organizations. Unlike vendor-funded
benchmarks, this project has no commercial stake in its findings. We expect to publish results
that challenge conventional wisdom. We invite challenge, critique, and contribution.**

Every GRC benchmark in our industry is funded by a vendor with a stake in the findings.
HC-Assay is different: it is built on an open methodology, publishes its raw data, pre-registers
its hypotheses before collection, and scores external claims against a machine-built empirical
baseline — not against vendor-defined criteria. If our findings are wrong, the data is there to
prove it.

---

## The Research

| | |
|---|---|
| **Status** | Wave 1 — data collection open |
| **Target** | N = 150 (preliminary findings at N = 50) |
| **Population** | Mid-market organizations (100–5,000 employees) across security-relevant industries |
| **Survey link** | [Participate in Wave 1][SURVEY-LINK] |
| **Findings** | [findings/](findings/) |
| **Methodology** | [METHODOLOGY.md](METHODOLOGY.md) |
| **Scoring model** | [docs/scoring-model.md](docs/scoring-model.md) |
| **Prior art** | [docs/prior-art.md](docs/prior-art.md) |
| **Cite this work** | [CITATION.cff](CITATION.cff) |

[SURVEY-LINK]: #

### Pre-Registered Research Questions

1. **RQ1 — Governance:** Do formal governance structures (CISO reporting line, committee
   structure, documented authority) predict security outcome quality independent of budget size?
2. **RQ2 — Risk Quantification:** Do organizations that quantify risk in financial terms
   (FAIR-style) achieve materially different security outcomes than those using qualitative
   ratings?
3. **RQ3 — Compliance-Outcome Linkage:** Do compliance certifications (SOC 2, ISO 27001,
   NIST CSF) predict lower breach rates or faster incident response, controlling for organization
   size and sector?
4. **RQ4 — Incident Response Agility:** Does tested, rehearsed incident response (tabletop
   frequency, cross-functional coverage, defined escalation paths) predict materially faster
   mean-time-to-contain?
5. **RQ5 — Board Integration:** Does genuine board-level security integration (dedicated
   committee, quantified risk reporting, CISO direct access) predict better program outcomes
   than compliance-only board engagement?

---

## The Engine

HC-Assay's research runs on a dataset-agnostic empirical engine — also published here — that
builds a machine-independent baseline from any security dataset and tests external claims
against it. The engine is what makes the findings adversarially reproducible: a hostile
reviewer can clone the repository, re-run the analysis on the published data, and verify or
refute every finding.

The engine (`src/assay_engine`) is reusable. If you have a security or privacy dataset you
want to analyze with the same rigor, you can clone this repo and adapt it. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the adapter contract.

### Engine Quickstart

> **Not yet on PyPI.** Install from source:

```bash
git clone https://github.com/thehipsterciso/hc-assay && cd hc-assay
make install          # all optional backends, hash-pinned lockfile
make test             # unit tests (no services needed)
make ci               # lint + typecheck + unit tests (local CI simulation)
```

```python
from assay_engine import StudyPlan, run_study, auto_approve

# implement the adapter Protocols for your dataset, then:
plan = StudyPlan(definition=..., source=..., baseline_builder=..., authority=..., ...)
result = run_study(plan, gate_handler=auto_approve)
print(result.phases, result.discovery_verdicts, result.scorecard)
result.provenance   # append-only, hash-chained audit trail
```

A complete runnable example is in [`examples/minimal_study.py`](examples/minimal_study.py).

The engine runs local-first and data-sovereign: all computation, storage, observability,
and the local reasoning tier run on-box. See
[ADR-0003](docs/decisions/ADR-0003-local-first-data-sovereign.md).

---

## Repository Layout

```
hc-assay/
├── METHODOLOGY.md             ← GRC survey research methodology (this study)
├── CITATION.cff               ← Academic citation
├── findings/                  ← Published findings, wave by wave
│   └── wave-01-preliminary.md ← Wave 1 hypothesis register + collection status
├── data/                      ← Anonymized response data (published per wave)
├── docs/
│   ├── prior-art.md           ← How HC-Assay differs from vendor benchmarks
│   ├── scoring-model.md       ← Transparent GRC maturity scoring logic
│   ├── question-rationale.md  ← Why each question category was designed as it was
│   ├── METHODOLOGY.md         ← Engine research method (verdicts, firewalls, reproducibility)
│   ├── ARCHITECTURE.md        ← Engine vs adapter, adapter contract, onboarding
│   ├── CHARTER.md             ← Purpose, principles, operating model
│   ├── GOVERNANCE.md          ← Gates, pre-registration, provenance, data sovereignty
│   ├── GLOSSARY.md            ← Canonical terms
│   └── decisions/             ← Architecture Decision Records
└── src/assay_engine/          ← The reusable empirical research engine
```

---

## Contributing

Contributions are welcome at every level: survey methodology critique, data analysis,
engine development, and finding challenges. See [CONTRIBUTING.md](CONTRIBUTING.md).

To challenge a published finding, open a GitHub Issue with the label `finding-challenge`
and cite the specific hypothesis, the data, and the alternative interpretation.
We will engage seriously with every challenge. That is the point.

---

## Documentation

| Doc | Purpose |
|---|---|
| [METHODOLOGY.md](METHODOLOGY.md) | GRC survey design, sampling, bias mitigation, wave structure |
| [docs/scoring-model.md](docs/scoring-model.md) | Maturity scoring dimensions and formula |
| [docs/question-rationale.md](docs/question-rationale.md) | Why each question category was designed as it was |
| [docs/prior-art.md](docs/prior-art.md) | HC-Assay vs. existing benchmarks |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Engine research method (verdicts, firewalls, reproducibility) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Engine adapter contract and onboarding |
| [docs/CHARTER.md](docs/CHARTER.md) | Purpose, principles, scope |
| [docs/GOVERNANCE.md](docs/GOVERNANCE.md) | Gates, pre-registration, provenance, data sovereignty |

---

## License

Code: [Apache 2.0](LICENSE)  
Research outputs (findings, white papers, methodology documents): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

Cite using [CITATION.cff](CITATION.cff).
