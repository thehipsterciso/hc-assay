# ADR-0003 — Local-first, data-sovereign; self-hosted observability

**Status:** Accepted (2026-06-15)

## Context

The analyzed data may be sensitive, licensed, or otherwise constrained. Reproducibility
also requires that traces and experiment records be retained. SaaS observability (managed
tracing) ships analyzed content off-box and, at corpus scale with long retention, is also
expensive.

## Decision

All engine computation, storage, tracing, experiment tracking, and the **bulk** reasoning tier
run **on-box**. Observability is **self-hosted** (OpenTelemetry → a local collector) plus a
local experiment-tracking store. The bulk reasoning tier uses a local model; no data,
embeddings, traces, or results from these paths leave the machine.

Two distinct concerns must not be conflated:

- **Billing model:** the optional **high-stakes** reasoning tier uses a fixed-cost subscription
  path (the `claude` CLI / Agent SDK with an OAuth token) — *no metered API*. `scrubbed_env()`
  strips metered credentials, off-box redirects (`ANTHROPIC_BASE_URL`), and proxies.
- **Data residency:** "no metered API" is **not** the same as "on-box". The high-stakes tier
  sends prompt content (derived from the data) to a frontier model hosted by Anthropic over the
  network — it is **off-box** by construction (there is no local frontier model). A study whose
  data must never leave the box must use only the bulk/local tier or `UnconfiguredReasoningSeam`.

## Consequences

- SaaS tracing/observability is disqualified by the data-sovereignty constraint,
  independent of cost.
- The engine, storage, observability, and bulk reasoning are runnable fully offline; only the
  optional high-stakes tier depends on a remote service (and is off-box) to advance.
- The operator owns retention and the full reproducibility record locally.
