# ADR-0003 — Local-first, data-sovereign; self-hosted observability

**Status:** Accepted (2026-06-15)

## Context

The analyzed data may be sensitive, licensed, or otherwise constrained. Reproducibility
also requires that traces and experiment records be retained. SaaS observability (managed
tracing) ships analyzed content off-box and, at corpus scale with long retention, is also
expensive.

## Decision

All computation, storage, tracing, and experiment tracking run **on-box**. Observability is
**self-hosted** (OpenTelemetry → a local collector) plus a local experiment-tracking store.
The high-stakes reasoning tier uses a fixed-cost subscription path (no metered API); the
bulk tier uses a local model. No data, embeddings, traces, or results leave the machine.

## Consequences

- SaaS tracing/observability is disqualified by the data-sovereignty constraint,
  independent of cost.
- The platform is runnable fully offline; nothing depends on a remote service to advance.
- The operator owns retention and the full reproducibility record locally.
