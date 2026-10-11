# First vertical slice: stool

Milestone 12 exercises the same API 1.0 used by all clients. No stool-specific
runtime tool, provider SDK, unrestricted runtime script execution or additional
agent is introduced. `benchmarks.stool` supplies a deterministic hand-authored
baseline; `benchmarks.agent` connects a single external agent through JSON lines.
The actual agent run used this Codex session, with interactive tool decisions and
UUID/selection-handle results passed back through the bridge.

The prompt is the canonical modern wooden stool: 450 mm high, 400 mm wide, four
slightly angled and tapered legs, rounded edges, clean geometry and wood-like
material. The baseline uses a rectangular seat and four angled, tapered legs. The Codex
agent chose a circular seat and produced tapered legs by subtracting a cube from
an inverted cone, beveling the remaining end rings, duplicating the result and
tilting each leg. Both exercises delete factory objects inside a private transaction.

## Measured results

Measured on Linux with Python 3.12.3 and Blender 5.2.2 LTS, through persistent IPC.
The initial evidence used runtime 0.11.0 / API 1.0; this benchmark release is 0.12.0
with the same public tools and schemas.

| Criterion | Manual baseline | Codex agent |
| --- | --- | --- |
| Width / depth / height | 400.00 / 400.00 / 450.00 mm | 399.68 / 399.68 / 450.00 mm |
| Four distinct leg objects | Pass | Pass |
| Closed geometry, non-manifold edges, degenerate faces, negative scale | Pass | Pass |
| Common ground, each leg supporting seat, connected assembly | Pass | Pass |
| Assigned materials | Fail | Fail |
| Full benchmark | Incomplete | Incomplete |
| Recorded public calls, including harness evaluation/transaction calls | 48 | 34 |
| Structured API rejections | 0 | 0 |

Ground/contact/support checks use evaluated AABBs with 2 mm tolerance. They do not
prove exact surface contact, stability or load capacity. Angle, taper and rounding
are visible/modeling observations rather than automatically certified criteria.
The subjective visual rubric was reviewed separately from technical checks;
scores and evidence are recorded below. No composite technical score is invented.

Final local artifacts from this session are in `artifacts/stool-manual-final` and
`artifacts/stool-agent`: `report.json`, `trace.json`, six named PNGs and, for the
agent, `agent_commands.json`. Artifacts are ignored by Git. No persistent `.blend`
asset is exported: the runtime has no public save/export tool yet. UUIDs in evidence
belong to their recorded sessions and cannot be reused in a new runtime.

## Failure analysis and refinement

Missing material creation/assignment is a confirmed interface gap: discovery has
no such tools and `validate.asset(require_materials=True)` fails. Implement general
basic PBR creation/assignment in Milestone 13 rather than a stool-specific tool.

The initial assumption that taper was an interface limitation was incorrect.
Cone creation and boolean subtraction compose into a frustum. The agent run
demonstrated this and the reports' analysis revision records the correction. The
original manual recipe's untapered legs were a baseline simplification, not proof
of a runtime limitation. That recipe has now been repaired with public cone,
boolean, bevel, transform and inspection calls. Independent semantic queries in
the Blender integration test assert a larger upper cap and a smaller foot cap on
every leg. Missing a convenience tool alone does not establish incapability.

The first tilted agent leg measured a bottom at -2.47 mm, outside the 2 mm ground
tolerance. Inspection exposed this placement error; the agent raised the leg by
2.47 mm before duplicating. Final geometry and assembly checks pass. This was an
agent positioning issue corrected using existing inspection and transform tools.

Refinement is in the exercise/reporting layer: role UUIDs are explicit, technical
failure reports remain distinct from interface gaps and unverified visual criteria,
arguments are copied into traces, PNG payloads are separate, and transport failures
are distinguished from repairable structured tool errors. No repeated runtime
failure justified changing the public tool set in this exercise.

## Connecting an agent

```bash
python3 -m benchmarks.agent --agent "Codex session" --output artifacts/new-agent-run
```

The first stdout line reports the task, available tools and session. Send one JSON
object per stdin line, reading each response before making dependent decisions:

```json
{"tool":"scene.list_objects","arguments":{}}
{"tool":"runtime.describe_tool","arguments":{"name":"mesh.bevel"}}
```

Tools preserve the ordinary success/error envelope and revision information.
The bridge omits PNG payloads from responses/traces; final renders are saved as
artifacts. The controller supplies current state preconditions. No failed call is
automatically retried. Discover schemas and query a fresh selection handle after
every mutation. Explicitly remove all factory objects before constructing the stool.

Finish using actual UUIDs returned by creation/duplication:

```json
{"finish":{"seat":"<seat UUID>","legs":["<leg 1>","<leg 2>","<leg 3>","<leg 4>"]}}
```

The harness evaluates roles, renders and commits when supported technical checks
pass, even while material/visual requirements remain incomplete. Failed technical
checks trigger rollback. EOF, malformed input, transport failure or call-budget
exhaustion also leave the checkpoint subject to rollback/owned-process cleanup.
Transaction controls and scene.diff belong to the harness and are excluded from
the bridge's advertised agent tools. Default budget: 100 input commands, maximum
500; each line is limited to 1 MiB and runtime calls have a 90-second deadline.
This is a local trusted agent bridge, not a network service or provider adapter.

Verification includes the manual public-API build and renders, post-build deletion
and full-file rollback with UUID re-resolution, bridge schema rejection followed
by successful modeling, blocked agent transaction controls and EOF rollback.
Tests are in `tests/integration/test_stool.py` and mirrored by conformance.

## Milestone 12 acceptance

| Canonical step | Completed evidence |
| --- | --- |
| 63: manual stool | Repeatable hand-authored public-API build with tapered, angled legs; technical checks and six rendered views. |
| 64: connect one AI agent | This Codex session connected through the local JSON-line bridge; no new provider credentials required. |
| 65: AI stool | Interactive Codex build with live UUID/handle observations; command trace, technical report and six views saved. |
| 66: classify model versus interface failures | Ground-placement error corrected; mistaken taper diagnosis corrected; missing material tools confirmed by discovery and validation. |
| 67: refine selection/tools/inspection | Explicit role-based checks, cap-area regression coverage, faithful argument traces, PNG separation and distinct API/transport failure handling; no repeated core-runtime defect justified adding a tool. |

Both stools' visual evaluations are recorded. Milestone 12 is complete as a
vertical-slice exercise with analyzed outcomes. Completion does not mean the
entire wooden-stool benchmark passes: material creation/assignment belongs to
Milestone 13 and remains a recorded interface gap.

## Visual evaluation

Evaluator: **Codex (GPT-6), same session as builder; unblinded self-review**.
Rubric version: **stool-visual-v1**. All six Workbench PNGs of each build were
directly inspected. Scores use 1–5: 1 absent/major problems, 2 noticeable problems,
3 adequate with limitations, 4 good with minor limitations, 5 excellent.
There is no overall score. This is a recorded self-review, not independent expert
or blind evaluation. The JSON record includes image paths and SHA-256 hashes so
the reviewed evidence can be identified after future builds:
[visual review record](evidence/stool_visual_review_v1.json).

| Category | Manual | Codex agent | Observation |
| --- | --- | --- | --- |
| Proportions | 4 | 4 | Clear compact-stool proportions; dimensions independently validated. |
| Silhouette | 4 | 4 | Recognizable symmetric forms, gently splayed tapered legs; opposite legs overlap in cardinal projections. |
| Structural plausibility | 3 | 3 | Legs visually meet seat and ground; no visible joinery or bracing. Strength/stability remains unproven. |
| Surface cleanliness | 3 | 3 | No obvious holes or detached pieces; cylindrical faceting and uneven highlight bands remain. Edge rounding is subtle under nonuniform scale. |
| Material plausibility | 1 | 1 | Grey diagnostic shading has no wood appearance; material assignment fails. |

The visual observations confirm leg taper/angle and edge rounding without claiming
production-ready surfaces. Material appearance will be reassessed after Milestone
13 using EEVEE; current scores preserve the pre-material baseline. The absent
material is classified as an interface gap. Faceting and limited joinery are
model/recipe quality limitations, not evidence of a failed runtime operation.
