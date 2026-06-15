# ADR-0002 — Engine + adapter blueprint; one repo per study

**Status:** Accepted (2026-06-15)

## Context

This is a reusable blueprint, not a single study. A prior internal platform tangled
dataset specifics into its core, which made it un-clonable and drifted its governing
documents out of sync. We want to clone onto a new dataset by writing an adapter, not by
refactoring the core.

## Decision

1. Split the system into a dataset-agnostic **engine** and per-dataset **adapters**. The
   engine never imports dataset specifics; adapters implement interfaces the engine calls
   and depend only on the engine.
2. The engine is lifted from the prior internal platform's hardened infrastructure
   (governance, reasoning seam, observability, persistence) — that work is goal-agnostic
   and reused; its dataset-specific methodology is **not** carried over.
3. Each concrete study lives in **its own repository** built on the engine, to keep every
   study's pre-registration independent and uncontaminated.

## Consequences

- Onboarding a dataset = implement adapter + study definition + run.
- The engine ↔ adapter boundary is the stable contract and must be guarded in review.
- The engine can be versioned and shared across studies; breaking changes are managed like
  any library release.
