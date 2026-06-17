#!/usr/bin/env bash
# Regenerate the hash-pinned lockfiles from pyproject.toml (#G-016).
#
# Dependabot bumps the version ranges in pyproject.toml but cannot regenerate the uv lockfiles,
# so a Dependabot PR will fail the CI "requirements.lock is stale" gate until the lockfiles are
# regenerated. Run this on a Dependabot branch (or any PR that changes pyproject dependencies),
# then commit the updated requirements*.lock files:
#
#     scripts/regenerate_lockfiles.sh && git commit -am "chore: regenerate lockfiles"
#
# uv is pinned to the same version CI uses (#F-031) so the output matches the sync check exactly.
set -euo pipefail

UV_VERSION="0.11.21"

if ! command -v uv >/dev/null 2>&1 || [ "$(uv --version | awk '{print $2}')" != "$UV_VERSION" ]; then
  echo "installing uv==$UV_VERSION (CI-pinned) ..." >&2
  python -m pip install "uv==$UV_VERSION" >&2
fi

uv pip compile pyproject.toml --all-extras --universal --generate-hashes -o requirements.lock
uv pip compile pyproject.toml --extra dev --universal --generate-hashes -o requirements-core.lock

echo "regenerated requirements.lock + requirements-core.lock — review and commit them."
