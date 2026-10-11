# Current milestone

Milestone 8 — Core Mesh Control (steps 41–45): complete.

Implemented `mesh.extrude`, `mesh.inset`, `mesh.bevel`, `mesh.boolean` and
`mesh.cleanup`. The server advertises 23 public tools. Runtime package version:
0.8.0; public API version: 1.0.

Extrude/inset use FACE handles; bevel uses EDGE handles. Read-only preparation
resolves handles at the current revision under the dispatcher lock, before the
mutation advance. Every schema-valid attempt consumes one revision, including
preparation rejection; schema/state failures consume none. Success reports the
target UUID in `modified_ids`; edits keep objects and UUIDs intact.

BMesh edits stage independent mesh data, check output budgets and publish only the
target's new data. Linked duplicates retain the original mesh. Extrusion uses a
local displacement vector; inset uses an even region border; bevel uses bounded
segments and overlap clamping. Lengths use m/cm/mm normalized in local mesh space,
independent of handle query space. Boolean bakes an EXACT modifier from a temporary
copy and retains its operand; temporary objects are cleaned on success or failure.
Cleanup optionally welds nearby vertices and recalculates normals.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 67 unit tests and 24
real-Blender integration cases plus the same 24 conformance checks passed. Fixtures verify all five operations, signed volumes and manifold edges,
UV/material preservation, linked-copy isolation, units and local scaled offsets,
boolean volumes and empty intersections, welding/normals, handle resolution and
expiry, stale revisions, unsupported states, Edit mode and output-budget rejection
without staged mesh leaks. Exact commands are in README.md and contracts in
MESH_CONTROL.md.

Limits: Object mode and editable active-scene meshes only; no shape keys, modifiers
or vertex groups. Boolean operands follow the same restrictions. Query space
selects elements but edit units/vectors remain object-local. No evaluated topology
editing, individual inset, vertex bevel, comprehensive geometry repair or general
rollback. Original orphan mesh datablocks are retained. Publication isolates linked
copies; mesh layers follow Blender's native interpolation. External changes are
not automatically revision-tracked. Change arrays report the directly edited
object, not a full scene diff. Tools are not transaction-safe.

Next: Milestone 9 — Validation (steps 46–49): geometry, evaluated dimensions,
assembly and asset validators, with structured findings and conformance tests.
