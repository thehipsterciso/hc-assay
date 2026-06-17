#!/usr/bin/env bash
# Pre-merge CI gate (#CI-1) — compensating control for an unenforceable required status check.
#
# Branch protection / required status checks are UNAVAILABLE on this repo's plan: it is private on
# a free tier, so `gh api repos/<owner>/<repo>/branches/main/protection` returns HTTP 403
# ("Upgrade to GitHub Pro or make this repository public"). GitHub therefore does NOT block merging
# a PR whose CI is red — the `all-checks` fan-in job is computed but nothing consumes it as a gate.
# That is the exact mechanism by which CI went silently red across several hardening passes (merged
# via --admin / un-gated). Making the repo public to enable protection is out of scope (it would
# publish the committed transcripts); upgrading the plan is an operator/billing decision.
#
# Until one of those changes, THIS is the gate: it exits non-zero unless the latest `ci` run for the
# branch concluded success. Run it before every merge and refuse to merge on failure:
#
#   scripts/require_green_ci.sh [branch]      # defaults to the current branch
#   scripts/require_green_ci.sh && gh pr merge <n> --merge --delete-branch
set -euo pipefail

branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
read -r status conclusion < <(
  gh run list --branch "$branch" --workflow ci.yml --limit 1 \
    --json status,conclusion -q '.[0].status + " " + (.[0].conclusion // "none")'
)
echo "latest ci run for '$branch': status=$status conclusion=$conclusion"
if [ "$status" = "completed" ] && [ "$conclusion" = "success" ]; then
  echo "CI is green — safe to merge."
  exit 0
fi
echo "::error::CI for '$branch' is not green (status=$status conclusion=$conclusion) — do NOT merge (#CI-1)." >&2
exit 1
