# ADR-0007 — Engine-native content-addressed data versioning (external VCS optional)

**Status:** Accepted (2026-06-16)

## Context

Reproducibility requires that every finding cite the exact bytes it was computed from — the
inputs and artifacts must be versioned and re-fetchable by id (METHODOLOGY.md §7). The prior
platform delegated this to an external data-version-control tool driven through a separate
process/integration. That couples the engine to an external binary and its remote/config
model, adds a heavyweight dependency to a capability the engine needs from its first run, and
makes the determinism guarantee depend on tooling outside the engine's control.

## Decision

The engine ships a **dependency-free, content-addressed local store** as the default
`DataVersioner`:

- an artifact is hashed (SHA-256, streamed in chunks) and copied under
  `<store>/<first-2-hex>/<full-hash>`; the hash is the version id;
- the same bytes always produce the same id (content-addressed), so versioning is
  deterministic and storing a duplicate is a no-op;
- publication is **atomic** — content is written to a per-writer-unique temp file in the
  destination directory and `os.replace`-d into place, so a reader never observes a partial
  artifact and concurrent writers of the same digest cannot corrupt each other;
- it is fully **on-box** (ADR-0003) and requires no external service or network.

`DataVersioner` is a Protocol (`put` → version id, `fingerprint` → hash). A study that
genuinely needs an external VCS (e.g. for a shared team remote) implements that Protocol in
its **adapter** and supplies it — the engine contract is unchanged. The engine itself never
depends on an external versioning tool.

Note: *retrieval by id* is store-implementation-specific and intentionally **not** part of
the `DataVersioner` Protocol. The default `LocalDataVersioner` exposes `path_for(id)` to
resolve a stored artifact locally; an adapter over a different store provides its own
retrieval mechanism. Code that must fetch artifacts by id therefore depends on the concrete
store, not the Protocol — by design, since retrieval semantics differ across backends.

## Consequences

- Determinism and provenance work out of the box, offline, with no extra dependency — the
  reproducibility guarantee rests on engine code, not an external binary's configuration.
- The default store is local-only by design; sharing artifacts across machines is an explicit
  adapter responsibility, not a silent default (consistent with data sovereignty).
- The store grows monotonically (content-addressed; no garbage collection in the engine);
  pruning, if needed, is an operator/adapter concern. This is an accepted trade-off for a
  simple, race-safe, deterministic default.
- Symlinks and special files are stored by their resolved content; the store versions file
  *bytes*, not filesystem metadata semantics.
