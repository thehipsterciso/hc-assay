# Hardening Pass 11 — IPv6/MAC scrubbing + fix-regression (2 MED)

Branch `harden/pass-11`. Same dimensions as pass 10. Model: Claude Sonnet 4.6.

## 1. Assessment → self-refutation → verification

6 dimension assessors (security, privacy, provenance, reliability, fix-regression, actual-CI)
produced 5 findings: **2 MED, 3 LOW, 0 HIGH**. All 2-agent verified.

## 2. Findings

| ID | Sev | Dimension | Finding |
|----|-----|-----------|---------|
| B-11-1 | MED | privacy | **No IPv6 ULA/link-local scrubbing.** `_SECRET_PATTERNS` covered only RFC1918 IPv4; `ifconfig -a` output captured in transcripts leaks `fd00::/8` (ULA — operator's private LAN) and `fe80::/10` (link-local) IPv6 addresses. Confirmed active leak: `fd0f:a420:ea11:4652:c9a:5e04:db1f:3adc` and `fe80::a61a:dbfb:8d96:e4fe%utun0` in the assessor agent's transcript. |
| B-11-2 | MED | privacy | **No MAC address scrubbing.** `ifconfig` output contains `ether aa:bb:cc:dd:ee:ff` — persistent hardware identity on macOS wired/primary interface. `b2:35:c2:4c:12:2f` found unredacted in same transcript. |
| A-11-2/E-11-1 | LOW | security / fix-reg | `servicefile` is not a real libpq DSN keyword; the comment added in pass-10 claiming it "loads an off-box service definition" was factually incorrect for a DSN context. Dead code with a misleading comment. |
| A-11-3 | LOW | security | `TRACING_HOST` frozen at module import; post-import env change has no security effect (the frozen value is always used for validation). Misconfiguration risk only, no bypass. |
| A-11-4 | LOW | security | Same as A-11-3 for `VECTOR_HOST` in `vectorstore.py`. |

## 3. 0 HIGH for the first time in 4 passes

Dimensions C (provenance), D (reliability), and F (CI) found no new findings. The fix-regression
dimension only surfaced the LOW comment/dead-code issue (A-11-2), confirming the pass-10 changes
were structurally sound. Privacy remains the productive attack surface (three MED finds across
passes 9–11 all in the scrubber).

## 4. Fixes

- **B-11-1** — two regex patterns added to `_SECRET_PATTERNS` in `scripts/capture_transcripts.py`:
  - IPv6 ULA (`fc00::/7` incl. `fd00::/8`) and link-local (`fe80::/10`): `(?<![0-9a-fA-F:])(?:fe80|f[cd][0-9a-fA-F]{2}):[0-9a-fA-F:]{2,}(?:%[a-zA-Z0-9]+)?` with `IGNORECASE`. Zone IDs (`%utun0`, `%lo0`) included in match. Loopback `::1` starts with `:` and is not matched.
  - MAC addresses: `(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}(?![0-9a-fA-F:])` with `IGNORECASE`. 6 two-hex-digit groups; lookbehind/ahead prevent false matches inside IPv6 (which uses 4-digit groups) or longer hex strings.
  - Corpus re-scrubbed: confirmed 0 matches for the leaked addresses in committed transcripts.
- **B-11-2** — covered by the MAC pattern above.
- **A-11-2** — comment corrected: `servicefile` is documented as belt-and-suspenders for a non-existent libpq DSN keyword (the real attack via service file is via the `service=` DSN keyword, already blocked, and via `PGSERVICEFILE` env var, blocked in `_assert_local_libpq_env`).
- **A-11-3/A-11-4** — no code change; documented as note (no production security risk, env set before Python starts in all real deployments).

## 5. Confirmation (2 agents per fix)

Both MEDs (B-11-1, B-11-2) were confirmed TRUE_POSITIVE by both agents independently with
evidence of actual leaked addresses in the committed transcript.

For A-11-2: agent A rated FALSE_POSITIVE (harmless dead code, no impact); agent B rated
TRUE_POSITIVE (dead code with misleading comment). Resolved: fix the comment (done), keep the
`servicefile` keyword guard as belt-and-suspenders. No security regression in either direction.

## 6. Final state

- Gates: `ruff` + `ruff format --check` + `mypy --strict` clean; **543 passed, 4 skipped**.
- Corpus clean: no IPv6 ULA/link-local or MAC addresses remain in committed transcripts.
- Merged after `require_green_ci.sh` confirms green for this HEAD.

## 7. Convergence — not declared

2 MED, 0 HIGH this pass. Privacy scrubber continues to yield new vectors (now 4 passes running:
username → hostname → RFC1918 IPv4 → IPv6 + MAC). Security dimension converging (no HIGH for
the first time in 4 passes). Not declaring global convergence while privacy vectors remain active.
