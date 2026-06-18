"""Airflow DAG example — illustrative only; Airflow is not a project dependency.

Adapt ADAPTER_MODULE and the schedule to your study. The DAG runs one task: it imports
your adapter's ``make_plan()`` and calls ``run_study()``, then persists the provenance trail
as an Airflow XCom value and writes it to a dated output file.

Install Airflow separately (``pip install apache-airflow``); it is not in hc-assay's extras.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Configuration — edit these
# ---------------------------------------------------------------------------
ADAPTER_MODULE = "my_study.adapter"   # dotted module path exposing make_plan()
DAG_ID = "hc_assay_study"
SCHEDULE = "@weekly"
# ---------------------------------------------------------------------------

from airflow import DAG  # noqa: E402
from airflow.operators.python import PythonOperator  # noqa: E402


def _run_study(**context: object) -> dict[str, object]:
    import importlib
    import json
    from pathlib import Path

    from assay_engine.pipeline import auto_approve, run_study

    mod = importlib.import_module(ADAPTER_MODULE)
    plan = mod.make_plan()

    # Retrieve the prior fingerprint from the previous DAG run's XCom, if available.
    ti = context.get("ti")
    prior_fp: str | None = None
    if ti is not None:
        try:
            prior_fp = ti.xcom_pull(task_ids="run_study", key="corpus_fingerprint", dag_id=DAG_ID, include_prior_dates=True)
        except Exception:  # noqa: BLE001
            pass

    result = run_study(
        plan,
        gate_handler=auto_approve,
        prior_corpus_fingerprint=prior_fp,
    )

    # Persist provenance trail to a dated file alongside the DAG.
    run_date = context.get("ds", datetime.utcnow().strftime("%Y-%m-%d"))
    out = Path(f"provenance_{result.study}_{run_date}.json")
    result.persist_trail(out)

    summary = {
        "study": result.study,
        "corpus_fingerprint": result.corpus_fingerprint,
        "n_discovery_verdicts": len(result.discovery_verdicts),
        "phases": [p.name for p in result.phases],
        "provenance_file": str(out),
    }

    # Push fingerprint for the next run's drift detection.
    if ti is not None:
        ti.xcom_push(key="corpus_fingerprint", value=result.corpus_fingerprint)

    return summary


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2026, 1, 1),
    schedule_interval=SCHEDULE,
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["hc-assay", "ml-study"],
) as dag:
    run_study_task = PythonOperator(
        task_id="run_study",
        python_callable=_run_study,
    )
