# Current milestone

Milestone 12 — First Vertical Slice (steps 63–67): complete.

Implemented a manual public-API stool baseline, one-agent JSON-line bridge,
role-based technical evaluation, separate traces/reports/render artifacts and
model-versus-interface failure analysis. This Codex session connected through the
bridge and built a stool with a circular seat and four angled, tapered legs.
Both builds now have angled, tapered legs and pass dimensions, geometry and
approximate assembly checks. The manual recipe uses cone/boolean construction;
integration tests independently check larger top-cap and smaller foot-cap areas
on all four legs. All six views of each stool were reviewed and per-category
visual scores recorded with evaluator identity and rubric version in
evidence/stool_visual_review_v1.json. See STOOL_BENCHMARK.md for the acceptance
checklist, measured results, scores and failure analysis.

The milestone's manual/AI exercise, visual evaluation and failure classification
are complete. The full wooden-stool benchmark still fails material assignment;
general material tools are the explicitly scheduled work of Milestone 13. Visual
self-review records faceting and absent joinery rather than claiming production
quality. Physical stability is outside the current approximate validation contract.

Runtime/package version: 0.12.0; public API: 1.0; 34 public tools. No new public
runtime tools or provider dependencies. The bridge owns transactions and rolls
back on incomplete/disconnected agent runs. Artifacts are generated locally and
ignored by Git; no persistent .blend export is exposed yet.

Verification: 93 unit tests and 33 real-Blender integration cases, mirrored in
conformance. The tapered manual baseline, actual interactive Codex build, all six views,
bridge rejection/repair and disconnect rollback were exercised. The new tests also
check trace argument snapshots, PNG omission and transport-error propagation.

Next: Milestone 13 — Basic Materials (steps 68–69): simple PBR material creation
and assignment, then rerun stool material checks and reassess material appearance
with EEVEE. Existing Workbench visual scores are retained as the pre-material baseline.

## Previous milestone: diagnostic observation

Milestone 11 — Observation (steps 57–62): complete.

Implemented `observe.camera`, `observe.render` and `observe.render_multiview`.
The persistent server advertises 34 public tools. At that milestone the runtime
package version was 0.11.0; public API version: 1.0. In-process owners opt in with `observation=True`
and live scene/view-layer/evaluated providers, independently of object control.

Deterministic cameras fit evaluated world mesh bounds with aspect/depth-aware
framing. Front/back/left/right/top/bottom use orthographic cameras; perspective
uses a fixed diagonal camera and 50 mm lens. Workbench is the default engine at
384 × 384. Multiview returns front/back/left/right/top/perspective in one bounded
batch. Optional EEVEE preserves mesh materials and UVs under a diagnostic world
and area light rig; engine names handle both EEVEE_NEXT and EEVEE. Wireframe shows
actual evaluated edges (including loose edges) as thin curves; silhouette uses
black unlit surfaces. Both are Workbench modes on white. Camera metadata, target
UUIDs and inline PNG data are fully described by discovery schemas.

All observation calls are read-only and transaction safe. Source geometry,
materials, selection, active object, camera, frame and render/colour settings are
preserved. Render settings live on an isolated temporary scene containing copied
evaluated geometry, a private camera/world and optional lights/curves. Temporary
objects and data are removed in finally, including injected render failures and
PNG overflow. PNG files live under the controller's temporary root and are removed
before returning. Volatile timestamp/filename stamps and dithering are disabled.
Blender's global Render Result may be replaced, but tracked scene state is not.
Cursors and selection handles remain usable; scene.diff stays empty after renders,
and UUID resolution works after full-file rollback.

Limits: Object mode, meshes in the active scene/view layer, visible and render
enabled. Default selection omits cameras/lights/non-meshes. Explicit targets must
be unique managed UUIDs; instanced targets reject rather than silently losing
instances. Geometry is viewport evaluated, not render-time modifier evaluation.
Budgets are 100 objects, 200,000 evaluated vertices+edges+faces, six views,
768 pixels per axis, 1,048,576 combined pixels and 700,000 combined raw PNG bytes.
Base64 with bounded metadata fits the existing 1 MiB transport frame. Coordinates
must be finite and within one million metres. Rendering and dependency-graph costs
remain bounded by the controller deadline rather than the scan budget. EEVEE
startup can require a longer client timeout on software renderers. Native GPU
failures and externally installed callbacks are outside Python cleanup guarantees.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 90 unit tests, 31
real-Blender integration cases and the same 31 conformance checks passed. Coverage includes
all camera views at square/portrait/landscape aspect ratios, default six-view PNG
transport, actual solid/wire/silhouette pixels, repeated images and camera metadata,
EEVEE material appearance, hostile source render settings, allocation/file cleanup,
transaction/handle/cursor preservation, rollback re-resolution, unsupported modes,
missing/duplicate/unmanaged/out-of-scene/non-mesh/hidden/empty/instanced targets,
geometry/pixel/PNG budgets and injected renderer failure. Commands are in README.md
and the full observation contract is in OBSERVATION.md.
