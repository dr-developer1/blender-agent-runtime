# Technical validation

Milestone 9 exposes four read-only tools in API 1.0: `validate.geometry`,
`validate.dimensions`, `validate.assembly` and `validate.asset`. Discovery reports
`validation: true` when scene and dependency-graph providers are attached. The
validation milestone brought the Blender server to 27 tools at runtime version
0.9.0. The current server tool count/version is in CURRENT_MILESTONE.md.

All tools require unique `object_ids` (1–100 managed mesh UUIDs in the active
scene). Object mode is required. Inputs are bounded and finite. Identity scans
reject collisions rather than repairing them. State guards apply to every call.
Validation does not change geometry, IDs, selection, handles or revisions.

Every result has `passed` and `checks`. Each check has `code`, `passed`,
`object_ids` and `details`, with measurements or counts and up to 20 sample
indices where relevant. Indices are diagnostic samples at the observed revision,
not persistent addresses. `passed` is the conjunction of the checks; there is no
quality score. Defects return a successful tool response with `result.passed:
false`. Invalid requests, unresolved identities, unsupported states, unmeasurable
bounds and exhausted budgets return structured execution errors. The envelope's
`validation` field remains null; reports live in `result`.

## Geometry

`validate.geometry` accepts `object_ids`, optional `geometry` (`base`, default,
or `evaluated`), `require_closed` (default true) and `area_epsilon` (default
1e-12 square meters). Areas and dimensions use transformed world vertices;
normal validity checks the mesh's local polygon normals.

Checks cover UUID uniqueness, finite coordinates, empty meshes, negative local
scale or a reflected world transform, collapsed dimensions, loose vertices and
edges, non-manifold edges, inconsistent adjacent winding, zero-area and
degenerate faces, invalid normals, exact coincident vertices and coordinate-cycle
faces. `MESH_COMPONENTS` reports the number of edge-connected vertex components
without failing disconnected geometry by itself. A nonfinite mesh yields a
JSON-safe failed `NONFINITE_GEOMETRY` check without running topology arithmetic.

Closed meshes require every edge to have two incident faces and all three world
extents to be positive. With `require_closed: false`, boundary edges and flat
surfaces are accepted; edges incident to more than two faces still fail. Loose
geometry, invalid winding and other defects remain failures. Coincident detection
uses exact positions, so intentional unwelded seams can fail this strict policy.
Zero-area detection uses Newell polygon area and is intended for planar faces.

The total budget per geometry or bounds scan is 200,000 vertices + edges + faces
+ loops across all requested meshes, including evaluated modifier output. Exceeding
it returns `VALIDATION_LIMIT_EXCEEDED`, without partial reports or writes.

## Evaluated dimensions

`validate.dimensions` requires `expected: [x, y, z]`, with optional `unit`
(`m`, default; `cm` or `mm`) and `tolerance` (default 0.001 in that unit).
It compares the union of evaluated world-space axis-aligned bounds for the
requested objects against the expected extents. Measurements in the report are
always meters. Modifiers, parenting, rotation and world scale contribute to the
bounds. An empty or nonfinite evaluated mesh returns `INVALID_GEOMETRY`.

```python
response = client.call('validate.dimensions', {
    'object_ids': part_ids,
    'expected': [400, 400, 450], 'unit': 'mm', 'tolerance': 2,
})
```

## Assembly

`validate.assembly` requires `checks` (1–200 declarations), with optional `unit`
and `tolerance` as above. Every referenced UUID must occur in `object_ids`.
Missing or irrelevant fields return `INVALID_ARGUMENT`. Pair checks require
different objects, except symmetry may compare an object to its own reflection.
The method is explicitly `evaluated_world_aabb`.

| Check kind | Fields besides `kind` | Pass condition |
| --- | --- | --- |
| `ground` | `object_id`, optional `plane` (default 0) | World bottom is within tolerance of horizontal Z plane. |
| `contact` | `object_id`, `other_id` | Boxes meet within tolerance without deep overlap along every axis. |
| `support` | `object_id`, `other_id` | First object's top meets second object's bottom and XY footprints overlap with positive area. |
| `no_overlap` | `object_id`, `other_id` | Boxes do not overlap beyond tolerance along all three axes. |
| `clearance` | `object_id`, `other_id`, `minimum` | Euclidean distance between boxes meets minimum minus tolerance. |
| `symmetry` | `object_id`, `other_id`, optional `axis` (X/Y/Z, default X), `plane` (default 0) | First box reflected across the named coordinate plane matches second box. |
| `component_count` | `expected` | Number of requested objects matches expected count. |
| `connected` | None | All requested object boxes form one contact/overlap graph within tolerance. |

`plane`, `minimum` and `tolerance` use the supplied length unit. To check floating
parts, combine `connected` with explicit `ground` checks for the intended feet.
Select role-specific UUID subsets when checking a component count such as four
legs. A mesh's internal component count is reported by the geometry validator.

These are approximate spatial checks. AABBs can overlap for separated rotated or
concave surfaces, and can hide holes. Symmetry checks bounds, not topology.
Support checks a local relationship, not balance, center of mass or load capacity.
There is no exact surface collision/contact test, physical stability simulation,
automatic role inference or inference of intended relationships in this milestone.

## Asset

`validate.asset` runs geometry validation using the same geometry options. It
optionally takes `dimensions` (the expected/unit/tolerance fields), `assembly`
(the checks/unit/tolerance fields) and `require_materials` (default false).
It combines those checks in one report without a score. Material validation checks
that every base face resolves to a nonempty object material slot, respecting
object-linked overrides; it does not judge shader appearance or material quality.
Nested dimension and assembly units are independent. A failed prerequisite such
as empty bounds returns an execution error, even if geometry findings are available.

```python
response = client.call('validate.asset', {
    'object_ids': part_ids,
    'dimensions': {'expected': [400, 400, 450], 'unit': 'mm', 'tolerance': 2},
    'assembly': {'checks': [{'kind': 'connected'}]},
    'require_materials': True,
})
if response['success']:
    failures = [c for c in response['result']['checks'] if not c['passed']]
```

Limits also include no self-intersection detection, outward-normal/volume proof,
near-duplicate tolerance, non-mesh validation, UV/export certification or repair.
External edits remain outside automatic revision tracking. Validation is an
explicit observation at the requested state, not a guarantee about later edits.

Run the Blender fixture with
`python3 -m controller.headless tests/blender/validation_smoke.py`.
