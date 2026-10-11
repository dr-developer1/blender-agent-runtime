# Current milestone

Milestone 3 — State Model (steps 14–16): complete.

Implemented: fresh runtime session UUIDs; monotonic revision counters; strict
state fields on every public request; session and stale-state rejection before
execution; revision fields on success/error responses; authenticated state
bootstrap; automatic controller state tracking with explicit observation
precondition overrides; response timeline validation; serialized mutation hooks.
Read-only discovery leaves revisions unchanged. Declared mutation attempts advance
before execution, including failures; scene restoration never rewinds the counter.
Runtime package version: 0.3.0; public API version: 1.0.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 25 unit tests, 13
integration tests, 13 conformance checks reusing the integration suite, and an
isolated headless API smoke check. Integration includes a real Blender create/
restore fixture. Checks cover stale and wrong-session rejection, restart identity,
concurrent edits, failures, monotonic restoration and corrupt controller responses,
plus all prior lifecycle and discovery regressions. Commands are in README.md.

Limits: seven production tools remain read-only discovery. Mutation and rollback
hooks are exercised through private test fixtures, not public modeling tools.
External bpy edits are not automatically tracked. Argument schemas still support
only the discovery object/string subset. No recovery snapshots, object IDs,
transactions, AI integration or adapters have been added.

Next: Milestone 4 — Identity (steps 17–21): persistent object UUIDs, resolution,
and save/load, duplication and deletion tests.
