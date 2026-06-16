# ADR-0006 — Heavy backends are optional: lazy imports + install extras

**Status:** Accepted (2026-06-16)

## Context

The engine's infrastructure seams (reasoning, observability, persistence) are implemented
over heavy third-party backends — a local model runtime and a frontier-model SDK, an
OpenTelemetry/collector stack and an experiment-tracking store, a Postgres-backed
checkpointer and a vector store. Most of these require external services running on the box
and large, version-sensitive dependency trees.

A blueprint cloned into 100+ studies must nonetheless be trivial to install, import, and
unit-test in CI and on a fresh machine — without standing up Postgres, a collector, a model
runtime, or pulling hundreds of megabytes of optional wheels. At the same time, a seam used
without its backend must fail clearly, never silently.

## Decision

1. **The core engine has zero hard runtime dependencies.** Every heavy backend is declared
   under a named install extra (`reasoning`, `observability`, `persistence`) in
   `pyproject.toml`, never in `dependencies`.
2. **Backends are imported lazily**, inside the function that uses them — never at module
   top level. Importing any engine module, and running the full unit-test suite, succeeds
   with no extra installed.
3. **Absence fails loud at point of use.** When a seam method needs a missing backend it
   raises a clear error naming the required extra (e.g. *"requires the 'persistence' extra
   …"*) — it never silently no-ops or returns a degraded result. The one deliberate
   exception is **tracing**, which must never be load-bearing (ADR-0003) and so degrades to a
   silent no-op when its backend or collector is absent.
4. **The security/correctness logic that wraps a backend is pure and lives outside the lazy
   import**, so it is unit-tested offline: credential scrubbing/redaction, loopback
   enforcement, retry budgets, the JSON walker, content hashing, connection-string
   resolution.
5. The type-checker is told these optional modules are untyped (a `mypy` override with
   `ignore_missing_imports`), matching their runtime optionality.

## Consequences

- `pip install .` yields an importable, testable engine; `pip install '.[reasoning,observability,persistence]'`
  (plus the on-box services) yields a running platform.
- CI exercises every hardened invariant without external services, because the load-bearing
  logic is separated from the I/O it guards.
- Each seam carries a small amount of lazy-import boilerplate and a fail-loud branch; this is
  the explicit cost of keeping the core dependency-free, and is preferred over conditional
  top-level imports that would make import success depend on the environment.
- A test that asserts the *absent-backend* path must skip when the extra happens to be
  installed, so an extras-installed CI lane stays green.
