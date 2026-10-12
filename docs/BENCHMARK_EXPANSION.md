# Expanded asset benchmarks

Milestone 15 implements canonical steps 77–96 with twenty versioned millimetre
briefs. `benchmarks/catalog.py` declares roles, dimensions, materials, cavities,
apertures, bores and assembly relationships. Labels are not Blender addresses;
submitted persistent UUIDs address every role. The stool and historical evidence
remain separate. All final briefs are version 3.

| Benchmark | Overall XYZ (mm) | Construction details |
| --- | --- | --- |
| coffee_table | 1000 × 600 × 450 | Top, four legs and four apron rails |
| storage_crate | 600 × 400 × 350 | Open tray, handholds and corner battens |
| wall_shelf | 800 × 250 × 200 | Shelf, rear mounting plates, arms and diagonal braces |
| bottle | 90 × 90 × 250 | Hollow body, tapered shoulder, open neck and closure bead |
| bookshelf | 800 × 300 × 1600 | Two sides, five shelves and recessed backing |
| cabinet | 800 × 450 × 900 | Shelves, backing, inset static doors and mounted pulls |
| desk_lamp | 200 × 200 × 450 | Base, roof-connected stem, hollow shade, collar, socket and switch |
| sci_fi_crate | 600 × 400 × 400 | Tray, lid, recessed plates, latches and corner inlays |
| metal_bracket | 120 × 80 × 100 | L bracket, main through-hole and two mounting bores |
| pipe_connector | 100 × 100 × 150 | Bored tube, flange and four bolt bores |
| drawer | 500 × 400 × 180 | Open tray, inset front and mounted pull |
| bench | 1200 × 400 × 450 | Top, four legs and four apron rails |
| simple_chair | 450 × 450 × 850 | Seat, legs, apron, backrest, back posts and lower stretchers |
| shelving_unit | 1000 × 400 × 1800 | Two sides, six shelves and recessed backing |
| planter | 300 × 300 × 350 | Hollow terracotta cylinder, closed bottom and drainage bore |
| toolbox | 500 × 250 × 300 | Open tray, crossbar, raised handle and corner reinforcement |
| monitor_stand | 600 × 250 × 120 | Top, side supports and rear rail |
| side_table | 450 × 450 × 550 | Top, four legs and four apron rails |
| appliance_housing | 400 × 300 × 600 | Open-front polymer shell with seven rear ventilation slots |
| product_casing | 180 × 100 × 40 | Hollow shell, bored bosses, contrasting lid and recessed screw heads |

## Reproduction

```bash
python3 -m docs.evidence.expansion_quality_build_m15 --output artifacts/all-forty-new --jobs 2
python3 -m benchmarks.expansion --engine EEVEE --output artifacts/manual-new
python3 -m docs.evidence.expansion_codex_plan_m15 --engine EEVEE --output artifacts/codex-new
python3 -m benchmarks.expansion --benchmark pipe_connector --engine EEVEE --output artifacts/pipe-new
python3 -m benchmarks.replay --output artifacts/replay-new
python3 -m conformance --output artifacts/conformance-new.json
```

Output directories must be empty. Each asset starts a fresh Blender process with
a private checkpoint and retains a report, trace and six PNGs. The suite records
incremental summaries, continues after asset failures and exits nonzero for any
failed technical acceptance or execution error. Failed assets render for diagnosis
and roll back. A dead transport is not retried; closing the client cleans its
private process. Rendering uses 128-sample EEVEE diagnostics, with a 180-second benchmark tool
allowance; the normal controller default remains unchanged. The final runner
limits concurrency to two private Blender processes by default. PNGs and raw traces
stay in ignored `artifacts/` directories.

## Three evaluation layers

**Runtime:** both builders use public tools for discovery, scene cleanup,
primitives, semantic edge queries, bevels, booleans, material assignment and
validation. No benchmark directly edits Blender data. A bounding cube intersection
bakes each primitive's nonuniform scale through `mesh.boolean` before beveling,
so widths measure actual millimetres on long panels and narrow legs. Bevels precede
cavity cuts to avoid degenerate annular miter faces. Manual round parts use 128
segments; scripted-agent parts use 192, except the small product-casing fittings/bores
use 96 to keep intermediate boolean meshes inside the recovery scan cap. Bounded procedural finishes were necessary
to resolve the recurring flat-material interface limitation. They extend
`material.create` additively while preserving plain defaults and the other 35
public descriptors; see [materials](MATERIALS.md).

**Agent:** the JSON-line bridge advertises the full brief and exact role names.
It owns transaction lifetime, rejects agent transaction control, permits repair
of structured errors and invalid finish mappings within the call budget, and
accepts a role-to-UUID mapping. UUIDs must be unique, cover every role and match
the whole scene. Failed acceptance, disconnection, malformed input and budget
exhaustion roll back. Runs retain submitted commands and tool traces.

```bash
python3 -m benchmarks.agent --benchmark coffee_table --agent "agent identity" --max-calls 500 --output artifacts/agent-new
```

Use the bridge's advertised roles, including all four apron rails for the v3
coffee table. Tool counts, elapsed tool time, structured/selection rejections and
rollbacks are measured. Token/context usage remains null because the bridge
cannot measure model usage.

The retained Codex plan is separately authored and uses duplication, different
bevel widths and different finish anchors. It discovers tools, builds, inspects
and submits UUIDs through the bridge. Reasoning happens at script-authoring time,
not through a model invocation per call. Shared briefs and prior baseline knowledge
make this an assisted scripted-agent exercise, not a blind autonomous model
comparison. Manual recipe protocol replay remains a separate transport/lifecycle
exercise and is not counted as an independent AI build.

**Asset quality:** technical acceptance checks closed geometry, overall/per-role
bounds within 2 mm, component count, complete scene coverage, assigned materials,
connected assembly and ground/contact declarations. Embedded sleeves, housed
joinery and inset fittings are explicitly recorded separately from shallow AABB
surface contacts. Neither approximate check certifies an exact fit.

Interior queries require cavity side walls, pocket back walls, slot walls and
additional bore walls. Bore faces must exceed 1e-8 square metres so tiny solver
remnants cannot establish a functional opening. Lamp cap/roof queries verify
opposing planar surfaces at Z=442 mm; bottle shoulder queries verify a slope.
Negative regressions restore the floating lamp stem, filled crate pockets,
stepped bottle shoulder, filled pipe bore, blocked planter drainage and a blocked
ventilation slot, as well as displaced roles. Rollback compares exact restored
UUID inspections against the original scene.

Visual review scores proportions, silhouette, structural plausibility, surface
cleanliness and material plausibility from 1–5: 1 poor/missing, 2 rudimentary,
3 usable blockout, 4 convincing, 5 polished. Every category must reach 4 for the
user's completion target. Assignment does not imply material appearance; EEVEE
views are required. Raw build reports leave `full_benchmark_passed: false` pending
visual review. The separate quality audit combines both technical and visual
results into `full_benchmark_passed` without implying production certification.

The audit requires 40 unique manual/scripted-agent reviews, complete scores,
six reviewed views, current brief versions, committed technical reports and exact
report/image hashes. Final evidence also hashes the reviewed runtime/build sources;
source changes revoke the review even if a version was accidentally not bumped.

```bash
python3 -m benchmarks.quality --review docs/evidence/expansion_visual_review_m15_quality_final.json --output artifacts/quality-new.json --require-quality
```

Fresh rebuilds require fresh review and hashes. Manufacturing, physical stability,
electrical function, pressure sealing, ergonomics and photorealism remain outside
these small visual benchmark briefs. Procedural grain fits individual meshes;
it does not provide end-grain or physically scaled grain on arbitrary geometry.

## Evidence and failure analysis

The final technical, visual, quality and conformance evidence use the suffix
`m15_quality_final`. Earlier `m15`, `m15_followup` and `m15_continuation` records
remain historical and retain their original failures and source hashes.
The original material descriptor is archived in
[material_create_api_1_0_m15_previous.json](evidence/material_create_api_1_0_m15_previous.json).

Earlier technical passes missed flat wood, weak structural detail, floating
lamp support, overlapping crate inlays and the stepped bottle shoulder. The
current recipes repair geometry and materials rather than changing the 4/5 visual
threshold. The lamp, pocket and slope gates remain explicit regressions. New
bores/slots have their own rejection cases. Boolean coplanarity can leave microscopic
wall remnants; the drainage regression motivated the minimum-area bore gate.

The material limitation is addressed with a small shared procedural surface
option, not per-asset runtime tools. General textures, arbitrary node editing,
material updates and broad blind model comparisons remain future work. All final
visual scores are Codex self-review, not independent external certification.

The final scripted casing attempt initially exceeded the unchanged recovery mesh
scan budget at commit and rolled back. Reducing its radial sampling from 192 to
96 produced a fresh committed build; that failed attempt remains excluded. The
accepted collection combines the 39 successful final-suite builds with this
separate casing rerun. Other geometry/material recipes remain unchanged.

Final results: all forty accepted builds commit and pass technical acceptance;
all 240 views were reviewed with every visual category scored 4/5. The strict
quality gate reports `evaluation_complete`, `asset_quality_passed` and
`full_benchmark_passed` as true with no errors. Verification records 113 unit
tests and 40 real-Blender conformance cases, zero skips.

- [Technical results](evidence/expansion_m15_quality_final.json)
- [Visual self-review](evidence/expansion_visual_review_m15_quality_final.json)
- [Passing quality gate](evidence/expansion_quality_gate_m15_quality_final.json)
- [Conformance](evidence/conformance_m15_quality_final.json)
- [Visual overview](evidence/expansion_m15_quality_preview.jpg)

Milestone 15 is complete. Milestone 16 is queued and has not been started.
