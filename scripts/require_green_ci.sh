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
# The SHA the green run MUST match (#P10-CI-1): checking only the latest run's conclusion let a
# STALE green run (from an earlier commit) certify a newer, untested HEAD — the gate must bind the
# green result to the exact commit being merged, and fail closed if no completed run exists for it.
head_sha="$(git rev-parse "origin/$branch" 2>/dev/null || git rev-parse "$branch")"
read -r status conclusion run_sha < <(
  gh run list --branch "$branch" --workflow ci.yml --limit 1 \
    --json status,conclusion,headSha \
    -q '.[0].status + " " + (.[0].conclusion // "none") + " " + (.[0].headSha // "none")'
)
echo "latest ci run for '$branch': status=$status conclusion=$conclusion sha=$run_sha (HEAD=$head_sha)"
if [ "$run_sha" != "$head_sha" ]; then
  echo "::error::latest CI run is for $run_sha but '$branch' HEAD is $head_sha — CI for this commit has not completed; do NOT merge (#P10-CI-1)." >&2
  exit 1
fi
if [ "$status" = "completed" ] && [ "$conclusion" = "success" ]; then
  echo "CI is green for the current HEAD — safe to merge."
  exit 0
fi
echo "::error::CI for '$branch'@$head_sha is not green (status=$status conclusion=$conclusion) — do NOT merge (#CI-1)." >&2
exit 1
