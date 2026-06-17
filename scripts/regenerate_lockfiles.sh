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
# The resolution is ALSO pinned to a fixed point-in-time index via --exclude-newer (#K-OPS-1): the
# date lives in .uv-exclude-newer (single source of truth, read by CI too) so the regen is
# deterministic. Without it, uv resolves the NEWEST in-range version of every (largely
# unconstrained, transitive) dep at wall-clock time, so the committed lock would drift the instant
# any upstream publishes an in-range release and the "in sync" gate would go red on unrelated PRs.
# To intentionally pick up new releases, bump the date in .uv-exclude-newer and re-run this script.
#
# This regenerates ALL THREE gated lockfiles — requirements.lock, requirements-core.lock, AND
# requirements-build.lock (#K-OPS-2): the build lock is gated by CI too, so omitting it left a
# maintainer following this script still red on a build-backend bump with no scripted fix.
set -euo pipefail

cd "$(dirname "$0")/.."

UV_VERSION="0.11.21"
EXCLUDE_NEWER="$(tr -d '[:space:]' < .uv-exclude-newer)"

if ! command -v uv >/dev/null 2>&1 || [ "$(uv --version | awk '{print $2}')" != "$UV_VERSION" ]; then
  echo "installing uv==$UV_VERSION (CI-pinned) ..." >&2
  python -m pip install "uv==$UV_VERSION" >&2
fi

uv pip compile pyproject.toml --all-extras --universal --generate-hashes \
  --exclude-newer "$EXCLUDE_NEWER" -o requirements.lock
uv pip compile pyproject.toml --extra dev --universal --generate-hashes \
  --exclude-newer "$EXCLUDE_NEWER" -o requirements-core.lock
printf 'hatchling\neditables\n' > /tmp/build-reqs.in
uv pip compile /tmp/build-reqs.in --universal --generate-hashes \
  --exclude-newer "$EXCLUDE_NEWER" -o requirements-build.lock

echo "regenerated requirements.lock + requirements-core.lock + requirements-build.lock (exclude-newer=$EXCLUDE_NEWER) — review and commit them."
