# Current milestone

Milestone 4 — Identity (steps 17–21): complete.

Implemented: persistent `bar_uuid` object custom properties; startup management of
all Blender data objects; strict canonical UUID validation; live UUID resolution;
known-duplicate identity assignment; fail-closed collision handling; structured
missing-object, malformed-identity, read-only and write-failure errors. IDs survive
renames and .blend save/load. Removing data makes IDs unresolved; name reuse does
not revive identity. Resolution retains no object references across file loads.
The Blender server advertises `object_identity` support through discovery.
Runtime package version: 0.4.0; public API version: 1.0.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 35 unit tests, 15
integration tests, and 15 conformance checks reusing the integration suite, plus
direct headless identity/API smoke checks. Real Blender tests cover data-block and
operator duplication, collision/malformed-ID rejection, deletion, name reuse,
save/load with the existing resolver, and persistence across two Blender processes
with different sessions. Mutation and file-load fixtures verify revision hooks.
All prior lifecycle, API and state checks pass. Commands are in README.md.

Limits: identity helpers are internal; seven public tools remain discovery only.
Missing IDs are initialized as part of the revision-zero baseline before the
startup handshake. Later writes must run inside revision-guarded mutation handlers.
Unknown collisions require explicit repair; linked-library management and automatic
tracking of external edits are not implemented. Resolution scans all current data.
No scene observation tools, recovery snapshots, transactions, AI or adapters yet.
See IDENTITY.md for the service contract and error behavior.

Next: Milestone 5 — Scene Observability (steps 22–24): scene summary, filtered
object listing and pagination.
