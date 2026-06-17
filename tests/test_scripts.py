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


def test_license_gate_closes_the_report_file(tmp_path):
    # #F-050: the report must be opened via a context manager so the fd is closed deterministically.
    # Discriminating: intercept the module's open() and capture the file handle; after main()
    # returns, assert it is .closed. A bare json.load(open(...)) leaves the handle open (closed
    # only later by GC), so this fails when the context-manager fix is reverted.
    import builtins
    import json

    gate = _load("scripts/license_gate.py", "license_gate_fd")
    p = tmp_path / "licenses.json"
    p.write_text(json.dumps([{"Name": "ok", "Version": "1", "License": "MIT"}]), encoding="utf-8")

    handles = []
    real_open = builtins.open

    def tracking_open(*a, **k):
        fh = real_open(*a, **k)
        handles.append(fh)
        return fh

    gate.open = tracking_open  # module globals win over builtins for the bare open() call
    rc = gate.main(str(p))
    assert rc == 0
    assert handles and all(h.closed for h in handles), (
        "license_gate left the report file open (#F-050)"
    )


def test_transcript_scrub_redacts_operator_pii():
    # #F-024 (mandate-compatible mitigation): transcripts are committed as provenance per the
    # campaign mandate, but the capture scrubber must mask operator PII — email addresses and the
    # home-path username — so identity is not published. The path STRUCTURE is preserved.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_pii")
    out = cap._scrub("user me@example.com at /Users/somebody/hc-assay/x.py and /home/somebody/y")
    assert "me@example.com" not in out
    assert "somebody" not in out
    assert "/Users/[REDACTED]/hc-assay/x.py" in out  # structure kept, username masked
    assert "/home/[REDACTED]/y" in out


def test_transcript_scrub_redacts_bare_operator_username():
    # #G-007: the operator username must be redacted wherever it appears (git author strings,
    # project-dir slugs like -Users-<name>-..., prose), not only inside /Users|/home paths.
    from pathlib import Path

    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_user")
    name = Path.home().name
    if not name or len(name) < 4:
        import pytest

        pytest.skip("home username too short to redact safely")
    text = f"git author: {name} <x@y.z>; project dir -Users-{name}-hc-grc"
    out = cap._scrub(text)
    assert name not in out  # bare handle masked everywhere, not only in a /Users path


def test_transcript_scrub_redacts_username_in_project_dir_slug():
    # #H-018: the Claude project-dir slug (-Users-<name>-...) must have its username redacted at
    # ANY length (the bare-token rule skips short handles to avoid over-redaction, but the slug
    # form is unambiguous PII).
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_slug")
    out = cap._scrub("dir: -Users-tj-hc-grc and -home-ci-proj")  # short names
    assert "-Users-tj-" not in out and "-home-ci-" not in out
    assert "-Users-[REDACTED]-hc-grc" in out and "-home-[REDACTED]-proj" in out


def test_copy_scrubbed_scrubs_non_jsonl_text_files(tmp_path):
    # #CV-O-1: the session subtree holds .json workflow/subagent transcripts; redaction must apply
    # to EVERY text file, not only .jsonl, or operator PII + secrets leak into committed files.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_nonjsonl")
    src = tmp_path / "wf.json"  # a .json (NOT .jsonl) workflow transcript
    src.write_text('{"path": "/Users/somebody/x", "tok": "Bearer abcdefghijklmnopqrstuv"}', "utf-8")
    dst = tmp_path / "out" / "wf.json"
    cap._copy_scrubbed(src, dst)
    out = dst.read_text("utf-8")
    assert "somebody" not in out and "/Users/[REDACTED]/x" in out  # path username scrubbed
    assert "abcdefghijklmnopqrstuv" not in out  # bearer token scrubbed


def test_copy_scrubbed_copies_binary_verbatim(tmp_path):
    # #CV-O-1: a genuinely binary file (undecodable) is copied unchanged, not corrupted.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_bin")
    src = tmp_path / "blob.bin"
    src.write_bytes(b"\xff\xfe\x00\x01binary")
    dst = tmp_path / "out" / "blob.bin"
    cap._copy_scrubbed(src, dst)
    assert dst.read_bytes() == b"\xff\xfe\x00\x01binary"


def test_example_uses_no_hardcoded_hmac_secret():
    # #F-048: the example must not carry a shippable, publicly-known HMAC secret a user could copy
    # into production. It derives a fresh random secret per run instead.
    src = (_ROOT / "examples" / "minimal_study.py").read_text(encoding="utf-8")
    assert b"example-study-secret-key".decode() not in src  # the stale weak literal is gone
    assert "os.urandom(32)" in src  # the fresh-per-run secret is in place
