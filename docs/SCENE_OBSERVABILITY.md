# Scene observability

The Blender server exposes `scene.summary`, `scene.list_objects`,
`scene.get_hierarchy`, and `scene.inspect_objects`, using the
current scene and view layer. All four tools are read-only, require session/revision
preconditions, and leave the timeline and persistent IDs unchanged. Standalone
API instances advertise these tools only when an object provider and scene provider
are attached. Inspection additionally requires an evaluated dependency graph
provider. Discovery reports `scene_observation` and page-size limits.

`scene.summary` accepts `{}` and returns `scene_name`, `object_count`,
`object_types` (counts keyed by Blender type), `collection_count` (including the
master collection), `visible_count`, `render_enabled_count`, and `frame`.
No object list or unbounded collection-name list is included in the summary.

`scene.list_objects` returns `objects`, `total` (all matching objects), and
`next_cursor` (string or null). Each object contains `object_id`, `name`,
`object_type`, `collections`, `visible`, `render_enabled`, `tags`, and
`world_origin`, and `parent_id` (UUID or null). IDs are persistent UUIDs; names remain labels. Results include
objects linked to the active scene, including excluded/hidden collections. Orphans
and objects linked only to other scenes are omitted. IDs are validated against
current Blender data; unmanaged objects, malformed IDs, and collisions return
identity errors rather than creating IDs during a read.

Optional filters combine with AND:

| Argument | Meaning |
| --- | --- |
| `object_type` | Exact Blender type, such as `MESH`, `EMPTY`, or `LIGHT`. |
| `collection` | Exact name of a direct membership collection within the active scene. Descendants are not implicitly included. |
| `visible` | Boolean for visibility in the active view layer, including collection exclusion and viewport hide flags. |
| `name_pattern` | Case-sensitive shell-style pattern: `*`, `?`, `[abc]`. |
| `tags` | String map; every requested key/value must match `obj["bar_tags"]`. Only string-valued stored tags are reported. |
| `region` | `{ "min": [x,y,z], "max": [x,y,z] }`; inclusive world-space object-origin box, in internal meters. |

The adapter updates the active view layer before sampling world transforms.
`visible` uses Blender's
[`Object.visible_get`](https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.visible_get)
without a viewport local-view context. `render_enabled` means only the object's
`hide_render` flag is false; it is not a prediction of final render visibility.
It does not account for collection render flags, occlusion, or render layers.
The spatial filter tests origins, not geometry bounds or evaluated surfaces.

Pagination uses `limit` (integer 1–100, default 50) and `cursor` (opaque string).
Rows are sorted by UUID; the cursor resumes after the previous page's final ID.
Repeat the same filters on subsequent requests. The page size may change.
A completed or empty result has `next_cursor: null`. Replaying a valid cursor
against the same data returns the same page for the same page size.

```python
filters = {"object_type": "MESH", "name_pattern": "Bolt_*"}
arguments = {**filters, "limit": 25}
revision = client.revision
while True:
    response = client.call("scene.list_objects", arguments, expected_revision=revision)
    if not response["success"]:
        raise RuntimeError(response["error"])
    for obj in response["result"]["objects"]:
        print(obj["object_id"], obj["name"])
    cursor = response["result"]["next_cursor"]
    if cursor is None:
        break
    arguments["cursor"] = cursor
```

Cursors carry authenticated session, revision, filter digest, observation digest,
and last UUID. There is no retained server-side page or object-reference cache.
Tampering, foreign-runtime cursors and changed filters return `INVALID_CURSOR`.
A changed revision or changed matching object data returns `STALE_SCENE_STATE`.
Restart the query with fresh observations after rejection. The observation digest
also detects relevant external edits between pages, even if those edits bypassed
the revision hooks. It does not provide general external-edit tracking.

Input validation enforces nested object fields, booleans, finite numeric vectors,
string lengths and integer bounds, rejecting unknown fields. Region minima cannot
exceed maxima. Type/collection filters without matches return an empty page.
Results exceeding the transport budget return `RESPONSE_TOO_LARGE` while keeping
the runtime usable; try a smaller limit. A single unusually large object's tags
may exceed the budget even at limit one.

Each query currently scans live identities and scene data, materializes matching
observations and sorts by UUID. The response is bounded; computation and memory
still scale with scene size. Targeted mesh inspection also visits evaluated vertices and computes triangle
counts. No general query language, mutation tools, or UI integration is added.

`scene.get_hierarchy` accepts only `limit` and `cursor`, using the same page bounds
and UUID ordering. It returns `nodes` with `object_id`, `name`, `parent_id`, plus
`total` and `next_cursor`. A root has a null parent. A parent UUID can refer to an
object outside the active scene or outside the current page; callers reconstruct
relationships by ID. Children are not dumped in unbounded arrays. Hierarchy and
object-list cursors cannot be interchanged, and reparenting invalidates a cursor.

`scene.inspect_objects` requires `object_ids`, a unique array of 1–100 UUIDs.
Results preserve request order in `objects`. Each result includes the listing
fields, evaluated `world_matrix` (4×4), `base_geometry`, `evaluated_geometry`,
`evaluated_bounds`, `evaluated_dimensions`, and `bounds_method`. All requested IDs
are checked before geometry evaluation. Unknown IDs return `OBJECT_NOT_FOUND`;
managed objects outside the active scene return `OBJECT_NOT_IN_SCENE`; objects
excluded from the active dependency graph return `OBJECT_NOT_EVALUATED`. Missing,
duplicate, malformed or oversized ID lists are rejected. These are scene reads,
so identity repair never happens implicitly.

Mesh geometry records contain `vertices`, `edges`, `faces`, and `triangles`.
Base counts describe the original mesh; evaluated counts include viewport-enabled
modifiers. World bounds for meshes are computed from evaluated vertex positions,
including parent transforms, rotation and negative scale. `evaluated_dimensions`
is the extent of that world-axis-aligned box in meters, not a local-space
`Object.dimensions` value. `bounds_method` is `evaluated_vertices` for meshes.
Other supported geometry types use transformed evaluated bounding-box corners,
with method `evaluated_bounding_box`; this enclosing box may be conservative under
rotation. Empty geometry and objects without geometry return null bounds,
dimensions and method. Mesh counts are null for non-mesh objects.

The adapter uses Blender's
[evaluated dependency graph](https://docs.blender.org/api/current/bpy.types.Depsgraph.html)
for animated, constrained and modified data. Evaluation follows the current view
layer and viewport modifier settings, not a render-mode graph. Instanced geometry
is not expanded. No temporary mesh data-blocks or evaluated object references are
retained after the response. Computing bounds scales with inspected mesh size;
inspection is bounded by object count, not by vertex processing time.
