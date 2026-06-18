.PHONY: install install-core test test-all lint format typecheck lock ci clean

UV := uv

# Install all optional backends from the pinned lockfile.
install:
	$(UV) pip install -e ".[all]" --require-hashes -r requirements.lock

# Install dependency-free core only (no backends, works fully offline).
install-core:
	$(UV) pip install -e "." --require-hashes -r requirements-core.lock

# Unit tests — no services required.
test:
	pytest -q

# Full test suite with coverage — requires Postgres + Qdrant (see CI for service setup).
test-all:
	pytest -q --cov=assay_engine --cov-report=term-missing --cov-fail-under=90

lint:
	ruff check src tests

format:
	ruff format src tests

typecheck:
	mypy --strict src/assay_engine

# Regenerate all three pinned lockfiles (requires uv).
lock:
	bash scripts/regenerate_lockfiles.sh

# Local CI simulation: lint + typecheck + unit tests. Matches the core CI job.
ci: lint typecheck test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
