# Conformance

Milestone 1 reuses the integration acceptance tests against real isolated Blender
processes. Run `python3 -m unittest discover -s conformance -v` from the repo root.
No AI model is involved. Future capability conformance will live in this directory.

Checks cover persistent process identity, contiguous execution sequence under
concurrent controller callers, execution on the Blender main thread, structured
command rejection and subsequent recovery, clean exit, forced process death,
missing executable, and independent headless script success/failure propagation.
Transport unit tests check framing, non-finite/malformed JSON, bounds and disconnects.


Milestone 2 adds real-process API discovery, descriptor lookup, version rejection,
invalid-argument rejection, unknown-tool handling, subsequent-call recovery and
captured JSON logs. Unit tests independently check strict schemas, version contracts,
response validation, registry consistency, descriptor isolation, non-JSON outputs,
internal-error redaction and omission of arguments/results from logs.

Run `python3 -m controller.headless tests/blender/api_smoke.py` for an isolated
Blender check that all advertised read-only tools return valid success envelopes and leave scene
objects unchanged. This supplements the persistent-process integration suite.

Milestone 3 covers session bootstrap, new sessions after process restart, stale
revision and old-session rejection, malformed state fields and recovery. A real
Blender scene fixture creates and removes an object while verifying that restoring
contents advances the timeline. Unit tests additionally cover conservative revision
advancement after failure, concurrent stale edits, read stability, and client
rejection of corrupt state responses. The state fixture can also run directly with
`python3 -m controller.headless tests/blender/state_smoke.py`.

Milestone 4 verifies startup identity capability reporting, UUID assignment,
rename-safe resolution, Blender data-block and operator duplication, collision and
malformed-ID detection, deletion and name reuse, and save/load with live-reference
reacquisition. A second check writes a .blend file in one isolated process and
resolves the same UUIDs in another process with a different session. Unit tests
also cover read-only objects, write failures, generation collisions, and rejection
of unmanaged or removed objects. Run the lifecycle fixture directly with
`python3 -m controller.headless tests/blender/identity_smoke.py`.

Milestone 5 checks scene summary and paginated UUID listing over persistent IPC.
A real Blender fixture adds 253 objects and verifies type, collection, visibility,
name, tag and world-origin region filters, bounded complete pagination, exclusion
visibility, collision-free resolution, and read-only state. It rejects tampered,
filter-mismatched, edited-scene and old-revision cursors. Orphans and other-scene
objects remain excluded. Unit checks also cover empty scenes, nested invalid
arguments, schema rejection, response size limits and subsequent-call recovery.
Run `python3 -m controller.headless tests/blender/scene_smoke.py` directly.

Targeted inspection tests compare original mesh counts with array/mirror/solidify
results and verify evaluated world bounds under parenting, rotation and negative
scale. Geometry-free objects have nullable dimensions. Hierarchy checks paginate
parent UUID edges and reject cross-endpoint and reparented cursors. Inspection
checks UUID order, duplicate/unknown/malformed IDs, excluded evaluation, base-mesh
preservation and absence of temporary mesh data-block leaks. Run
`python3 -m controller.headless tests/blender/geometry_smoke.py` directly.

Milestone 6 checks semantic mesh addressing over persistent IPC and isolated Blender.
Deterministic fixtures verify four top perimeter edges, upward faces, height ranges,
sharp dihedral angles, open boundaries, disconnected components and non-manifold
branches. World/local targeting is verified under translation, rotation and negative
scale. Modifiers leave base queries and Blender UI selection unchanged. Handles
reject vertex/topology/transform edits, removed/deleted objects, Edit mode, unknown
sessions and runtime revision changes. Unit tests also verify selector intersection,
ties, degenerate/empty geometry, schemas, handle eviction and budgets. Run
`python3 -m controller.headless tests/blender/selection_smoke.py` directly.

Milestone 7 exercises all five object-control tools over persistent IPC and an
isolated Blender fixture. Checks cover primitive dimensions, outward winding,
unit conversion, absolute XYZ transforms, omitted quaternion/delta components,
independent/shared mesh copies and fresh UUIDs, rename/deletion/name reuse,
parenting cycles, local/world pose preservation, direct-child handling on deletion,
singular parents, sheared poses, constraints, Edit mode, schema/precondition versus
handler revision behavior, change arrays and selection-handle expiry. Unit tests
verify closed primitive edge incidence and opposite winding, bounded schemas,
mutation envelopes and explicit backend availability. Run
`python3 -m controller.headless tests/blender/object_smoke.py` directly.


Milestone 8 adds a mesh-control IPC case and isolated `mesh_smoke.py` fixture,
reused by conformance. They verify all five tools, signed solid volumes and manifold
edges, UV/material preservation, copy-on-write linked meshes, unit conversion,
local offsets under scaling, exact boolean operations and empty intersections,
cleanup welding/normals, handle preparation and invalidation, stale preconditions,
unsupported states, Edit mode, output budgets and staged-data/temporary-object
cleanup. Run the fixture with `python3 -m controller.headless tests/blender/mesh_smoke.py`.

Milestone 9 adds validation over IPC and a `validation_smoke.py` fixture, reused
by conformance. Checks cover all four tools, failed findings versus execution
errors, topology defects, empty/nonfinite geometry, open-surface policy, negative
and singular transforms, modifier/rotation-aware dimensions, assembly contact,
support, ground, overlap, clearance, symmetry, count and disconnected boxes,
asset composition and material assignment. Validation preserves mesh datablocks,
UI selections, object identity, revisions and valid selection handles. Duplicate
UUIDs, invalid arguments, Edit mode, missing objects, non-meshes and exhausted
budgets reject without writes. Pure unit tests cover numeric algorithms and
strict bounded schemas. Run
`python3 -m controller.headless tests/blender/validation_smoke.py` directly.
