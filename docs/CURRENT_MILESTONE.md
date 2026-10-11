# Current milestone

Milestone 6 — Semantic Geometry Addressing (steps 28–35): complete.

Implemented `mesh.query` and `mesh.inspect_selection`, selection schemas,
spatial/geometric/topological/basic semantic selectors, bounded selection handles,
revision invalidation and real-Blender selection conformance. The server advertises
thirteen public tools. Runtime package version: 0.6.0; public API version: 1.0.

Selectors address base mesh vertices, edges or faces in world/local coordinates,
combine by intersection, and return temporary handles. Spatial queries cover
extremum planes, boxes, height ranges and nearest centers. Geometric queries cover
normal cones, lengths, areas and dihedral angles. Topological queries cover edge
incidence and connected components. Basic semantic queries cover cap/side faces and
open boundaries. Queries preserve geometry, UI selection, UUIDs and revision.

Handles bind the current runtime revision and UUID. Resolution reacquires live
geometry and verifies a fingerprint covering base coordinates, topology and world
transform, detecting untracked edits. Any revision change invalidates every handle.
The store retains no Blender references and caps at 256 handles with oldest-created
eviction. Queries cap at 200,000 mesh vertices + edges + polygons + loops and
10,000 matched indices, returning structured errors instead of truncation.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 60 unit tests, 20
real-Blender integration cases (also exercised as conformance checks), and direct
headless process/API/state/identity/scene/geometry/selection smoke checks. Fixtures
verify four cube top perimeter edges, upward faces, upper-height faces, sharp
angles, open boundaries, non-manifold branches, disconnected components,
world/local transforms, negative scale, empty/degenerate meshes, modifier
independence, handle eviction, budgets and invalidation. All previous lifecycle,
state, identity and scene regressions remain covered. Commands are in README.md.

Limits: background runtime; public tools still provide discovery and reads only.
Mesh queries require Object mode and address base geometry; generated modifier
results and instances are excluded. Areas/normals use Newell's vector (projected
area for nonplanar polygons). Basic outer_boundary includes holes; edge incidence
does not certify full manifoldness. Element indices are diagnostic and temporary.
Untracked edits restored to identical data cannot be detected without timeline
tracking. Every query/resolution scans and hashes the base mesh. No edge-loop/ring,
curvature, richer semantic inference, public modeling, transaction or recovery
support yet. See SELECTION_LANGUAGE.md for exact contracts and limits.

Next: Milestone 7 — Basic Object Control (steps 36–40): primitive creation,
deterministic transforms, duplication, deletion and parenting, with revision and
identity tracking and integration/conformance tests.
