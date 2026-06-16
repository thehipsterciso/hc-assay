# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for a vulnerability.

Use GitHub's private vulnerability reporting ("Report a vulnerability" under the repository's
**Security** tab), or open a regular issue asking for a private channel without disclosing
details.

Please include: what the issue is, how to reproduce it, and the impact you foresee. We aim to
acknowledge a report within a few days.

## Scope notes

hc-assay is local-first and data-sovereign by design (ADR-0003): the engine routes execution
through a loopback-only / on-box path and scrubs metered API credentials before any subprocess
call. Findings that weaken these guarantees — data leaving the box, a metered credential
reaching a subprocess, a firewall/pre-registration bypass, or a forgeable provenance trail — are
in scope and especially welcome.

The engine's honest-scope limits are documented (e.g. in-process trust for the unkeyed
provenance chain, signature-level rather than frame-isolation firewalls); a report that defeats a
guarantee *within* its stated scope is a valid finding.
