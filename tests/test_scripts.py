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


def test_scrub_fails_closed_on_invalid_utf8_bytes():
    # #J-001: a stray non-UTF-8 byte must NOT disable redaction for the whole file. The scrubber
    # decodes errors='replace' and classifies binary by a NUL byte, so a secret next to an invalid
    # byte is still scrubbed (the pass-6 strict-decode fix had made this fail OPEN).
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_failclosed")
    raw = b'{"out":"sk-ant-oat01-SECRETTOKEN1234567890 caf\xe9 /Users/somebody/x"}'  # invalid \xe9
    text = raw.decode("utf-8", errors="replace")
    out = cap._scrub(text)
    assert "sk-ant-oat01-SECRETTOKEN1234567890" not in out  # secret scrubbed despite the bad byte
    assert "somebody" not in out


def test_copy_scrubbed_scrubs_file_with_invalid_utf8(tmp_path):
    # #J-001 end-to-end: a .jsonl with an invalid byte is still scrubbed on copy, not copied raw.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_fc2")
    src = tmp_path / "t.jsonl"
    src.write_bytes(b'{"k":"Bearer abcdefghijklmnopqrstuv \x80 end"}')  # invalid \x80
    dst = tmp_path / "out" / "t.jsonl"
    cap._copy_scrubbed(src, dst)
    out = dst.read_bytes()
    assert b"abcdefghijklmnopqrstuv" not in out and b"[REDACTED]" in out


def test_scrub_redacts_operator_display_name(monkeypatch):
    # #J-002: the operator's full display name (from ASSAY_SCRUB_NAMES / git user.name) is redacted,
    # not just the email — distinct PII that leaked beside redacted emails.
    monkeypatch.setenv("ASSAY_SCRUB_NAMES", "Ada Lovelace")
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_name")
    out = cap._scrub("Author: Ada Lovelace <a@b.co>; also Ada   Lovelace in prose")
    assert "Ada Lovelace" not in out and "Ada   Lovelace" not in out  # flexible whitespace too
    assert "a@b.co" not in out  # email still scrubbed


def test_scrub_redacts_bare_name_tokens(monkeypatch):
    # #J-002 confirm-concern: the operator's bare first/last name (not just the full name) is
    # operator PII — "Thomas approves ..." appears in governance prose hundreds of times. Each
    # name token (len>=4) is redacted standalone, while a longer word containing it is protected.
    monkeypatch.setenv("ASSAY_SCRUB_NAMES", "Thomas Jones")
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_tokens")
    out = cap._scrub("Thomas approves the charter; Jones governs. The Joneses are unrelated.")
    assert "Thomas approves" not in out  # bare first name redacted
    assert "Jones governs" not in out  # bare last name redacted
    assert "Joneses" in out  # trailing \b protects the longer word
    # CASE-INSENSITIVE (#J-002 confirm-concern round 2): the name also leaks lowercased as actor
    # tokens — "thomas@hcgrc", "thomas-jones (human)" — which a case-sensitive pattern missed.
    low = cap._scrub('initiated_by="thomas@hcgrc"; actor thomas-jones (human); the joneses stay')
    assert "thomas" not in low and "jones (" not in low  # both casings redacted
    assert "joneses" in low  # still protected case-insensitively


def test_scrub_redacts_github_handle(monkeypatch):
    # #J-008: the operator's repo owner / GitHub handle leaks in PR/issue URLs and `gh --repo
    # <handle>/...` commands — operator PII no email/username rule covers. It is redacted while the
    # repo name is preserved (legitimate provenance).
    monkeypatch.setenv("ASSAY_SCRUB_HANDLES", "theninjacoder")
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_handle")
    out = cap._scrub(
        "gh issue list --repo theninjacoder/hc-assay; "
        "https://github.com/TheNinjaCoder/hc-assay/pull/28; "
        "skill ninjacoder-audience-profiles; brand: The Ninja Coder writes; "
        "a normal coder reviews and the ninja stays."
    )
    assert "theninjacoder" not in out.lower()  # handle redacted everywhere, case-insensitively
    assert "ninjacoder" not in out.lower()  # the distinctive STEM (handle minus "the") too (#J-008)
    assert (
        "The Ninja Coder" not in out
    )  # the SPACED source brand, reconstructable by concat (#J-008 r3)
    assert "hc-assay" in out  # repo name (not PII) preserved
    # NO over-redaction: a standalone common token that merely appears inside the handle's letters
    # is preserved — the whole ordered sequence must be present for the separator-flexible rule.
    assert "a normal coder reviews" in out and "the ninja stays" in out


def test_scrub_redacts_machine_and_namespace_hostnames(monkeypatch):
    # #P9-PII-1: the production node's hostname and internal *.local hosts are operator/infra PII
    # that no email/username/handle rule covered. The machine hostname is redacted bare + .local;
    # an ASSAY_SCRUB_HOSTS namespace host has its .local form redacted while the bare project token
    # (which appears in legit paths/repo refs) is preserved, and unrelated "*.local" is untouched.
    monkeypatch.setenv("ASSAY_SCRUB_HOSTS", "hc-proj")
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_host")
    # force a deterministic machine hostname regardless of the test host
    monkeypatch.setattr(cap.socket, "gethostname", lambda: "buildbox-7")
    monkeypatch.setattr(cap.platform, "node", lambda: "buildbox-7")
    cap._HOSTNAME_RES = cap._hostname_patterns()
    out = cap._scrub(
        "ran on buildbox-7.local (bare buildbox-7); ns https://hc-proj.local/prov#; "
        "repo hc-proj/app and settings.local.json"
    )
    assert "buildbox-7" not in out  # machine hostname redacted (bare + .local)
    assert "hc-proj.local" not in out  # namespace host .local form redacted
    assert "hc-proj/app" in out  # bare project token preserved (not over-redacted)
    assert "settings.local.json" in out  # unrelated *.local untouched (no blanket rule)


def test_scrub_redacts_private_ips_keeps_loopback_and_public():
    # #P10-PII-1: captured ifconfig/route/lsof output leaks the operator's LAN subnet/gateway/host
    # IP (RFC1918). Redact 10/8, 172.16/12, 192.168/16 — including a form glued to a JSON-\n — while
    # KEEPING loopback (127.x), 0.0.0.0, and public IPs (remote API endpoints, not operator PII).
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_ip")
    # include a sentence-final form "192.168.50.134." — the old (?![\d.]) lookahead refused the
    # trailing period and left the operator's real IP in cleartext (#P10-PII-1 confirm-concern).
    out = cap._scrub(
        "gw 192.168.50.1 host 192.168.50.134 ten 10.0.0.9 priv 172.16.5.4 "
        "loop 127.0.0.1 any 0.0.0.0 pub 160.79.104.10 glued:\\n192.168.1.50 "
        "sentence addr 192.168.50.134. Next sentence."
    )
    for priv in ("192.168.50.1", "192.168.50.134", "10.0.0.9", "172.16.5.4", "192.168.1.50"):
        assert priv not in out, f"private IP {priv} leaked"
    assert "127.0.0.1" in out and "0.0.0.0" in out and "160.79.104.10" in out  # kept


def test_scrub_hostname_does_not_over_redact_as_substring(monkeypatch):
    # #P10-PII-2: the machine-hostname rule has a leading \b so a short/common hostname does not
    # match as a substring of legitimate content (e.g. host "host" must NOT redact "localhost").
    monkeypatch.delenv("ASSAY_SCRUB_HOSTS", raising=False)
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_hostsub")
    monkeypatch.setattr(cap.socket, "gethostname", lambda: "host")
    monkeypatch.setattr(cap.platform, "node", lambda: "host")
    cap._HOSTNAME_RES = cap._hostname_patterns()
    out = cap._scrub("connect to localhost; the localhostname var; rehosting the service")
    # leading \b prevents the SUBSTRING matches that were the defect: 'host' must not fire inside
    # 'localhost', 'localhostname', or 'rehosting'.
    # "to localhost;" tests the EXACT token in context — "localhost" alone would spuriously
    # pass via the substring "localhostname" even when localhost is redacted to "local[REDACTED]".
    assert "to localhost;" in out and "localhostname" in out and "rehosting" in out, (
        "over-redacted 'host' as a substring (#P10-PII-2)"
    )


def test_scrub_redacts_ipv6_ula_and_link_local():
    # #B-11-1: ifconfig output leaks the operator's internal IPv6 topology. ULA addresses
    # (fd00::/8) uniquely identify the operator's private LAN; link-local (fe80::/10) expose
    # interface-specific context. Loopback (::1) is NOT operator-identifying and is kept.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_ipv6")
    out = cap._scrub(
        "inet6 fd0f:a420:ea11:4652:c9a:5e04:db1f:3adc prefixlen 64 "
        "inet6 fe80::a61a:dbfb:8d96:e4fe%utun0 prefixlen 64 "
        "loopback ::1 remains safe "
        "public 2001:db8::1 also safe"
    )
    assert "fd0f:a420:ea11:4652" not in out, "ULA address leaked"
    assert "fe80::a61a:dbfb" not in out, "link-local address leaked"
    assert "::1" in out, "loopback IPv6 should not be redacted"
    assert "2001:db8::1" in out, "public IPv6 should not be redacted"
    assert "[REDACTED]" in out, "at least one redaction should have occurred"


def test_scrub_redacts_mac_addresses():
    # #B-11-2: ifconfig 'ether' lines expose hardware-level operator identity (persistent
    # on macOS wired/primary interface). Six colon-separated 2-hex-digit groups.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_mac")
    out = cap._scrub(
        "ether b2:35:c2:4c:12:2f flags=8863 ether AA:BB:CC:DD:EE:FF mtu 1500 loop 127.0.0.1 ok"
    )
    assert "b2:35:c2:4c:12:2f" not in out, "lowercase MAC leaked"
    assert "AA:BB:CC:DD:EE:FF" not in out, "uppercase MAC leaked"
    assert "127.0.0.1" in out, "loopback IPv4 should be kept"
    assert "[REDACTED]" in out


def test_precommit_hook_wires_namespace_host_into_capture():
    # #P9-PII-1 confirm-concern: the namespace host (hc-grc.local) only redacts when ASSAY_SCRUB_HOSTS
    # names it; the machine hostname auto-derives but this does not. The pre-commit hook must set
    # ASSAY_SCRUB_HOSTS before running capture, else every commit re-introduces hc-grc.local.
    hook = (_ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8")
    assert "ASSAY_SCRUB_HOSTS" in hook, "pre-commit hook does not wire the namespace host scrub"
    # it must be exported BEFORE the capture invocation
    pre = hook.split("capture_transcripts.py")[0]
    assert "ASSAY_SCRUB_HOSTS" in pre, "ASSAY_SCRUB_HOSTS set after capture (too late)"


def test_example_uses_no_hardcoded_hmac_secret():
    # #F-048: the example must not carry a shippable, publicly-known HMAC secret a user could copy
    # into production. It derives a fresh random secret per run instead.
    src = (_ROOT / "examples" / "minimal_study.py").read_text(encoding="utf-8")
    assert b"example-study-secret-key".decode() not in src  # the stale weak literal is gone
    assert "os.urandom(32)" in src  # the fresh-per-run secret is in place


def test_scrub_redacts_password_env_vars():
    # #B-12-1: PGPASSWORD, DATABASE_PASSWORD, DB_PASSWORD, DB_PASS, REDIS_PASSWORD and similar
    # credential env vars appear in `env`/`printenv` output and in psycopg error messages captured
    # in agent transcripts. The _TOKEN/_KEY/_SECRET rules required an 8-char minimum and did not
    # cover _PASSWORD/_PASS variants — leaving short or differently-suffixed passwords in cleartext.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_pass")
    # JSON value form (captured from env dump with JSON encoding)
    out_json = cap._scrub('{"PGPASSWORD": "s3cr3t", "DB_PASSWORD": "hunter2", "DB_PASS": "pw"}')
    assert "s3cr3t" not in out_json, "PGPASSWORD value leaked in JSON form"
    assert "hunter2" not in out_json, "DB_PASSWORD value leaked in JSON form"
    assert "pw" not in out_json, "DB_PASS value leaked in JSON form"
    # env/export form: NAME=value (no quotes)
    out_env = cap._scrub("PGPASSWORD=s3cr3t DB_PASSWORD=hunter2 REDIS_PASSWORD=abc123 DB_PASS=pw")
    assert "s3cr3t" not in out_env, "PGPASSWORD value leaked in env form"
    assert "hunter2" not in out_env, "DB_PASSWORD value leaked in env form"
    assert "abc123" not in out_env, "REDIS_PASSWORD value leaked in env form"
    assert "pw" not in out_env, "DB_PASS value leaked in env form"
    # negative: BYPASS and COMPASS must not be over-redacted by the _PASS\b boundary rule
    out_safe = cap._scrub("BYPASS=foo COMPASS=bar")
    assert "BYPASS=foo" in out_safe, "BYPASS over-redacted"
    assert "COMPASS=bar" in out_safe, "COMPASS over-redacted"


def test_scrub_mac_pattern_does_not_redact_timestamps():
    # #B-12-2: HH:MM:SS timestamps (e.g. "12:34:56") are 3 colon-separated 2-hex-digit groups —
    # a false-positive substring of the 6-group MAC pattern. The lookbehind/lookahead guards in
    # the MAC pattern must reject them so log/trace output is not mangled.
    cap = _load("scripts/capture_transcripts.py", "capture_transcripts_mac_neg")
    out = cap._scrub(
        "timestamp 12:34:56 elapsed 00:01:23 at 23:59:59 ether b2:35:c2:4c:12:2f real-mac"
    )
    assert "12:34:56" in out, "HH:MM:SS timestamp incorrectly redacted as MAC"
    assert "00:01:23" in out, "elapsed time incorrectly redacted as MAC"
    assert "23:59:59" in out, "HH:MM:SS timestamp incorrectly redacted as MAC"
    assert "b2:35:c2:4c:12:2f" not in out, "real MAC address should be redacted"
