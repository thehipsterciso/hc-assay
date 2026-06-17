"""Guards for repo scripts + examples (pass 3: #F-051, #F-048).

These exercise non-package files (scripts/, examples/) that the wheel never ships but that run
on every commit (transcript capture) or are copied by users (the example). Where a test targets
a file's *content* it reads THAT file and asserts both the corrected form and the absence of the
stale/insecure form (the artifact-vs-test fidelity rule).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bearer_token_scrub_covers_base64_chars():
    # #F-051: a bearer token containing base64 chars (+ / =) must be FULLY redacted, not split at
    # the first such char leaving a trailing fragment in the transcript.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts")
    text = "Authorization: Bearer eyJhbGc+iOiJIUzI1NiJ9.payload/signature=="
    scrubbed = cap._scrub(text)
    assert "[REDACTED]" in scrubbed
    # no recognizable token fragment survives
    for frag in ("eyJhbGc", "payload/signature", "/signature", "iOiJIUzI1NiJ9"):
        assert frag not in scrubbed, f"token fragment {frag!r} leaked past redaction"


def test_example_uses_no_hardcoded_hmac_secret():
    # #F-048: the example must not carry a shippable, publicly-known HMAC secret a user could copy
    # into production. It derives a fresh random secret per run instead.
    src = (_ROOT / "examples" / "minimal_study.py").read_text(encoding="utf-8")
    assert b"example-study-secret-key".decode() not in src  # the stale weak literal is gone
    assert "os.urandom(32)" in src  # the fresh-per-run secret is in place
