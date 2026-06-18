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
import platform
import re
import socket
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
    # password-class env vars (#B-12-1): PGPASSWORD, DATABASE_PASSWORD, DB_PASSWORD, DB_PASS,
    # REDIS_PASSWORD, etc. — absent from the _TOKEN/_KEY/_SECRET rules above. These appear in
    # `env`/`printenv` output and in psycopg error messages captured in agent transcripts.
    # Boundaries: _PASS\b avoids BYPASS/COMPASS; PGPASSWORD matched explicitly (ends in GPASSWORD,
    # not _PASSWORD). No minimum-length floor — DB_PASS=pw is unambiguous credential context.
    re.compile(r'((?:PGPASSWORD|_PASSWORD|_PASS\b)"\s*:\s*")[^"]+?(")'),
    re.compile(r"((?:PGPASSWORD|_PASSWORD|_PASS\b)=)[^\s\"']+"),
    # DSN URI userinfo (#L-13-P1): credentials embedded in a URI authority (scheme://user:pass@host)
    # are NOT caught by the email regex (which requires a real TLD — '@localhost' has none) and are
    # absent from the env-var _PASS patterns. A psycopg connection string printed by the engine or
    # in agent Bash output would expose the password verbatim. Capture the '://' prefix and '@'
    # suffix as sentinels so the URI structure is preserved for readability; only the credentials
    # are replaced.
    re.compile(r"(://)[^@\s]+(@)"),  # ://user:pass@ → ://[REDACTED]@
    # libpq keyword form 'password=<val>' (#L-13-P2): psycopg error messages and DSN strings
    # printed in Bash output use the keyword form 'password=s3cret' — not an env-var prefix name
    # so the _PASS\b patterns above don't cover it. '\bpassword' requires a word boundary, so
    # PGPASSWORD (no '_' before 'PASSWORD') is unaffected. Handles quoted and unquoted values;
    # terminates at whitespace, delimiters, and common DSN token separators.
    re.compile(
        r"(?i)(\bpassword\s*=\s*)(?:'[^']*'|\"[^\"]*\"|[^\s\"',;()\[\]]+)"
    ),  # password=<val> → password=[REDACTED]
    # operator PII (#F-024): email addresses, and the username segment of a home path
    # (/Users/<name>, /home/<name>) — the path STRUCTURE is kept, only the identity is masked.
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email → [REDACTED]
    re.compile(r"(/(?:Users|home)/)[^/\s\"']+"),  # /Users/<name> → /Users/[REDACTED]
    # The Claude project-dir SLUG (e.g. -Users-thomasjones-hc-grc): redact the username segment
    # regardless of length (#H-018) — the bare-token rule below skips short handles to avoid
    # over-redacting common words, but the slug form is unambiguous PII at any length.
    re.compile(r"(-(?:Users|home)-)[^-\s/\"']+"),  # -Users-<name>- → -Users-[REDACTED]-
    # Private (RFC1918) IPv4 addresses (#P10-PII-1): captured ifconfig/route/lsof output leaks the
    # operator's LAN subnet/gateway/host IP (e.g. 192.168.50.134, gateway 192.168.50.1) — infra-
    # identifying topology no other rule covers. Redact 10/8, 172.16/12, 192.168/16. Loopback
    # (127.0.0.0/8) and 0.0.0.0 are NOT private/identifying and are left (they appear in guard
    # tests/messages); public IPs (e.g. remote API endpoints) are not the operator's and are left.
    # Digit/dot lookarounds (not \b): the IP often abuts a JSON-escaped newline ("...\\n192.168...")
    # where \b fails because the escape's 'n' is a word char. Leading guard: not preceded by a
    # digit/dot (so we don't match inside a longer dotted number). Trailing guard: not followed by a
    # digit, and not by a dot-then-digit — this still bounds a longer IP ("10.0.0.50", "...0.134.5")
    # WITHOUT rejecting an IP that merely ends a sentence ("addr 192.168.50.134. Next ...") — the
    # earlier (?![\d.]) refused the sentence-final period and left the operator's real IP in cleartext
    # (#P10-PII-1 confirm-concern).
    re.compile(
        r"(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3})(?!\d)(?!\.\d)"
    ),  # RFC1918 → [REDACTED]
    # IPv6 ULA (fd00::/8, fc00::/7) and link-local (fe80::/10) addresses (#B-11-1): captured
    # ifconfig/ip addr output leaks the operator's internal IPv6 topology just as RFC1918 does
    # for IPv4. ULA prefixes (fd/fc) identify the operator's private LAN; link-local (fe80)
    # exposes interface-specific context. Loopback (::1) starts with ':' and is NOT matched.
    # Zone IDs (%utun0, %lo0, %en0) are included so the full token is redacted.
    re.compile(
        r"(?<![0-9a-fA-F:])(?:fe80|f[cd][0-9a-fA-F]{2}):[0-9a-fA-F:]{2,}(?:%[a-zA-Z0-9]+)?",
        re.IGNORECASE,
    ),  # IPv6 ULA + link-local → [REDACTED]
    # MAC addresses (#B-11-2): ifconfig output contains 'ether aa:bb:cc:dd:ee:ff' — persistent
    # hardware identity for the primary interface (not randomized on wired macOS). Six colon-
    # separated 2-hex-digit groups; lookbehind/lookahead guard against partial matches inside
    # longer hex strings or IPv6 addresses (which use 4-digit groups, not 2-digit groups).
    re.compile(
        r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}(?![0-9a-fA-F:])",
        re.IGNORECASE,
    ),  # MAC address → [REDACTED]
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


def _display_name_patterns() -> list[re.Pattern[str]]:
    """Redactions for the operator's full DISPLAY NAME (#J-002).

    The username/email rules leave the real name (e.g. a git ``user.name`` like "Thomas Jones")
    in cleartext — distinct operator PII that appears in git author strings, ``pyproject``
    ``authors=``, and prose, often right beside an already-redacted email. Derive candidate names
    from ``git config user.name`` and the ``ASSAY_SCRUB_NAMES`` env (comma-separated), redact each
    (and, for a multi-word name, its whitespace-flexible form). Length-guarded to avoid
    over-redacting common words.
    """
    names: list[str] = []
    extra = os.environ.get("ASSAY_SCRUB_NAMES", "")
    names.extend(n.strip() for n in extra.split(",") if n.strip())
    # Derive the operator name from SEVERAL sources — any one may be empty in a given context
    # (#J-002 follow-up): on this node local `git config user.name` is unset yet commits still
    # carry an author via global config / env, so a single-source lookup scrubbed nothing. Cover
    # the env author vars, git config, AND the actual last-commit author.
    for env_name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        v = os.environ.get(env_name, "").strip()
        if v:
            names.append(v)
    try:
        import subprocess

        for cmd in (["git", "config", "user.name"], ["git", "log", "-1", "--format=%an"]):
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                names.append(out.stdout.strip())
    except Exception:  # noqa: BLE001 - git absent/misconfigured must never break capture
        pass
    pats: list[re.Pattern[str]] = []
    seen: set[str] = set()
    for n in names:
        if len(n) < 4 or n in seen:
            continue  # too short → risks over-redacting common words; or already added
        seen.add(n)
        # Flexible inter-token whitespace (e.g. "Thomas   Jones"). NO leading \b: the name often
        # appears glued to a JSON-escaped newline ("...---\\nThomas Jones") where \b doesn't fire
        # because the escape's 'n' abuts the name (#J-002 follow-up). A trailing \b still prevents
        # matching inside a longer word (e.g. "Joneses"); the >=4-char guard bounds over-redaction.
        # CASE-INSENSITIVE (#J-002 confirm-concern round 2): the operator's name also appears
        # lowercased as actor/handle tokens — "thomas@hcgrc" (an initiated_by field), "thomas-jones
        # (human)" in actor tables — which a case-sensitive pattern misses. re.IGNORECASE covers all
        # casings; "Joneses"/"joneses" stays protected by the trailing \b either way.
        toks = n.split()
        pats.append(re.compile(r"\s+".join(re.escape(t) for t in toks) + r"\b", re.IGNORECASE))
        # Redact each NAME TOKEN standalone too (#J-002 confirm-concern): the full-name pattern
        # leaves the operator's bare first/last name in cleartext — e.g. "Thomas approves ..." and
        # "Thomas builds and governs ..." appear in governance prose hundreds of times, uniquely
        # re-identifying the operator. Per-token redaction (len>=4, trailing \b, no leading \b for
        # the JSON-\n-glued case) closes it. Over-redaction is bounded: the tokens come only from
        # the verified operator name and the corpus contains no unrelated bearer of these tokens
        # (all 256 "Thomas" contexts were sampled — every one is an operator governance reference).
        for t in toks:
            if len(t) >= 4 and t.lower() not in seen:
                seen.add(t.lower())
                pats.append(re.compile(re.escape(t) + r"\b", re.IGNORECASE))
    return pats


def _repo_handle_patterns() -> list[re.Pattern[str]]:
    """Redactions for the operator's repo owner / GitHub handle (#J-008).

    The handle (the ``<owner>`` in ``github.com/<owner>/<repo>``, e.g. in PR/issue URLs and
    ``gh --repo <owner>/...`` commands) is operator-identifying PII that NO existing rule covers:
    it is not an email (the email rule needs an ``@``), and it differs from the home-dir username
    the bare-username rule derives. Left uncovered it leaked across hundreds of transcript files
    (#J-008). Derive candidate handles from the git remotes and the ``ASSAY_SCRUB_HANDLES`` env;
    redact each as a bare token (length-guarded). A handle is a single unambiguous string, so no
    word-boundary is needed — redact it inside URLs, ``gh`` args, and the ``<handle>@`` email stem.
    Matched case-insensitively, and the distinctive STEM (handle minus a generic ``the`` prefix) is
    also redacted, because the handle leaks via derived names — e.g. ``hipsterciso-audience-profiles``
    (a skill name) embeds the handle minus ``the`` (#J-008 confirm-concern).
    """
    handles: list[str] = []
    extra = os.environ.get("ASSAY_SCRUB_HANDLES", "")
    handles.extend(h.strip() for h in extra.split(",") if h.strip())
    try:
        import subprocess

        out = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            for m in re.finditer(r"github\.com[:/]([^/\s]+)/", out.stdout):
                handles.append(m.group(1))
    except Exception:  # noqa: BLE001 - git absent/misconfigured must never break capture
        pass
    # Expand each handle with its distinctive stem (drop a leading generic "the") so handle-derived
    # names/slugs are covered too (#J-008 confirm-concern).
    expanded: list[str] = []
    for h in handles:
        expanded.append(h)
        if h.lower().startswith("the") and len(h) - 3 >= 4:
            expanded.append(h[3:])
    pats: list[re.Pattern[str]] = []
    seen: set[str] = set()
    for h in expanded:
        key = h.lower()
        if len(h) < 4 or key in seen:
            continue  # too short → risks over-redacting common words; or already added
        seen.add(key)
        if len(h) >= 8:
            # SEPARATOR-FLEXIBLE (#J-008 confirm-concern round 3): a GitHub handle is usually a
            # de-spaced brand ("thehipsterciso" = "The Hipster CISO"); the SPACED source brand
            # appears in prose/links and lets a reader reconstruct the redacted handle/email by
            # concatenation. Allow punctuation/whitespace between each character so the spaced,
            # hyphenated, and dotted forms all redact — while the de-spaced form (empty separators)
            # still matches. The separator class is space/._- ONLY, so unrelated prose cannot
            # accidentally spell out the handle, and common single tokens (e.g. "CISO") are NOT
            # redacted because the WHOLE letter sequence (…hipsterciso) must be present in order.
            pats.append(re.compile(r"[\s._-]*".join(re.escape(c) for c in h), re.IGNORECASE))
        else:
            pats.append(re.compile(re.escape(h), re.IGNORECASE))
    return pats


def _hostname_patterns() -> list[re.Pattern[str]]:
    """Redactions for the operator's machine/infrastructure hostname (#P9-MO/P9-PII-1).

    The scrubber masked email/username/display-name/handle but had NO rule for the host the node
    runs on, so the production machine's hostname (e.g. ``hc-macmini`` / ``hc-macmini.local``) and
    internal ``*.local`` mDNS/namespace hosts leaked into committed transcripts — operator/infra
    identity. Derive the MACHINE hostname from ``socket.gethostname``/``platform.node`` (and, on
    macOS, ``scutil --get LocalHostName``/``ComputerName``) and redact both its bare and ``.local``
    forms (a machine name is distinctive). Additional internal hosts (e.g. an RDF-namespace host
    like ``hc-grc.local``) are supplied via the comma-separated ``ASSAY_SCRUB_HOSTS`` env and have
    ONLY their ``.local`` form redacted — the bare label (often a project name like ``hc-grc``)
    appears in legitimate paths/repo refs and must not be over-redacted.
    """
    machine: list[str] = []
    try:
        machine.append(socket.gethostname())
    except Exception:  # noqa: BLE001
        pass
    try:
        machine.append(platform.node())
    except Exception:  # noqa: BLE001
        pass
    try:
        import subprocess

        for arg in ("LocalHostName", "ComputerName"):
            out = subprocess.run(["scutil", "--get", arg], capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                machine.append(out.stdout.strip())
    except Exception:  # noqa: BLE001 - scutil absent (non-macOS) must never break capture
        pass
    extra = [h.strip() for h in os.environ.get("ASSAY_SCRUB_HOSTS", "").split(",") if h.strip()]

    pats: list[re.Pattern[str]] = []
    seen: set[str] = set()

    def _base(name: str) -> str:
        n = name.strip()
        return n[: -len(".local")] if n.lower().endswith(".local") else n

    for name in machine:  # machine hostname → redact BARE + .local (distinctive identity)
        b = _base(name)
        if len(b) < 4 or b.lower() in seen:
            continue
        seen.add(b.lower())
        # Leading \b (#P10-PII-2): without it the bare hostname matches as a SUBSTRING, so a short/
        # common derived hostname (e.g. "host" on a CI runner) would corrupt legit content — "host"
        # inside "localhost" → "local[REDACTED]". The boundary requires a token start.
        pats.append(re.compile(r"\b" + re.escape(b) + r"(?:\.local)?\b", re.IGNORECASE))
    for name in extra:  # supplied namespace hosts → redact ONLY the .local FQDN form
        b = _base(name)
        if len(b) < 4 or ("local:" + b.lower()) in seen:
            continue
        seen.add("local:" + b.lower())
        pats.append(re.compile(re.escape(b) + r"\.local\b", re.IGNORECASE))
    return pats


_USERNAME_RE = _username_pattern()
_DISPLAY_NAME_RES = _display_name_patterns()
_REPO_HANDLE_RES = _repo_handle_patterns()
_HOSTNAME_RES = _hostname_patterns()


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
    # Redact the operator's full display name + bare name tokens too (#J-002) — distinct PII the
    # username/email rules leave in cleartext (git author strings, pyproject authors=, prose).
    for pat in _DISPLAY_NAME_RES:
        text = pat.sub("[REDACTED]", text)
    # Redact the repo owner / GitHub handle (#J-008) — operator-identifying PII in PR/issue URLs
    # and `gh --repo <handle>/...` commands that no email/username rule covers.
    for pat in _REPO_HANDLE_RES:
        text = pat.sub("[REDACTED]", text)
    # Redact the machine/infrastructure hostname (#P9-PII-1) — the production node's hostname and
    # internal *.local hosts that no other rule covers.
    for pat in _HOSTNAME_RES:
        text = pat.sub("[REDACTED]", text)
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
        #
        # FAIL CLOSED on redaction (#J-001): classify binary by an actual binary SIGNAL (a NUL
        # byte), NOT by UTF-8 validity. A transcript routinely embeds arbitrary subprocess stdout
        # (latin-1 dumps, truncated multibyte) inside JSONL strings; gating on strict decode meant
        # a single stray byte routed the WHOLE file to the verbatim branch and re-leaked it (the
        # CV-O-1 fix had turned an always-redact path into a fail-open one). Decode with
        # errors="replace" so redaction ALWAYS runs on text; only a genuinely binary blob (NUL
        # present) is copied verbatim.
        if b"\x00" in raw:
            data = raw  # genuinely binary — nothing to scrub
        else:
            data = _scrub(raw.decode("utf-8", errors="replace")).encode("utf-8")
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
