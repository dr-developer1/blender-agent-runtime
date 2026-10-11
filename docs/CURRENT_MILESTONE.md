# Current milestone

Milestone 9 — Validation (steps 46–49): complete.

Implemented `validate.geometry`, `validate.dimensions`, `validate.assembly` and
`validate.asset`. The server advertises 27 public tools. Runtime package version:
0.9.0; public API version: 1.0.

Validators use bounded numeric mesh snapshots and return `passed` plus concrete
checks in `result`. Geometry checks cover empty/nonfinite meshes, negative scale,
collapsed dimensions, loose and non-manifold topology, zero-area/degenerate faces,
normal validity, adjacent winding, exact coincident geometry and component counts.
UUID collisions remain structured resolver errors. Closed geometry is the default;
explicit open-surface policy permits flat boundaries. Evaluated dimension checks
include modifiers and world transforms and compare the union of requested bounds.

Assembly validation takes explicit declarations for ground, contact, support,
non-overlap, clearance, bounds symmetry, object count and connected object boxes.
Every spatial relationship uses evaluated world AABBs and reports that method.
Asset validation combines geometry with optional dimensions, assembly declarations
and base-face material assignment checks. No composite score is produced.

All tools are read-only, state guarded, and independent of the mutation backend.
They preserve geometry, identity, Blender UI state, revision and current handles.
Scans are limited to 200,000 total mesh elements; assembly calls allow at most
200 checks and all validators accept at most 100 unique mesh UUIDs.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 74 unit tests, 26
real-Blender integration cases and the same 26 conformance checks passed. The
isolated validation and API discovery fixtures also passed. Cases verify defects
versus execution failures, empty/nonfinite geometry, planar policy, singular and
negative transforms, modifier/rotation-aware dimensions, all assembly check kinds,
asset composition, material assignment, unchanged data/UI/handles/revisions,
strict schemas, stale state, missing/non-mesh objects, collisions, Edit mode and
budget rejection. Exact commands are in README.md and contracts in VALIDATION.md.

Limits: Object mode and active-scene meshes only. Assembly checks approximate
bounds rather than exact surface contact/collision or physical stability. Symmetry
compares boxes, and component count compares requested objects. Geometry does not
prove outward orientation, detect self-intersections, certify nonplanar polygon
area, or find near-duplicates. Material checks verify assignment rather than visual
quality. Bounds for empty/nonfinite meshes return an execution error. Asset
validation is configurable technical checking, not export or production-quality
certification. External changes are not automatically revision tracked. No general
repair, transaction recovery or rollback yet.

Next: Milestone 10 — Recovery (steps 50–56): scene diff, transaction begin,
snapshot, commit, rollback, monotonic rollback revisions and UUID re-resolution.
