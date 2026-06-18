#!/usr/bin/env bash
# run_once.sh — minimal wrapper to run a study and record its output fingerprint.
#
# Usage:
#   bash study_runner/run_once.sh my_study.adapter
#
# The corpus fingerprint from this run is written to .last_fingerprint so you can pass
# it as --prior-fingerprint on the next invocation for cross-run drift detection.

set -euo pipefail

ADAPTER_MODULE="${1:?Usage: $0 <adapter_module> [--prior-fingerprint SHA256]}"
FINGERPRINT_FILE=".last_fingerprint"
PRIOR_FLAG=""

if [[ -f "$FINGERPRINT_FILE" ]]; then
    PRIOR=$(cat "$FINGERPRINT_FILE")
    PRIOR_FLAG="--prior-fingerprint $PRIOR"
    echo "[run_once] prior fingerprint: $PRIOR"
fi

# Activate the project virtualenv if present.
if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

OUTPUT=$(python -m study_runner "$ADAPTER_MODULE" $PRIOR_FLAG)
echo "$OUTPUT"

# Persist the current fingerprint for the next run.
CURRENT=$(echo "$OUTPUT" | python -c "import sys,json; print(json.load(sys.stdin)['corpus_fingerprint'])")
echo "$CURRENT" > "$FINGERPRINT_FILE"
echo "[run_once] fingerprint recorded: $CURRENT"
