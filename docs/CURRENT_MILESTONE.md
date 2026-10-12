# Current milestone

Milestone 15 — Benchmark Expansion (steps 77–96): complete.
All twenty version-3 briefs pass runtime acceptance, scripted-agent evaluation
and the requested convincing-asset quality gate. Forty fresh builds (twenty manual
and twenty separately authored Codex scripted plans) commit successfully. All 240
EEVEE diagnostic views were inspected; every build scores 4/5 in all five visual
categories. The quality audit verifies complete coverage, current versions,
committed technical reports, exact image/report hashes and reviewed source hashes.
The earlier failing quality gates remain historical evidence.

Materials now have bounded procedural wood, coated-metal, ceramic and polymer
finishes through optional `material.create` fields. Plain defaults and original
result fields are preserved. Wood grain follows the declared part's longest local
axis. Both builders bake primitive scale through public booleans before beveling,
so long panels and narrow legs receive real millimetre edge rounding. EEVEE uses
128 diagnostic samples; benchmark clients allow 180 seconds per call. Normal
controller defaults and public observation budgets are unchanged.

The v3 assets add apron frames, crate handholds/battens, braced wall supports,
shelf backing, cabinet/drawer pulls, chair posts/stretchers, lamp fittings,
recessed crate latches/inlays, mounting/bolt bores, planter drainage, rear ventilation
and casing bosses with recessed screw heads. Prior lamp, inlay and tapered-bottle
repairs remain. Embedded joinery is declared separately from shallow AABB contact;
interior queries check pocket, slot and bore walls, excluding microscopic bore
remnants. These checks remain approximate rather than manufacturing certification.

Verification: **113 unit tests and 40 real-Blender conformance cases pass, zero
skips**. Regressions reject displaced roles, the old floating lamp stem, filled
crate pockets, an identical-bounds stepped bottle shoulder, a filled pipe bore,
blocked drainage and a blocked ventilation slot. Rollback restores exact UUID
inspections. Material tests cover procedural links/axes, persistence, rollback,
invalid arguments and allocation cleanup after an injected recipe failure.

Runtime/package version: 0.15.0; public API: 1.0; 36 public tools.
The compatibility baseline explicitly reviews the additive `material.create`
input/output fields; the other 35 descriptors remain unchanged. Its prior
descriptor and review are retained in the evidence directory. No provider
SDK, external texture dependency or per-asset runtime tool was added.

Final evidence:

- [Technical builds](evidence/expansion_m15_quality_final.json)
- [Visual self-review](evidence/expansion_visual_review_m15_quality_final.json)
- [Passing quality gate](evidence/expansion_quality_gate_m15_quality_final.json)
- [Conformance](evidence/conformance_m15_quality_final.json)
- [Visual overview](evidence/expansion_m15_quality_preview.jpg)
- [API compatibility review](evidence/material_create_api_1_0_m15_review.json)

Accepted PNGs, reports, traces and submitted agent commands are under
`artifacts/expansion-m15-quality-accepted/`, with the final scripted casing under
`artifacts/expansion-m15-quality-casing-agent-fixed/`. The accepted mapping is
`artifacts/expansion-m15-quality-accepted/final_collection.json`. Its original
summary retains the 192-sided casing rejection at commit; a 96-sided rerun
replaces it without raising recovery budgets. Prototype/superseded runs and
four-way render deadline failures are excluded. The retained final runner
reproduces all forty builds with two isolated Blender processes by default:

```bash
python3 -m docs.evidence.expansion_quality_build_m15 --output artifacts/m15-new --jobs 2
python3 -m benchmarks.quality --review docs/evidence/expansion_visual_review_m15_quality_final.json --output artifacts/m15-audit-new.json --require-quality
```

Fresh builds require fresh review; old hashes cannot certify them. Reasoning is
at Codex script-authoring time, with shared briefs and prior baseline knowledge;
this is an assisted scripted-agent evaluation, not a blind autonomous comparison.
Visual scores are self-review. Production readiness, physical functionality and
photorealism remain unassessed. Procedural grain is a mesh-fitted approximation,
with no end-grain or fixed physical grain scale. See BENCHMARK_EXPANSION.md for
contracts, run provenance and failure analysis.

Next: Milestone 16 — Adapters (steps 97–100), queued and not started.

# Previous milestone: runtime conformance

Milestone 14 — Runtime Conformance Suite (steps 70–76): complete.

Added a repository conformance report command, a frozen API 1.0 descriptor baseline
for all 36 public server tools, timed warm IPC reads and a deterministic large-scene
fixture. Existing real-Blender fixtures supply operation, evaluated inspection,
semantic selection and full-file recovery correctness. The report preserves
individual outcomes, timings, tracebacks, environment and performance measurements;
it returns nonzero on failures or skipped checks. Unit tests verify subtest failures,
errors, skipped reasons and measured result recording.

The stress fixture verifies exact listing/hierarchy coverage over 2,001 objects,
1,000 tag-filtered matches and 100 targeted world-origin inspections. It checks
clean rejection above the recovery object cap and above the independent snapshot
byte budget, then performs five transform/extrude/duplicate/rollback cycles on
250 objects with exact restored inspection, stable sessions, monotonic revisions
and checkpoint cleanup. The independent IPC case measures 25 warmed summaries.
See CONFORMANCE.md for fixed performance budgets and the coverage map.

Runtime/package version: 0.14.0; public API: 1.0; 36 public server tools.
No new public runtime capability. Compatibility pins exact descriptors and requires
explicit baseline review for additive changes as well as breaking changes.

Verification: 101 unit tests and 37 real-Blender conformance cases (the existing
34 integration cases plus three dedicated gates), with zero skipped checks.
Machine-readable run evidence is saved in `evidence/conformance_m14.json`.
An unavailable-executable run also verified nonzero exit and 37 recorded skips.

Limits: measured on the recorded Linux/Blender environment; the large fixture uses
empties and a cube rather than dense meshes. Broad timing gates detect severe
regressions and do not establish throughput guarantees. Recovery's 1,000-object
cap does not guarantee all scenes fit its separate byte/element budgets. API
compatibility compares current descriptors to a saved baseline, not historical
binary releases. Report tooling runs from the repository checkout.

Next: Milestone 15 — Benchmark Expansion (steps 77–96). Stop here per the canonical
milestone workflow.

## Previous milestone: basic materials

Milestone 13 — Basic Materials (steps 68–69): complete.

Implemented `material.create` and `material.assign`: opaque Principled PBR creation
with linear RGBA/roughness/metallic and whole-base-mesh assignment by persistent
material UUID. Assignment stages independent mesh data, preserves linked users,
and restores data/slot overrides on failure. Unassigned materials survive checkpoint
save/load through fake users; UUIDs resolve afresh after full-file rollback.
Both tools advance revisions and advertise transaction safety with recovery enabled.
Object diffs now fingerprint material slots and base face assignments. Material
UUIDs stay in tool results; envelope change arrays remain object-only.
See MATERIALS.md for exact contracts and unsupported states.

Runtime/package version: 0.13.0; public API: 1.0; 36 public server tools.
Read-only in-process instances keep material tools disabled with object control.

The manual stool recipe assigns one warm brown material to all five objects and
passes geometry, dimensions, assembly, leg count and material-assignment checks.
The exercise/agent harness now requires materials before committing. Six EEVEE
views were reviewed and separate rubric scores/image hashes recorded in
`evidence/stool_material_review_m13.json`. Original Workbench/agent evidence remains
unchanged. Material plausibility improves from 1 to 2: uniform brown PBR has no
wood grain, with faceted legs and noisy shadows still visible. Full visual
benchmark success and physical stability are not claimed.

Verification: 98 unit tests, 34 real-Blender integration cases and the mirrored
34 conformance cases. An outdated recovery tool-count assertion was corrected
and its integration/conformance checks rerun successfully. Material coverage
includes schemas/revision guards, discovery, real shader values/links, UUID rename,
unassigned persistence, rollback removal/restoration, collision and missing IDs,
linked mesh independence, single-slot replacement, edit-mode/non-mesh rejection,
UI preservation, diff visibility and injected failure cleanup/restoration.
The stool EEVEE rerun records 54 calls with zero structured rejections.

Limits: opaque surfaces, no material listing/edit/delete, no textures/procedural
recipes, no per-face assignment. Shader contents and unassigned material creation
are outside object diff scope but included in full-file restore. Workbench remains
the default shape diagnostic; use EEVEE to assess material appearance.

Next: Milestone 14 — Runtime Conformance Suite (steps 70–76): operation correctness,
inspection/selection accuracy, rollback reliability, API compatibility, performance
and large-scene inspection coverage. Stop here per the canonical milestone workflow.

## Previous milestone: first vertical slice

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
