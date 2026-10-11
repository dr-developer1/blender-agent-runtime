# Current milestone

Milestone 7 — Basic Object Control (steps 36–40): complete.

Implemented `object.create_primitive`, `object.transform`, `object.duplicate`,
`object.delete`, and `object.set_parent`, using Blender's data API on the main
thread. The server advertises eighteen public tools and `scene_mutation: true`.
Runtime package version: 0.7.0; public API version: 1.0.

Primitives cover cube, plane, cylinder and cone with finite bounded arguments,
m/cm/mm lengths and XYZ Euler degrees. Transforms set absolute parent-local
components and bake delta transforms. Copies receive fresh UUIDs, with independent
object data by default and optional shared data. Parenting detects cycles and
preserves world pose by default; clearing parents and deleting parents preserve
representable child world poses. Singular parents, shear, constraints, animation,
rigid-body state and non-object parenting are rejected where necessary for precise
transform behavior. Object control requires Object mode and leaves UI selection
and active-object state alone except when deleting the active/selected object.

Every mutation attempt consumes one revision after schema/state checks; rejected
handler preflight also advances, following the existing conservative policy.
Success envelopes report created/modified/deleted UUIDs. Revision changes expire
selection handles. State preconditions reject stale edits before execution.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 64 unit tests, 22
real-Blender integration cases, the same 22 conformance checks, and all eight direct
headless process/API/state/identity/scene/geometry/selection/object smoke fixtures.
Fixtures cover primitive dimensions and outward topology, unit conversion,
transform preservation, copying and shared data, identity after rename/delete,
parenting cycles, world/local pose behavior, child preservation, singular/sheared
transforms, constraints, Edit mode, state rejection and handle invalidation.
All checks passed. Commands are in README.md; exact contracts in OBJECT_CONTROL.md.

Limits: background runtime; basic primitive set only; no UVs/material assignment,
mesh edits, recovery or transactions yet. Transforms use parent-local components,
not evaluated world dimensions. Copies share materials and nested references;
delete removes the object globally and retains orphan datablocks. Change arrays
report direct object changes, not all indirect dependencies or a full scene diff.
Externally edited state is not automatically revision-tracked. See
OBJECT_CONTROL.md for supported object states and rejection semantics.

Next: Milestone 8 — Core Mesh Control (steps 41–45): extrude, inset, bevel,
boolean and cleanup, consuming semantic selection handles where applicable, with
revision/identity/change tracking and integration/conformance tests.
