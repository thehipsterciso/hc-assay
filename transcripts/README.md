# Transcripts (provenance)

This directory captures the **Claude session transcripts** behind the work in this repository,
so the provenance and effort of the agent interactions can be reviewed and audited alongside the
code.

## What's here

- `sessions/<session-id>.jsonl` — the main session transcript (one JSON object per line: prompts,
  tool calls, tool results, model output).
- `sessions/<session-id>/subagents/*.jsonl` — transcripts of subagents spawned in that session.
- `sessions/<session-id>/workflows/...` — workflow scripts and their subagent transcripts.
- `MANIFEST.json` — what was captured, when, and a SHA-256 of each file.

## How it's captured

A committed git hook (`.githooks/pre-commit`, enabled via `git config core.hooksPath .githooks`)
runs `scripts/capture_transcripts.py` before every commit, which snapshots the **active** session
(the most-recently-modified transcript) and its subtree into `sessions/`, then stages it. So
**every commit pulls in an up-to-date transcript snapshot.**

To enable the hook on a fresh clone: `git config core.hooksPath .githooks`.

## Scope & caveats (read before publishing)

- Credential-shaped secrets (API keys, OAuth/bearer tokens) are **redacted** on capture.
- Transcripts still contain **local filesystem paths** and may contain the **operator's email**
  and internal reasoning. They are legitimate provenance, but if this repository is made
  **public**, review this directory first — consider scrubbing further or excluding it
  (`git rm -r --cached transcripts/` + a `.gitignore` entry).
- These files are **not** shipped in the built wheel (only `src/assay_engine` is packaged).
- Transcripts are append-mostly JSONL, so they delta-compress well in git history.
