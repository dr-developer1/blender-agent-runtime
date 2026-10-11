# Core mesh control

Milestone 8 adds five API 1.0 mutations. All return `result.object_id` and report
only the target UUID in `modified_ids`. Objects and UUIDs remain intact. The
server has 23 tools; boolean registration requires a dependency graph provider.
The existing explicit object-control backend enables mesh control too.

| Tool | Required arguments | Optional arguments |
| --- | --- | --- |
| `mesh.extrude` | `selection_handle`, `offset` (three numbers) | `unit` |
| `mesh.inset` | `selection_handle`, `thickness` | `unit` |
| `mesh.bevel` | `selection_handle`, `width` | `unit`, `segments` (1–16, default 1) |
| `mesh.boolean` | `object_id`, `operand_id`, `operation` | — |
| `mesh.cleanup` | `object_id` | `merge_distance`, `unit`, `recalculate_normals` (default true) |

Lengths use m/cm/mm (default m), normalized to meters in **object-local mesh
coordinates**. Object scale therefore affects world-space results. A handle's
query space governs which elements match; edit distances and extrusion vectors
are always local. Extrusion requires a nonzero offset; widths, thicknesses and
merge distances must be positive, bounded finite numbers.

Extrude and inset consume nonempty FACE handles; bevel consumes nonempty EDGE
handles. Extrude moves a connected region's new cap by the specified vector and
replaces its original cap. Inset creates a region border with even offsets and
interpolated data. Bevel uses an offset width, a 0.5 profile, and overlap clamping.
Regions may contain disconnected components. There are no raw public element
indices or UI selection dependencies.

Boolean supports UNION, DIFFERENCE and INTERSECT using Blender's EXACT solver.
It evaluates a temporary copy with a boolean modifier, then publishes the baked
base mesh in the target's local coordinates. The operand remains intact. Inputs
must be distinct and have nonsingular world transforms. Closed, manifold solids
are the supported correctness case; open or self-intersecting inputs carry no
solid-result guarantee. Empty intersections are valid results.

Cleanup optionally welds vertices within `merge_distance`, then recalculates face
normals when requested. Omitting merge distance performs only normal recalculation.
It does not repair arbitrary self-intersections, remove every degenerate face or
promise outward orientation for open surfaces. Omitting merging while disabling
normal recalculation is rejected.

All tools require Object mode, active-scene membership and editable mesh objects
and data, without shape keys, modifiers or vertex groups. The current conservative
contract also applies these checks to boolean operands. Mesh edits preserve
object transforms, parenting, active object and selection. BMesh copies preserve
supported mesh layers and material slots; new topology follows Blender's native
interpolation rules. No new UV unwrapping or material generation is provided.

Edits run on a detached BMesh and copy of the target datablock; booleans use a
temporary object removed even on failure. Publication replaces only the target's
mesh data, giving copy-on-write behavior for linked duplicates. Existing mesh
references held by other objects stay unchanged; unused original mesh datablocks
are retained. Input and output meshes are limited by the advertised 200,000
mesh-element budget (vertices + edges + faces + loops) and finite coordinates.
Output rejection discards the staged mesh before publication.

Handle resolution happens under the dispatcher's serialization lock **before**
the mutation revision advances. It validates session-local ownership, revision,
geometry and transform fingerprints. Preparation does not edit Blender. Every
schema-valid mutation attempt consumes one revision, including failed handle
preparation or object preflight. Successful and rejected attempts expire existing
handles; query again before the next edit. Schema/state rejection consumes none.

Errors reuse the selection and object contracts, adding `EMPTY_SELECTION`. These
operations advertise transaction safety when the recovery backend is enabled.
Staging protects geometry from preparation, operation and output-budget failures;
explicit full-file checkpoint rollback is described in [RECOVERY.md](RECOVERY.md).
Evaluated topology editing, per-face normal extrusion, individual inset, vertex
bevel, modifier stacks and comprehensive repair remain outside this milestone.

Implementation references: [BMesh operators](https://docs.blender.org/api/current/bmesh.ops.html),
[mesh creation from evaluated objects](https://docs.blender.org/api/current/bpy.types.BlendDataMeshes.html),
and [boolean modifiers](https://docs.blender.org/api/current/bpy.types.BooleanModifier.html).
