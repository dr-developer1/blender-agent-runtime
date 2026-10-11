# Semantic mesh addressing — API 1.0

`mesh.query` requires `object_id`, `element_type` (`VERTEX`, `EDGE`, `FACE`),
and 1–16 `selectors`. Optional `space` defaults to `WORLD`; `LOCAL` uses mesh data
coordinates. Selectors combine by intersection. Every selector runs against the
whole mesh, so order does not affect results. Empty matches succeed.

```python
selection = client.call('mesh.query', {
    'object_id': cube_id,
    'element_type': 'EDGE',
    'selectors': [{'kind': 'top'}],
})['result']
indices = client.call('mesh.inspect_selection', {
    'selection_handle': selection['selection_handle'],
})['result']['indices']
```

Queries inspect **base** mesh data in Object mode. Modifiers, evaluated instances
and generated geometry are not addressed. Geometry inspection remains evaluated
through `scene.inspect_objects`. Queries do not change Blender selection, geometry,
UUIDs or revisions. Core mesh edits consume handles; see [mesh control](MESH_CONTROL.md).

Lengths use the selected coordinate space, in meters under the project conventions;
areas are square meters. Angles are degrees. World geometry includes the current
object/parent transform. Directions are coordinate-space vectors. Normals follow
transformed polygon winding, including reflections from negative scale. Degenerate
faces do not match normal selectors. Polygon normals and areas use Newell's vector;
nonplanar polygons use the projected vector area, not triangulated surface area.

| Kind | Elements | Required fields | Optional fields / meaning |
| --- | --- | --- | --- |
| `top`, `bottom`, `left`, `right`, `front`, `back` | All | None | `tolerance`: all vertices must lie on the mesh extremum plane; top +Z, right +X, front -Y |
| `within_bbox` | All | `min`, `max` (3-vectors) | `tolerance`: every vertex inside the inclusive box |
| `height_range` | All | `minimum`, `maximum` | `tolerance`: every vertex inside the inclusive Z range |
| `nearest_point` | All | `point` (3-vector) | `tolerance`: arithmetic element center closest to point; include ties within tolerance |
| `normal_direction` | FACE | `direction` (nonzero 3-vector) | `angle_degrees`, default 5: normal within inclusive cone |
| `length_range` | EDGE | `minimum`, `maximum` | Inclusive endpoint distance range |
| `area_range` | FACE | `minimum`, `maximum` | Inclusive polygon area range |
| `dihedral_angle` | EDGE | `minimum`, `maximum` | Inclusive 0–180 degree angle between two nondegenerate face normals; excludes edges with other face counts |
| `boundary` | EDGE | None | Exactly one incident face |
| `manifold` | EDGE | None | Exactly two incident faces; does not certify orientation or vertex manifoldness |
| `non_manifold` | EDGE | None | Other than two incident faces, including loose edges |
| `connected_to` | All | `seed_index` | Connected component; vertices via edges, edges via shared vertices, faces via shared edges |
| `outer_boundary` | EDGE | None | Basic semantic alias for every open boundary edge, including hole boundaries |
| `cap_faces` | FACE | None | `angle_degrees`, default 5: normal near either +Z or -Z |
| `side_faces` | FACE | None | `angle_degrees`, default 5 (max 90): normal within angle of XY plane |

Spatial tolerance defaults to `1e-6` meters. Selector fields are specific to the
kind; unrelated/missing fields, wrong element types, inverted ranges and zero
normal directions return `INVALID_ARGUMENT`. Ranges and boxes must be finite.
Extremum planes use all mesh vertices, including loose vertices. These simple
semantic selectors describe geometry, without inferring engineering roles.

`mesh.query` returns `selection_handle`, `object_id`, `element_type`, `matched_count`,
`valid_at_revision`, `space`, and `geometry: "BASE"`. `mesh.inspect_selection` takes
only `selection_handle` and adds ascending `indices` to those fields. Indices are
current base-mesh indices for debugging and seed queries, never persistent element
identities. Use handles to carry selections to mesh mutation tools.

Handles belong to one runtime session and revision. Any revision advance, including
a failed mutation attempt or future rollback, invalidates every handle. Expired,
unknown, evicted and other-runtime handles return `INVALID_SELECTION_HANDLE`.
Resolution reacquires the UUID and hashes base coordinates, edge/face topology and
world transform; changes made outside the revision system return `STALE_SELECTION`
and discard the affected handle. Deletion, identity collision, scene removal and
Edit mode surface their underlying structured errors. A restored identical mesh
and transform cannot be distinguished from the original without revision tracking.
Modifiers do not invalidate base-geometry handles. Handles are not saved in .blend
files, and no Blender object references are retained.

Limits: 256 handles per runtime (oldest-created eviction), 200,000 total mesh
vertices + edges + polygons + polygon loops per query, 10,000 matched indices.
Exceeding mesh/selection budgets returns `SELECTION_LIMIT_EXCEEDED`; no truncated
selection is returned. Each query and resolution reads and hashes the whole base
mesh. Scene edits remain serialized through the runtime. The internal resolver
must be called before a mutation advances the timeline. Broader topology,
edge loops/rings, curvature and richer semantic inference remain future work.
