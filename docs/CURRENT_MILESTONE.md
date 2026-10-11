# Current milestone

Milestone 5 — Scene Observability (steps 22–27): complete.

Implemented: `scene.summary`, filtered `scene.list_objects`, bounded cursor
pagination, targeted `scene.inspect_objects`, paginated `scene.get_hierarchy`,
and evaluated geometry/dimensions. The Blender server advertises eleven tools.
Filters combine type, direct collection membership, active-view-layer visibility,
name patterns, string custom tags and inclusive world-origin regions. Pages are
UUID-sorted, default to 50, and cap at 100. Signed cursors bind endpoint, session,
revision, filters and observed data, rejecting tampering and stale observations.
Scene reads preserve UUIDs and the revision. Nested schema validation enforces
filters and bounds. Oversized responses return structured failures.

Targeted inspection reports original/evaluated mesh and triangle counts, evaluated
world matrices, world-axis-aligned bounds and dimensions. Mesh bounds use evaluated
vertices; non-mesh geometry uses evaluated box corners. Parent UUIDs describe
hierarchy without unbounded child lists. Inspection preserves request order and
rejects duplicate/unknown IDs, other-scene objects and excluded evaluation.
Runtime package version: 0.5.0; public API version: 1.0.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 49 unit tests and 18
real-Blender integration cases (also exercised as conformance checks), plus direct
headless API, scene and geometry smoke checks. Includes a 253-object filtered
pagination fixture, collection exclusions, untracked edits, cursor rejection,
array/mirror/solidify modifiers, parent transforms, rotation, negative scale,
nullable geometry and mesh-data leak checks. All previous lifecycle, state and
identity regressions remain covered. Commands are in README.md.

Limits: background runtime; public tools provide discovery/reads only. Scene reads
never repair IDs. Scene-page computation still scans and sorts live data; geometry
bounds scale with inspected vertex counts. Evaluated data follows current viewport
settings, and instances are not expanded. Render-enabled flags are object flags,
not final render visibility. Region filtering tests origins, not surfaces. External
edits invalidate relevant cursors but are not generally revision-tracked. No general
query language, semantic geometry addressing, transactions, recovery, AI or UI yet.
See SCENE_OBSERVABILITY.md for exact contracts and limits.

Next: Milestone 6 — Semantic Geometry Addressing (steps 28–35): selection schemas,
spatial/geometric/topological/basic semantic selectors, selection handles, revision
invalidation and conformance tests.
