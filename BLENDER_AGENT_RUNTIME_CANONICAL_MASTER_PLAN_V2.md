# Blender Agent Runtime — Canonical Master Plan v2

## 0. Product Definition

Build the best possible machine interface between AI systems and Blender.

The project is not primarily:

> an AI that makes 3D models.

The project is:

> a stable, expressive, inspectable, reversible, model-independent machine interface that exposes Blender to current and future AI systems without unnecessary limitations.

The runtime should eventually allow any capable AI system to:

1. Discover what Blender capabilities are available.
2. Inspect a scene accurately and selectively.
3. Address objects and geometry reliably.
4. Perform precise modeling and scene operations.
5. Compose low-level tools into complex workflows.
6. Use optional professional skills when helpful.
7. Observe the effects of its own actions.
8. Validate technical and structural correctness.
9. Roll back failed or harmful edits.
10. Export production-ready results.
11. Access progressively broader Blender capabilities over time.
12. Remain compatible with different AI providers and future models.

---

# 1. Architectural Priorities

Every major design decision must be evaluated against these six priorities.

## 1.1 Controllability

The agent must be able to express precise operations without fighting Blender UI state.

## 1.2 Observability

The agent must be able to retrieve accurate, structured information about:

- scene state
- objects
- topology
- modifiers
- materials
- transforms
- hierarchy
- geometry
- relationships
- validation problems

## 1.3 Reliability

Operations should:

- behave predictably
- return structured errors
- report state changes
- support recovery
- avoid hidden context dependencies

## 1.4 Expressiveness

The interface should eventually expose nearly all useful Blender functionality.

Do not constrain the runtime around only the limitations of current AI models.

## 1.5 Composability

Small tools should compose into:

- larger procedures
- reusable skills
- workflows
- agent plans

## 1.6 Portability

Different AI systems should use the same Blender capabilities through different adapters.

---

# 2. High-Level Architecture

```text
                    AI SYSTEMS
       GPT / Claude / Gemini / Local / 3D AI
                         |
                         v
               PROTOCOL ADAPTERS
             MCP / REST / SDK / CLI
                         |
                         v
        +----------------------------------+
        |       BLENDER AGENT API          |
        |----------------------------------|
        | API Versioning                   |
        | Capability Discovery             |
        | Typed Contracts                  |
        | Semantic Geometry Queries        |
        | Selection Handles                |
        | Tool Introspection               |
        +----------------+-----------------+
                         |
                         v
        +----------------------------------+
        |          CORE RUNTIME            |
        |----------------------------------|
        | Session Management               |
        | Monotonic Revisions              |
        | Stable Object Identity           |
        | Scene Inspection                 |
        | Geometry Operations              |
        | State Tracking                   |
        | Transactions                     |
        | Rollback / Recovery              |
        | Scene Diff                       |
        | Geometry Validation              |
        | Assembly Validation              |
        | Observation / Rendering          |
        +----------------+-----------------+
                         |
                         v
                      BLENDER
                         |
                         v
        +----------------------------------+
        |       OPTIONAL CAPABILITIES      |
        |----------------------------------|
        | Professional Skills              |
        | Workflow Registry                |
        | Expert Demonstrations            |
        | Specialized Validators           |
        | Specialized Models               |
        +----------------------------------+
```

The optional capabilities must use the same core runtime API.

They must not become a second incompatible control system.

---

# 3. Core vs Skills

## Core Runtime

The core runtime should expose general Blender capabilities.

Examples:

```text
scene.summary
scene.query
scene.inspect_objects

object.create
object.transform
object.duplicate
object.delete

mesh.query
mesh.select
mesh.extrude
mesh.inset
mesh.bevel
mesh.boolean
mesh.merge
mesh.delete

material.inspect
material.create
material.assign

validate.geometry
validate.assembly
```

## Skills Layer

Skills are convenience procedures built on the core.

Examples:

```text
skill.create_furniture_leg
skill.create_panel
skill.create_enclosure
skill.create_fastener
skill.create_game_prop_shell
```

A weak/current model may rely heavily on skills.

A future stronger model may prefer direct core tools.

Both must remain supported.

---

# 4. Near-Complete Blender Coverage as Long-Term Goal

The runtime should be designed to eventually expose nearly all relevant Blender functionality.

Implement incrementally.

Suggested capability families:

## Level A

- scenes
- objects
- transforms
- meshes
- materials
- modifiers

## Level B

- semantic geometry selection
- UVs
- curves
- collections
- constraints

## Level C

- Geometry Nodes
- procedural systems
- advanced topology operations

## Level D

- rigging
- animation
- shape keys

## Level E

- physics
- cloth
- fluids
- particles
- simulation

## Level F

- rendering
- lighting
- compositing

## Level G

- advanced/specialized Blender functionality

Near-complete coverage does **not** mean wrapping every `bpy.ops` call one-to-one.

Expose coherent capability families.

---

# 5. Process Architecture

Prototype this before building major modeling features.

## Interactive use

Use a long-lived Blender process.

```text
AI / CLI
   |
   v
External Controller
   |
   | IPC
   v
Long-running Blender
   |
   v
Synchronous Command Executor
   |
   v
Runtime
```

## Rule

Blender mutations are serialized.

```text
request
→ execute
→ response
→ next request
```

Do not mutate Blender from arbitrary worker threads.

## Headless processes

Use isolated headless Blender processes for:

- CI
- regression tests
- benchmark isolation
- crash recovery tests
- conformance testing

---

# 6. Public Conventions

Document once.

## Axes

```text
+Z = up
X/Y = ground plane
```

Recommended asset front:

```text
forward = -Y
up = +Z
```

## Units

Public APIs may accept:

```text
mm
cm
m
```

Normalize internally to meters.

## Angles

Public API:

```text
degrees
```

Internal Blender conversion may use radians.

## Rotation order

Default:

```text
XYZ
```

## Dimensions

Default meaning:

```text
evaluated world-space dimensions
```

unless explicitly documented otherwise.

---

# 7. Session and Revision Model

## Session ID

Every Blender runtime instance gets:

```text
session_id
```

A Blender restart creates a new session.

## Monotonic Revision

The revision counter never moves backward.

Example:

```text
revision 43
edit
revision 44
edit
revision 45
rollback to old scene snapshot
revision 46
```

Rollback restores scene contents, not the runtime timeline.

## Request

```json
{
  "api_version": "1.0",
  "session_id": "abc123",
  "expected_revision": 46,
  "tool": "object.transform",
  "arguments": {}
}
```

If revision mismatches:

```text
STALE_SCENE_STATE
```

---

# 8. Stable Object Identity

Every managed object receives a persistent UUID.

Example:

```python
obj["bar_uuid"] = "7cbd3b9f-..."
```

Requirements:

- rename-safe
- save/load-safe
- duplicate-safe
- deletion-safe
- collision detection

Object names remain labels only.

---

# 9. API Versioning

Introduce API versioning from the beginning.

Example:

```text
BAR API 1.0
```

Requests include:

```json
{
  "api_version": "1.0"
}
```

The runtime should support:

```text
runtime.get_version
runtime.get_supported_versions
```

Later, individual capability versions may be exposed.

---

# 10. Capability Discovery

This belongs in the core.

Implement:

```text
runtime.describe_capabilities
runtime.list_tools
runtime.describe_tool
runtime.get_supported_features
runtime.get_limits
runtime.get_version
```

Example:

```json
{
  "tool": "runtime.describe_tool",
  "arguments": {
    "name": "mesh.bevel"
  }
}
```

Possible response:

```json
{
  "name": "mesh.bevel",
  "version": "1.2",
  "description": "Bevel selected mesh edges.",
  "supports": {
    "semantic_selection": true
  },
  "side_effects": [
    "topology_change"
  ],
  "transaction_safe": true
}
```

This allows agents and adapters to discover functionality dynamically.

---

# 11. Tool Contract

## Request

```json
{
  "api_version": "1.0",
  "session_id": "abc123",
  "expected_revision": 12,
  "tool": "mesh.bevel",
  "arguments": {}
}
```

## Success

```json
{
  "success": true,
  "session_id": "abc123",
  "revision_before": 12,
  "revision_after": 13,
  "created_ids": [],
  "modified_ids": ["obj_a1"],
  "deleted_ids": [],
  "warnings": [],
  "metrics": {},
  "validation": null
}
```

## Failure

```json
{
  "success": false,
  "session_id": "abc123",
  "revision": 12,
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "Width must be greater than zero.",
    "details": {}
  }
}
```

---

# 12. Scene Inspection

Scene inspection must scale.

Do not rely on one giant scene dump.

Implement:

```text
scene.summary
scene.list_objects
scene.inspect_objects
scene.query
scene.get_hierarchy
```

## Filtering

Support:

- object type
- collection
- visibility
- name patterns
- custom tags
- spatial region
- pagination

## Pagination

Use:

```text
limit
cursor
```

for large scenes.

---

# 13. Evaluated Geometry

The runtime must distinguish:

```text
base geometry
evaluated geometry
```

Use evaluated geometry for:

- final dimensions
- final bounds
- modifier results
- mirrored results
- array results
- solidify results
- final triangle counts when relevant

---

# 14. Semantic Geometry Addressing

This moves into the early core architecture.

The hard problem is not executing operations.

The hard problem is identifying **what geometry the agent means**.

Do not rely solely on unstable vertex/edge/face indices.

---

# 15. Semantic Geometry Query System

Introduce:

```text
mesh.query
```

The query system should support four selector families.

## Spatial selectors

Examples:

```text
top
bottom
left
right
front
back
nearest_point
inside_volume
within_bbox
height_range
```

## Geometric selectors

Examples:

```text
normal direction
angle threshold
length range
area range
curvature
orientation
distance
```

## Topological selectors

Examples:

```text
boundary
connected_to
adjacent_to
edge_loop
edge_ring
manifold
non_manifold
```

## Semantic selectors

Examples:

```text
outer_boundary
support_edges
attachment_region
symmetry_partner
cap_faces
side_faces
```

Semantic selectors may begin simple and become richer over time.

---

# 16. Selection Handles

Avoid forcing permanent IDs on every mesh element initially.

Use temporary revision-bound selection handles.

Example:

```json
{
  "selection_handle": "sel_1029",
  "object_id": "obj_123",
  "element_type": "EDGE",
  "matched_count": 4,
  "valid_at_revision": 83
}
```

Then:

```json
{
  "tool": "mesh.bevel",
  "arguments": {
    "selection_handle": "sel_1029",
    "width_mm": 3,
    "segments": 3
  }
}
```

If topology changes and revision becomes 84:

```text
sel_1029 is invalid
```

This solves many practical geometry-addressing problems without requiring permanent face/edge IDs immediately.

---

# 17. Geometry Selection Accuracy Benchmarks

Create fixture scenes specifically for selection.

Examples:

```text
Select four top perimeter edges of a cube.
Select upward-facing faces.
Select the outer boundary loop.
Select all faces above 75% of object height.
Select all edges with dihedral angle > 40°.
```

Expected selections are deterministic.

This becomes a core interface benchmark.

---

# 18. Core Modeling Operations

Initial core operations:

```text
object.create_primitive
object.transform
object.duplicate
object.delete
object.set_parent

mesh.query
mesh.select
mesh.extrude
mesh.inset
mesh.bevel
mesh.boolean
mesh.cleanup
```

Later:

```text
mesh.bridge
mesh.loop_cut
mesh.dissolve
mesh.merge
mesh.slide
mesh.knife
mesh.solidify
mesh.mirror
mesh.array
mesh.subdivision
mesh.weighted_normals
```

---

# 19. Geometry Validator

Deterministic checks:

- non-manifold edges
- loose vertices
- loose edges
- zero-area faces
- degenerate faces
- invalid normals
- duplicate geometry where detectable
- negative scale
- invalid dimensions
- empty meshes
- UUID collisions

Do not return arbitrary composite quality scores.

Return pass/fail plus concrete issues.

---

# 20. Assembly Validator

Geometry-valid parts can still form a broken object.

Add early checks for:

- floating components
- unintended interpenetration
- expected contact
- ground contact
- approximate symmetry
- support relationships
- component count
- clearances

Example stool:

```text
4 legs
each leg contacts seat
all legs reach ground plane
legs do not collide with each other
seat is supported
no floating component
```

---

# 21. Transactions

V0 strategy:

```text
transaction.begin
snapshot
mutate
validate
commit / rollback
```

Temporary `.blend` snapshots are acceptable initially.

After rollback:

```text
old Python references are invalid
re-resolve by UUID
revision continues forward
```

---

# 22. Scene Diff

Every mutation should report what changed.

Track initially:

- created objects
- modified objects
- deleted objects
- vertex count changes
- face count changes
- evaluated dimensions
- transforms
- modifiers

Later:

- UV state
- materials
- hierarchy
- topology metrics

---

# 23. Observation Engine

## Diagnostic default

Use:

```text
Workbench
```

or:

```text
EEVEE
```

when material appearance matters.

Default resolution:

```text
384 × 384
```

Required views:

- front
- back
- left
- right
- top
- perspective

Later:

- bottom
- wireframe
- normals
- depth
- silhouette
- object IDs
- material IDs
- UV layout

Cycles is for final rendering, not normal agent loops.

---

# 24. Restricted Advanced Execution

Typed tools remain the default.

However, long-term expressiveness must remain visible as a design goal.

Possible future advanced mechanism:

```text
experimental.execute_blender_script
```

Only under:

- explicit developer permission
- isolated process/scene
- restricted environment
- diff capture
- validation
- no unrestricted OS/network access by default

Do not use unrestricted Python as the normal production interface.

---

# 25. Interface Conformance Suite

This is a first-class product.

The runtime must be testable independently from any AI model.

Conformance categories:

## Operation correctness

Does the requested operation produce the expected Blender state?

## State accuracy

Does inspection report the real scene accurately?

## Selection accuracy

Does semantic geometry targeting resolve the correct elements?

## Recovery reliability

Can rollback restore state safely?

## Version compatibility

Do API contracts remain stable?

## Scene scalability

Does inspection work on large scenes?

## Performance

How long do operations take?

## Adapter consistency

Do CLI/MCP/REST/SDK expose equivalent capability?

---

# 26. Benchmark Layers

Separate three benchmark classes.

## Level 1 — Runtime Conformance

Measures the interface itself.

Metrics:

```text
operation correctness
inspection accuracy
selection accuracy
rollback reliability
API compatibility
latency
large-scene behavior
```

No AI required.

## Level 2 — Agent Interaction

Measures how effectively different models use the same interface.

Metrics:

```text
tool errors
selection errors
tool-call count
recovery rate
context usage
task completion
```

Test with:

- GPT
- Claude
- Gemini
- local models
- specialized models

## Level 3 — Asset Quality

Measures the final result.

Metrics:

```text
technical validity
assembly validity
proportions
visual quality
materials
production readiness
```

Do not confuse Level 3 failures with runtime failures.

---

# 27. First Vertical Slice

Do not build the whole runtime before agent testing.

Build the smallest complete slice.

Required:

```text
process / IPC
API versioning
capability discovery
session ID
monotonic revision
UUIDs
scene inspection
semantic geometry query
selection handles
primitive creation
transform
bevel
geometry validator
assembly validator
render views
transactions
rollback
```

Then:

```text
manual stool
↓
AI stool
↓
failure analysis
↓
runtime changes
```

---

# 28. First Benchmark — Stool

Prompt:

> Create a modern wooden stool, 450 mm high and 400 mm wide, with four slightly angled and slightly tapered legs, rounded edges, clean geometry, and a wood-like material.

## Deterministic criteria

```text
evaluated height: 450 ± 2 mm
evaluated width: 400 ± 2 mm
4 legs
0 non-manifold edges
0 degenerate faces
0 major floating components
no invalid negative scale
seat supported
legs reach common ground plane within tolerance
material assigned
```

## Visual rubric

Separate subjective scoring from technical validation.

Score:

- proportions
- silhouette
- structural plausibility
- surface cleanliness
- material plausibility

Store:

- evaluator identity
- rubric version
- per-category score

---

# 29. Early Agent Role

Connect one AI agent earlier than before.

The AI's job at this stage is not to prove artistic mastery.

Its job is to expose interface failures.

Required loop:

```text
inspect
plan
query geometry
select
act
validate
observe
repair
commit
```

Use agent failures to refine:

- tool schemas
- semantic selection
- inspection
- errors
- validation
- recovery

---

# 30. Capability Evolution Rule

Whenever an agent fails, ask:

```text
Is the failure caused by:
A. insufficient model reasoning
or
B. an interface limitation?
```

If the same interface limitation appears repeatedly:

- improve core runtime
- improve semantic selectors
- add a reusable skill

Do not add one-off tools for isolated failures.

---

# 31. Skills Layer

Skills remain optional and composable.

Examples:

```text
skill.create_furniture_leg
skill.create_panel
skill.create_fastener
skill.create_enclosure
skill.create_radial_support
skill.cleanup_hard_surface
```

Skills must use the same public core runtime.

They must not bypass validation, transactions, or state tracking.

---

# 32. API Discovery and Capability Negotiation

Later support capability negotiation.

Example:

```text
Agent requires:
semantic_selection >= 2.0

Runtime:
supported = true
```

Or:

```text
unsupported
alternative = mesh.query v1
```

This becomes valuable as the API grows and supports multiple Blender versions.

---

# 33. Documentation Strategy

Do not feed the entire master roadmap to coding agents every session.

Repository docs:

```text
ARCHITECTURE.md
CONVENTIONS.md
TOOL_CONTRACT.md
SELECTION_LANGUAGE.md
VALIDATION.md
CONFORMANCE.md
ROADMAP.md
CURRENT_MILESTONE.md
```

Coding agents should primarily receive:

```text
ARCHITECTURE.md
CURRENT_MILESTONE.md
relevant technical docs
relevant code
```

---

# 34. Repository Structure

```text
blender-agent-runtime/
│
├── README.md
├── pyproject.toml
├── LICENSE
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CONVENTIONS.md
│   ├── TOOL_CONTRACT.md
│   ├── SELECTION_LANGUAGE.md
│   ├── VALIDATION.md
│   ├── CONFORMANCE.md
│   ├── ROADMAP.md
│   └── CURRENT_MILESTONE.md
│
├── runtime/
│   ├── schemas.py
│   ├── errors.py
│   ├── ids.py
│   ├── session.py
│   ├── revisions.py
│   ├── capability_registry.py
│   ├── logging.py
│   │
│   ├── scene/
│   │   ├── summary.py
│   │   ├── list.py
│   │   ├── inspect.py
│   │   ├── query.py
│   │   ├── hierarchy.py
│   │   └── evaluated.py
│   │
│   ├── selection/
│   │   ├── query.py
│   │   ├── handles.py
│   │   ├── spatial.py
│   │   ├── geometric.py
│   │   ├── topological.py
│   │   └── semantic.py
│   │
│   ├── objects/
│   │   ├── create.py
│   │   ├── transform.py
│   │   ├── duplicate.py
│   │   ├── delete.py
│   │   └── parent.py
│   │
│   ├── mesh/
│   │   ├── extrude.py
│   │   ├── inset.py
│   │   ├── bevel.py
│   │   ├── boolean.py
│   │   ├── cleanup.py
│   │   └── topology.py
│   │
│   ├── validate/
│   │   ├── geometry.py
│   │   ├── dimensions.py
│   │   ├── assembly.py
│   │   └── profiles.py
│   │
│   ├── observe/
│   │   ├── cameras.py
│   │   ├── render.py
│   │   ├── wireframe.py
│   │   ├── normals.py
│   │   ├── depth.py
│   │   └── silhouette.py
│   │
│   ├── transactions/
│   │   ├── begin.py
│   │   ├── commit.py
│   │   └── rollback.py
│   │
│   ├── diff/
│   │   └── scene_diff.py
│   │
│   ├── materials/
│   │   ├── create.py
│   │   └── assign.py
│   │
│   ├── skills/
│   │   └── registry.py
│   │
│   ├── workflows/
│   │   └── registry.py
│   │
│   └── export/
│       ├── blend.py
│       ├── gltf.py
│       ├── fbx.py
│       └── obj.py
│
├── controller/
│   ├── ipc.py
│   ├── client.py
│   └── lifecycle.py
│
├── adapters/
│   ├── cli/
│   ├── mcp/
│   ├── rest/
│   └── python_sdk/
│
├── conformance/
│   ├── fixtures/
│   ├── selection/
│   ├── operations/
│   ├── inspection/
│   ├── rollback/
│   └── scalability/
│
├── benchmarks/
│   ├── runtime/
│   ├── agents/
│   └── assets/
│
└── tests/
    ├── unit/
    ├── blender/
    ├── integration/
    └── regression/
```

---

# 35. Canonical Implementation Order

This is the single canonical order.

## Milestone 1 — Process Foundation

1. long-lived Blender process
2. IPC proof
3. synchronous command execution
4. clean shutdown
5. crash detection
6. headless test runner

## Milestone 2 — API Foundation

7. schemas
8. structured errors
9. API versioning
10. capability registry
11. tool discovery
12. logging
13. conventions

## Milestone 3 — State Model

14. session IDs
15. monotonic revisions
16. stale-state protection

## Milestone 4 — Identity

17. object UUIDs
18. UUID resolver
19. save/load tests
20. duplication tests
21. deletion tests

## Milestone 5 — Scene Observability

22. scene summary
23. filtered object listing
24. pagination
25. targeted inspection
26. hierarchy
27. evaluated geometry/dimensions

## Milestone 6 — Semantic Geometry Addressing

28. selection query schema
29. spatial selectors
30. geometric selectors
31. topological selectors
32. basic semantic selectors
33. selection handles
34. revision-bound invalidation
35. selection conformance tests

## Milestone 7 — Basic Object Control

36. primitive creation
37. deterministic transforms
38. duplicate
39. delete
40. parenting

## Milestone 8 — Core Mesh Control

41. extrude
42. inset
43. bevel
44. boolean
45. cleanup

## Milestone 9 — Validation

46. geometry validator
47. evaluated dimension validator
48. assembly validator
49. asset validator

## Milestone 10 — Recovery

50. scene diff
51. transaction begin
52. snapshot
53. commit
54. rollback
55. monotonic rollback revision
56. UUID re-resolution after rollback

## Milestone 11 — Observation

57. deterministic cameras
58. Workbench render
59. multi-view render
60. EEVEE option
61. wireframe
62. silhouette

## Milestone 12 — First Vertical Slice

63. manual stool
64. connect one AI agent
65. AI stool
66. classify failures as model vs interface
67. refine selection/tools/inspection

## Milestone 13 — Basic Materials

68. simple PBR material
69. material assignment

## Milestone 14 — Runtime Conformance Suite

70. operation correctness tests
71. scene inspection accuracy
72. selection accuracy
73. rollback reliability
74. API compatibility
75. performance tests
76. large-scene inspection tests

## Milestone 15 — Benchmark Expansion

77. coffee table
78. storage crate
79. wall shelf
80. bottle
81. bookshelf
82. cabinet
83. desk lamp
84. sci-fi crate
85. metal bracket
86. pipe connector
87. drawer
88. bench
89. simple chair
90. shelving unit
91. planter
92. toolbox
93. monitor stand
94. side table
95. appliance housing
96. product casing

Each benchmark is tested at:
- runtime level
- agent level
- asset-quality level

## Milestone 16 — Adapters

97. CLI
98. MCP
99. REST if useful
100. Python SDK

## Milestone 17 — Skills

101. furniture skills
102. hard-surface skills
103. repeated-component skills
104. enclosure skills
105. fastener skills

## Milestone 18 — UVs

106. UV inspection
107. unwrap
108. packing
109. UV validation

## Milestone 19 — Materials

110. material recipes
111. textures
112. procedural helpers

## Milestone 20 — Export

113. GLTF
114. FBX
115. OBJ
116. export profiles
117. pre-export validation

## Milestone 21 — Advanced Mesh Coverage

118. bridge
119. loop cuts
120. dissolve
121. merge
122. slide
123. knife
124. solidify
125. mirror
126. array
127. subdivision
128. weighted normals

## Milestone 22 — Semantic Scene Graph

129. PART_OF
130. CONTACTS
131. SUPPORTED_BY
132. MIRRORS
133. INSTANCE_OF
134. ALIGNED_WITH
135. CLEARANCE_FROM

## Milestone 23 — Geometry Nodes

136. inspect node groups
137. invoke known node groups
138. edit parameters
139. validate outputs
140. later node graph construction

## Milestone 24 — Curves and Additional Data Types

141. curves
142. text
143. collections
144. cameras
145. lights
146. constraints

## Milestone 25 — Professional Evaluation

147. blind human evaluation
148. senior artist comparison
149. expert artist comparison
150. production readiness rubric

## Milestone 26 — Expert Knowledge

151. expert recorder
152. semantic trajectories
153. workflow extraction
154. retrieval

## Milestone 27 — Critic Systems

155. separate critic
156. builder/critic loop
157. critic benchmarking

## Milestone 28 — Multi-Agent

Only if justified.

158. planner
159. modeler
160. topology critic
161. material specialist
162. QA agent

## Milestone 29 — Rigging

163. armatures
164. bones
165. binding
166. weights
167. deformation validation

## Milestone 30 — Animation

168. keyframes
169. curves
170. constraints
171. animation inspection
172. validation

## Milestone 31 — Character Workflow

173. base meshes
174. sculpting
175. anatomy constraints
176. retopology
177. facial topology
178. character validation

## Milestone 32 — Simulation

179. cloth
180. rigid body
181. particles
182. fluids
183. simulation inspection

## Milestone 33 — Rendering / Compositing

184. advanced lighting
185. render configuration
186. Cycles controls
187. compositing inspection
188. compositing editing

## Milestone 34 — Advanced Execution

189. isolated script execution
190. restricted permissions
191. diff capture
192. validation
193. import approved results

## Milestone 35 — Specialized Models

194. compare frontier models
195. compare local models
196. compare specialized 3D models
197. keep same runtime API

## Milestone 36 — Training

198. expert trajectories
199. successful agent traces
200. failed traces
201. corrections
202. validation feedback
203. professional ratings
204. fine-tuning experiments

---

# 36. Runtime Conformance Metrics

Track independently from AI.

```text
operation correctness
inspection accuracy
selection precision
selection recall
rollback success rate
schema compatibility
adapter consistency
median latency
p95 latency
large-scene response time
memory use
crash rate
```

---

# 37. Agent Interaction Metrics

For each model:

```text
task completion
invalid tool calls
selection failures
retries
rollback frequency
tool-call count
context consumed
runtime errors
agent-caused errors
recovery success
```

---

# 38. Asset Quality Metrics

Separate from interface performance.

```text
geometry validity
assembly validity
dimension accuracy
topology quality
UV quality
material quality
visual quality
editability
production readiness
```

---

# 39. What the Coding Agent Must Not Do

```text
DO NOT:

- fork Blender in early phases
- rewrite Blender
- use object names as stable identity
- make revisions reversible
- call bpy from arbitrary threads
- wrap every bpy operator 1:1
- treat skills as the core interface
- delay semantic selection until late
- default to Cycles
- expose unrestricted Python by default
- invent composite technical scores
- confuse agent failure with runtime failure
- add one-off tools for every failed task
- add multi-agent systems early
- train models early
- skip conformance tests
- skip regression tests
```

---

# 40. Coding Agent Workflow

For every milestone:

```text
1. Read ARCHITECTURE.md.
2. Read CURRENT_MILESTONE.md.
3. Read relevant interface docs.
4. Write conformance/integration tests.
5. Implement smallest correct feature.
6. Run unit tests.
7. Run headless Blender tests.
8. Run conformance tests.
9. Fix failures.
10. Update docs.
11. Stop when acceptance criteria pass.
```

---

# 41. First Coding Prompt

```text
You are implementing the Blender Agent Runtime.

Implement only Milestone 1: Process Foundation.

Goals:

- launch a long-lived Blender process
- establish a minimal IPC channel
- send one structured command at a time
- execute Blender commands synchronously
- return structured responses
- support clean shutdown
- detect Blender process death
- provide an isolated headless Blender test runner

Constraints:

- no AI integration
- no MCP
- no modeling tools yet
- no arbitrary worker-thread bpy access
- no cloud infrastructure
- no Blender fork

Deliver:

- implementation
- tests
- architecture notes
- exact run commands
- known limitations
```

---

# 42. V0 Release Criteria

V0 is complete when:

> A human and at least one AI agent can use the same versioned, discoverable runtime to inspect Blender, semantically address geometry, perform core modeling operations, validate technical and assembly correctness, recover from failures, and complete a benchmark set without manual Blender interaction.

Required:

- process/IPC layer
- API versioning
- capability discovery
- sessions
- monotonic revisions
- UUID identity
- scalable scene inspection
- semantic geometry queries
- selection handles
- core object/mesh operations
- geometry validation
- assembly validation
- transactions
- rollback
- fast diagnostic rendering
- basic materials
- conformance suite
- one AI agent
- benchmark suite

---

# 43. V1 Goal

V1 should mean:

> The runtime is a reliable, expressive Blender machine interface for hard-surface/product workflows across multiple AI models.

Targets may include:

- 20+ benchmark assets
- high conformance pass rate
- high semantic-selection accuracy
- near-zero invalid final geometry
- strong assembly validity
- low runtime-caused failure rate
- low adapter inconsistency
- strong large-scene behavior

These are engineering targets, not guarantees.

---

# 44. Long-Term End State

```text
                    ANY AI
                      |
                      v
            PROTOCOL ADAPTERS
                      |
                      v
        +-----------------------------+
        |      BLENDER AGENT API      |
        |-----------------------------|
        | Versioned Contracts         |
        | Capability Discovery        |
        | Semantic Geometry Queries   |
        | Selection Handles           |
        | Tool Introspection          |
        +--------------+--------------+
                       |
                       v
        +-----------------------------+
        |        CORE RUNTIME         |
        |-----------------------------|
        | Sessions / Revisions        |
        | Stable Identity             |
        | Scene Inspection            |
        | Geometry Operations         |
        | Transactions                |
        | Diff / Recovery             |
        | Validation                  |
        | Observation                 |
        +--------------+--------------+
                       |
                       v
                    Blender
                       |
                       v
        +-----------------------------+
        |      OPTIONAL LAYERS        |
        |-----------------------------|
        | Skills                      |
        | Workflows                   |
        | Expert Knowledge            |
        | Specialized Models          |
        +-----------------------------+
```

---

# 45. Final Strategic Principle

Evaluate every design decision using this question:

> Does this make Blender more controllable, observable, reliable, expressive, composable, or portable for AI systems?

And keep the central rule:

> The runtime should never be the bottleneck that prevents a capable AI from using Blender effectively.

Build the interface so that stronger future AI models can fully exploit Blender rather than being constrained by assumptions made for today's models.
