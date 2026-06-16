# Contributing to hc-assay

Thanks for your interest. hc-assay is a **dataset-agnostic engine** — the single architectural
rule (ADR-0002) is that the engine never imports dataset specifics. Keep that in mind for any
change under `src/assay_engine/`.

## Development setup

```bash
# create an environment (Python 3.11–3.14)
python -m venv .venv && source .venv/bin/activate
# or: uv venv .venv && source .venv/bin/activate

# dependency-free core + dev tooling
pip install -e ".[dev]"
# everything (all optional backends) for the integration tests
pip install -e ".[dev,all]"
```

## Before you open a PR

All three must pass (CI enforces them):

```bash
ruff check . && ruff format --check src tests
mypy --strict src
pytest -q
```

- The **core** lane runs with no optional backends installed (the engine must import and
  unit-test offline — ADR-0006). Don't add a top-level import of an optional backend; import it
  lazily inside the function that needs it.
- New behavior needs a test. Methodology/security-class code needs a *negative* test (the thing
  it refuses must be proven to raise).
- Architectural decisions go in `docs/decisions/ADR-XXXX-*.md`.

## Project layout

- `src/assay_engine/` — the engine (contracts, methodology, baseline, the five seams, the
  composed `pipeline.run_study`, provenance, registry). Dataset-agnostic.
- `docs/` — CHARTER, METHODOLOGY, GOVERNANCE, ARCHITECTURE, GLOSSARY, ADRs.
- `examples/` — a runnable, synthetic reference study.
- `tests/` — unit tests (core) + `tests/integration/` (need backends/services).
