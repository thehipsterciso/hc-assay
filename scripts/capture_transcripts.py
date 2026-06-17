#!/usr/bin/env python3
"""Capture the active Claude session's JSONL transcript(s) into the repo for provenance.

Run by the pre-commit hook (.githooks/pre-commit) so every commit pulls in an up-to-date
snapshot of the agent interactions/effort behind it — an auditable record alongside the work.

What it captures: the *active* session (the most-recently-modified top-level transcript in the
Claude project dir) plus that session's ``<id>/`` subtree (subagents + workflow transcripts).
Other/unrelated sessions are left out. Credential-shaped secrets are redacted on the way in.

Honest scope: transcripts still contain local filesystem paths and may contain the operator's
email and internal reasoning. If this repo is published, review/exclude ``transcripts/`` first
(see transcripts/README.md). The wheel never ships them (only ``src/assay_engine`` is packaged).

Config: ASSAY_TRANSCRIPT_SRC overrides the source dir. Exits 0 on any error (never blocks a
commit).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_SRC = Path.home() / ".claude" / "projects" / "-Users-thomasjones-hc-grc"
DEST = Path(__file__).resolve().parent.parent / "transcripts" / "sessions"
MANIFEST = Path(__file__).resolve().parent.parent / "transcripts" / "MANIFEST.json"

# Credential-shaped secrets to redact (defense). Pass 3 (#F-024) extends this to operator PII —
# email addresses and the home-directory username embedded in filesystem paths — so committing
# transcripts as provenance (the campaign mandate) does not also publish the operator's identity.
# Reasoning content and the path STRUCTURE remain (legitimate provenance); see the README caveat
# for the full public-release consideration.
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{2,}"),  # any sk-ant- token incl. oat01 OAuth + placeholders
    re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    # bearer tokens incl. base64url/base64 JWTs — must cover + / = or the token is split at the
    # first such char and only the leading fragment is redacted (pass 3, #F-051).
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]{20,}"),
    # explicit OAuth/token env values: "...OAUTH_TOKEN":"<value>" / ...KEY=<value>
    re.compile(r'((?:OAUTH_TOKEN|_TOKEN|_KEY|_SECRET)"\s*:\s*")[^"]{8,}(")'),
    re.compile(r"((?:OAUTH_TOKEN|_TOKEN|_KEY|_SECRET)=)[^\s\"']{8,}"),
    # operator PII (#F-024): email addresses, and the username segment of a home path
    # (/Users/<name>, /home/<name>) — the path STRUCTURE is kept, only the identity is masked.
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email → [REDACTED]
    re.compile(r"(/(?:Users|home)/)[^/\s\"']+"),  # /Users/<name> → /Users/[REDACTED]
    # The Claude project-dir SLUG (e.g. -Users-thomasjones-hc-grc): redact the username segment
    # regardless of length (#H-018) — the bare-token rule below skips short handles to avoid
    # over-redacting common words, but the slug form is unambiguous PII at any length.
    re.compile(r"(-(?:Users|home)-)[^-\s/\"']+"),  # -Users-<name>- → -Users-[REDACTED]-
]


def _username_pattern() -> re.Pattern[str] | None:
    """A redaction for the bare operator username wherever it appears (#G-007).

    The /Users|/home path rule only masks the username inside a path; the same handle leaks via
    git author strings, prose, and the Claude project-dir slug (``-Users-<name>-...``). Derive the
    handle from the home directory and redact it as a standalone token too. Skipped for trivially
    short/None handles (e.g. a CI 'root') to avoid over-redacting common words.
    """
    try:
        name = Path.home().name
    except Exception:  # noqa: BLE001 - never break capture over a missing home
        return None
    if not name or len(name) < 4:
        return None
    return re.compile(re.escape(name))


_USERNAME_RE = _username_pattern()


def _scrub(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        if pat.groups == 2:
            text = pat.sub(r"\1[REDACTED]\2", text)
        elif pat.groups == 1:
            text = pat.sub(r"\1[REDACTED]", text)
        else:
            text = pat.sub("[REDACTED]", text)
    # Redact the bare operator username everywhere (#G-007), after the path rule so masked paths
    # don't re-expose it. Done last so it also catches it inside project-dir slugs / git authors.
    if _USERNAME_RE is not None:
        text = _USERNAME_RE.sub("[REDACTED]", text)
    return text


def _active_session(src: Path) -> Path | None:
    """The most-recently-modified top-level transcript = the live session."""
    candidates = sorted(src.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _copy_scrubbed(srcf: Path, dstf: Path) -> dict | None:
    try:
        dstf.parent.mkdir(parents=True, exist_ok=True)
        raw = srcf.read_bytes()
        # Scrub EVERY text file, not only .jsonl (#CV-O-1): the session subtree also holds .json
        # workflow/subagent transcripts that carry the same operator PII + credential-shaped
        # secrets — the old suffix==".jsonl" gate copied those RAW, bypassing redaction entirely.
        # Decode strictly to classify: text → scrub; genuinely binary (rare here) → copy verbatim.
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            data = raw  # binary blob — nothing to scrub
        else:
            data = _scrub(text).encode("utf-8")
        if dstf.exists() and dstf.read_bytes() == data:
            pass  # unchanged — still report it in the manifest
        else:
            dstf.write_bytes(data)
        return {
            "path": str(dstf.relative_to(DEST.parent.parent)),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    except Exception:  # noqa: BLE001 — provenance capture must never break a commit
        return None


def main() -> int:
    src = Path(os.environ.get("ASSAY_TRANSCRIPT_SRC", str(DEFAULT_SRC)))
    if not src.is_dir():
        return 0
    session = _active_session(src)
    if session is None:
        return 0
    sid = session.stem
    captured: list[dict] = []

    rec = _copy_scrubbed(session, DEST / f"{sid}.jsonl")
    if rec:
        captured.append(rec)

    # the session's subtree: subagents/ + workflows/ transcripts
    subtree = src / sid
    if subtree.is_dir():
        for f in sorted(subtree.rglob("*")):
            if f.is_file():
                rel = f.relative_to(subtree)
                rec = _copy_scrubbed(f, DEST / sid / rel)
                if rec:
                    captured.append(rec)

    try:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(
                {
                    "captured_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
                    "active_session": sid,
                    "n_files": len(captured),
                    "total_bytes": sum(c["bytes"] for c in captured),
                    "files": captured,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        return 0
    print(f"captured {len(captured)} transcript file(s) for session {sid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
