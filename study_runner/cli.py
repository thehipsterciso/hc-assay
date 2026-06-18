"""Study runner CLI — invoke as ``python -m study_runner <adapter_module> [--study NAME]``.

This is a thin orchestration wrapper, not part of the installable package. It imports an
adapter module (which registers its study plan via a ``make_plan()`` function), then calls
``run_study()`` with ``auto_approve`` as the gate handler.

Adapter convention::

    # my_study/adapter.py
    from assay_engine.pipeline import StudyPlan, auto_approve
    from assay_engine.methodology.preregistration import LocalHmacAuthority
    from pathlib import Path

    def make_plan(source: Path | None = None) -> StudyPlan:
        ...   # build and return a StudyPlan

The module is imported by importlib; ``make_plan()`` is called with no arguments (source path
should be embedded in the plan or read from env/config inside ``make_plan``). For interactive
gate review, replace ``auto_approve`` with a custom handler before wrapping in a scheduler.

Usage::

    python -m study_runner my_study.adapter
    python -m study_runner my_study.adapter --study my-study-name
    python -m study_runner my_study.adapter --prior-fingerprint abc123...
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import sys
import warnings
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_log = logging.getLogger("study_runner")


def _load_plan(adapter_module: str) -> object:
    """Import ``adapter_module`` and call its ``make_plan()`` factory."""
    try:
        mod = importlib.import_module(adapter_module)
    except ModuleNotFoundError as exc:
        _log.error("could not import adapter module %r: %s", adapter_module, exc)
        sys.exit(1)

    factory = getattr(mod, "make_plan", None)
    if factory is None or not callable(factory):
        _log.error(
            "adapter module %r must expose a callable make_plan() function", adapter_module
        )
        sys.exit(1)

    try:
        plan = factory()
    except Exception as exc:  # noqa: BLE001
        _log.error("make_plan() raised %s: %s", type(exc).__name__, exc)
        sys.exit(1)

    return plan


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="study_runner",
        description="Run an hc-assay study from an adapter module.",
    )
    parser.add_argument(
        "adapter_module",
        help="Dotted module path that exposes make_plan() (e.g. my_study.adapter)",
    )
    parser.add_argument(
        "--study",
        metavar="NAME",
        default=None,
        help="Override the study name (used as MLflow experiment run name).",
    )
    parser.add_argument(
        "--prior-fingerprint",
        metavar="SHA256",
        default=None,
        dest="prior_fingerprint",
        help="SHA-256 corpus fingerprint from the previous run for cross-run drift detection.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Write the provenance trail JSON to this path after a successful run.",
    )
    args = parser.parse_args(argv)

    from assay_engine.pipeline import StudyPlan, auto_approve, run_study

    plan = _load_plan(args.adapter_module)
    if not isinstance(plan, StudyPlan):
        _log.error(
            "make_plan() returned %s, expected StudyPlan", type(plan).__name__
        )
        sys.exit(1)

    _log.info("starting study %r from %s", plan.definition.name, args.adapter_module)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = run_study(
                plan,
                gate_handler=auto_approve,
                prior_corpus_fingerprint=args.prior_fingerprint,
            )
        except Exception as exc:  # noqa: BLE001
            _log.error("run_study failed: %s: %s", type(exc).__name__, exc)
            sys.exit(1)

    for w in caught:
        _log.warning("[%s] %s", w.category.__name__, w.message)

    _log.info(
        "study %r complete — phases=%s discovery_verdicts=%d scorecard=%s",
        result.study,
        [p.name for p in result.phases],
        len(result.discovery_verdicts),
        result.scorecard,
    )

    if args.output:
        out = Path(args.output)
        result.persist_trail(out)
        _log.info("provenance trail written to %s", out)

    # Emit the corpus fingerprint so the caller can pass it as --prior-fingerprint next time.
    print(json.dumps({"corpus_fingerprint": result.corpus_fingerprint, "study": result.study}))


if __name__ == "__main__":
    main()
