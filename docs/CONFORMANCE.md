# Conformance

Milestone 14 supplies a model-independent acceptance gate for steps 70–76.
Run from the repository root:

```bash
python3 -m unittest discover -s tests/unit -v
python3 -m conformance --output artifacts/conformance.json
```

The report command runs the inherited real-Blender integration fixtures plus the
dedicated conformance cases. It records test IDs, pass/fail/error/skip outcomes,
elapsed times, failure tracebacks, environment and performance measurements. It
returns nonzero if any check fails, is skipped, or no tests run. Plain unittest
discovery remains supported, but unittest can return success when Blender checks
are skipped. Set `BLENDER_EXECUTABLE` to select a different Blender executable.

| Canonical step | Acceptance evidence |
| --- | --- |
| 70: operation correctness | Existing object/mesh/material fixtures, analytic dimensions, signed volume, manifold edges, real shader links and copy isolation |
| 71: inspection accuracy | Existing evaluated modifier/world-bound fixtures plus large-scene UUID/name/world-origin ground truth |
| 72: selection accuracy | Existing exact-index/coordinate fixtures for caps, edges, normals, connected components, transform spaces and handle expiry |
| 73: rollback reliability | Existing full-file failure/lifecycle fixtures plus five successive transform/extrude/duplicate/restore cycles on 250 objects |
| 74: API compatibility | Frozen API 1.0 descriptors for 36 server tools, unsupported-version rejection and subsequent recovery |
| 75: performance | 25 warm public IPC summaries; timed large-scene summary, pagination, hierarchy, inspection and repeated rollback |
| 76: large scenes | 2,001 objects, complete UUID-ordered pages, 1,000 exact tag matches, 100 targeted inspections, bounded recovery rejections |

`conformance/api_1_0.json` freezes tool versions, input/output schemas, supports,
side effects and transaction safety. It deliberately excludes editorial descriptions
and the runtime package version. A contract change must be reviewed with its API
compatibility implications before updating this file; the suite never rewrites it.
This milestone pins exact descriptors, so additive tool/schema changes also require
an explicit baseline review. This verifies the current API against the saved
contract; it does not claim a matrix of historical runtime binaries.

The large-scene fixture uses 2,000 empties and one cube: it tests inspection scale,
not dense-mesh throughput. Every timed group has a fixed 30-second regression
budget, and all 25 warm IPC calls together have a 10-second budget. Startup is
excluded from the IPC sample. The fixture has a 120-second process deadline.
These intentionally broad bounds tolerate machine differences and catch severe
regressions; measured durations are useful evidence, not universal latency promises.

Recovery rejects the 2,001-object fixture with `RECOVERY_LIMIT_EXCEEDED`.
Even after reducing it to 1,000 objects, its serialized snapshot exceeds the
independent response budget and rejects with `RESPONSE_TOO_LARGE`. Both checks
verify that no transaction is left active and subsequent inspection works. Five
rollback cycles run on 250 objects, assert exact restored inspection, stable session,
monotonic revisions, restored counts and deletion of the private checkpoint.
The object cap alone does not guarantee that a snapshot fits all budgets.

Recorded Milestone 14 evidence is in `docs/evidence/conformance_m14.json`.
The coverage remains limited to the supported runtime contract and the recorded
Blender/platform combination; multi-release Blender support and stronger
large-scene scaling are separate work.

Milestone 1 reuses the integration acceptance tests against real isolated Blender
processes. Run `python3 -m unittest discover -s conformance -v` from the repo root.
No AI model is involved. Dedicated capability conformance also lives in this directory.

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


Milestone 10 adds transaction/diff IPC, full-file recovery and forced-death snapshot
cleanup cases, reused by conformance. They verify one active transaction, strict
IDs/state guards, monotonic rollback revisions and stable sessions, UUID re-resolution,
selection-handle expiry, commit persistence, same-count geometry and modifier diffs,
created/deleted/modified reporting, saved shared meshes, UV/material/hierarchy/UI
state, other scenes and orphan data, relative external resource targets, corrupted
checkpoints, unsupported Edit mode and recovery despite collisions/nonfinite/over-budget
current scenes. Unit tests also exercise save/load failures, retained checkpoints,
retry and numeric diff ordering. Run
`python3 -m controller.headless tests/blender/recovery_smoke.py` directly.


Milestone 11 adds observation IPC and an `observation_smoke.py` fixture, reused by
conformance. Checks cover default six-view delivery at 384 × 384 within the 1 MiB
frame, camera consistency, PNG dimensions/content, solid/wire/silhouette pixels,
EEVEE material appearance, repeatability, source render/UI/datablock preservation,
transaction diff and rollback re-resolution, handle/cursor preservation, invalid
arguments, missing/non-mesh/hidden targets, geometry/pixel/PNG budgets and injected
render failures with cleanup. Pure unit tests project AABB corners through every
view across square, portrait and landscape aspect ratios and verify schemas and
revision/error semantics. Run
`python3 -m controller.headless tests/blender/observation_smoke.py --timeout 90`.
