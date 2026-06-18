# study_runner

A thin orchestration layer for running hc-assay studies on a schedule. Not part of the
installable `assay_engine` package — copy or symlink this directory into your study repository.

## Adapter convention

Your adapter module must expose a `make_plan()` function that returns a `StudyPlan`:

```python
# my_study/adapter.py
from assay_engine.pipeline import StudyPlan
from assay_engine.methodology.preregistration import LocalHmacAuthority
from pathlib import Path
import os

def make_plan() -> StudyPlan:
    source = Path(os.environ.get("STUDY_SOURCE", "data/corpus.json"))
    authority = LocalHmacAuthority(os.environb[b"STUDY_HMAC_SECRET"])
    return StudyPlan(
        definition=...,
        source=source,
        baseline_builder=...,
        authority=authority,
        ...
    )
```

## When to use each pattern

| Pattern | Use when |
|---------|----------|
| `python -m study_runner` | One-off run, debugging, CI job |
| `run_once.sh` | Cron scheduling with automatic fingerprint tracking |
| `example.crontab` | Weekly/daily recurring runs on a server |
| `airflow_dag_example.py` | You already run Airflow and want retry logic + XCom history |

## Quick start

```bash
# One-off run
python -m study_runner my_study.adapter

# With drift detection (pass fingerprint from previous run)
python -m study_runner my_study.adapter --prior-fingerprint abc123...

# Persist the provenance trail
python -m study_runner my_study.adapter --output provenance.json

# Via the shell wrapper (auto-tracks fingerprint in .last_fingerprint)
bash study_runner/run_once.sh my_study.adapter

# Cron (see example.crontab)
crontab -e   # paste the relevant line from example.crontab
```

## Gate handler

The CLI uses `auto_approve` (no human review). For studies that require operator sign-off
before confirmatory testing, wire a custom gate handler:

```python
# in make_plan() or a wrapper script:
from assay_engine.pipeline import run_study, GateReview
from assay_engine.orchestration.gates import GateDecision

def my_gate(review: GateReview) -> GateDecision:
    print(f"GATE: {review.summary}")
    answer = input("Approve? [y/N] ")
    return GateDecision(approved=answer.lower() == "y", gate=review.gate, reason="operator")

result = run_study(plan, gate_handler=my_gate)
```
