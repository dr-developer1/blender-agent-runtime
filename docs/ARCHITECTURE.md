# Architecture

The external controller owns one long-lived, isolated headless Blender subprocess.
Blender connects to an ephemeral loopback TCP listener using a random launch token.
A bounded newline-delimited JSON protocol carries one request and one response at a
time. A controller lock serializes callers; the Blender Python entrypoint executes
all commands on its main thread. No worker thread accesses bpy.

Milestone 1 lifecycle commands `process.ping` and `process.shutdown` remain private
scaffolding. Milestone 2 adds a public API 1.0 envelope (`api_version`, `session_id`, `expected_revision`, `tool`,
`arguments`) and seven read-only discovery tools, invoked with `client.call()`.
Both envelope types carry a private correlation ID over the same serialized channel.
No script execution is available over IPC.

The Blender-independent API dispatcher validates the request, resolves a tool in
one capability registry, validates its arguments and returns a typed success/error
response. Discovery uses the same registry and reports only available tools. Every
public call emits structured metadata without arguments or results. Internal errors
are redacted. The controller validates public responses before returning them.
Milestone 3 gives each API instance a fresh session UUID and an independent monotonic
revision counter. The startup handshake supplies initial state to the controller.
The dispatcher lock covers state validation and execution; state preconditions
apply to reads and mutations alike. Validated tools with declared side effects
advance the timeline before execution, including failed attempts. Scene snapshots
must never include the counter. The controller tracks returned revisions and
rejects different-session or backward-state responses. Public object tools declare mutations; test fixtures also exercise scene restoration.

Milestone 4 attaches a persistent `bar_uuid` custom property to every object in
Blender data during startup, preserving valid existing IDs. The optional live
object provider keeps the API testable without importing bpy. Identity resolution
rescans current data instead of retaining references across deletion or file loads.
Known duplicates receive fresh IDs; ambiguous collisions are rejected. Identity
writes after bootstrap belong inside mutation handlers, while the initial IDs form
the revision-zero baseline. See IDENTITY.md for the internal service contract.

Milestone 5 attaches live scene and view-layer providers. Scene observations reuse
the identity index without storing long-lived object references. Listing filters
current observations and emits bounded pages sorted by UUID. Signed cursors bind
the query, session, revision and observation digest, detecting stale timelines and
changed matching data between pages. No server-side cursor cache is retained.
Nested schemas validate filters and page bounds before execution. Oversized results
return structured errors instead of overflowing the transport. Computation still
scans scene data for each page. Targeted UUID inspection reads the evaluated
dependency graph and reports base/evaluated mesh counts plus world-space bounds.
Hierarchy pages expose parent UUID edges without unbounded child arrays; see SCENE_OBSERVABILITY.md for current limits.

The controller owns process lifetime, deadlines, log capture and cleanup. A timeout
or broken protocol poisons the connection and terminates the child: an uncertain
command is never automatically retried. A separate headless runner launches a fresh
factory-startup Blender for each local test script.

The current executor runs in background mode. Interactive UI integration will need
a main-thread timer/queue executor; the blocking loop must not run inside a GUI.

Milestone 6 registers `mesh.query` and `mesh.inspect_selection` when scene providers
are present. A plain numeric base-mesh snapshot supports deterministic selector
intersection. A bounded runtime-local handle store retains only UUIDs, revision,
indices and geometry fingerprints, never live Blender references. Resolution
reacquires the object and rejects changed geometry/transform. Revision changes clear
the store lazily before its next use. Queries are read-only scene operations even
though they create temporary addressing metadata. See SELECTION_LANGUAGE.md.

Milestone 7 explicitly enables a Blender object-control backend on the server.
Five object tools use direct datablock construction and edits, with no operator
context or UI selection dependency. Plain in-process API instances keep this
backend disabled unless requested. MutationResult carries object changes into the
response envelope while the registry still validates schemas and advances the
revision before execution. Copying repairs UUID identity before publishing the
result; deletion re-resolves children and preserves their world poses. Parenting
preflights cycles, singular transforms and shear. General rollback and transaction diffs are supplied by the
Milestone 10 recovery service described below. See OBJECT_CONTROL.md.


Milestone 8 enables a mesh-control backend alongside object control. Registry
entries can provide read-only preparation under the existing dispatcher lock;
selection handles resolve at the observed revision, then every validated mutation
attempt advances once even if preparation rejects. Extrude/inset/bevel/cleanup
work on detached BMesh data and publish an independent mesh after output checks.
Booleans bake an EXACT modifier on a temporary object with finally cleanup.
Linked duplicates keep their original data. No UI operator context is required.
The tools retain object identity and report the modified target UUID; broader
transaction recovery is provided by Milestone 10. See MESH_CONTROL.md.

Milestone 9 registers four read-only validation tools when evaluated observation
providers exist, independently of the mutation backend. Bounded numeric snapshots
feed geometry checks and evaluated world AABB dimension/relationship checks.
Asset validation composes their findings and optional face material assignment.
Reports contain concrete pass/fail checks with no score, inside the ordinary
result envelope. No datablock publication, UUID repair, UI operator or revision
advance occurs. See VALIDATION.md for approximate assembly semantics and limits.


Milestone 10 enables a RecoveryService with object control and evaluated providers.
Begin captures bounded plain UUID-keyed records and saves a private full-file copy;
no live datablock references are retained. One checkpoint is active per runtime.
Diff compares observations, base geometry fingerprints and writable modifier
settings; commit reports accumulated changes and discards the file. Rollback
checks its checksum, attempts a reverse diff, reloads with embedded scripts disabled
and reacquires UUIDs. Invalid current observations cannot strand a valid checkpoint.
Scene restoration never touches RuntimeState. All transaction controls declare
side effects, so successful and rejected attempts advance revisions and invalidate
handles/cursors. Relative external resources become absolute after reload; Blender's
read-only filepath remains the checkpoint name. The controller owns the temporary
root, ensuring cleanup even after child death. Server disconnect/shutdown runs API
cleanup in finally. See RECOVERY.md for restore versus diff scope and limits.


Milestone 11 explicitly enables ObservationService with live evaluated providers.
Pure camera math fits world AABB corners for canonical orthographic and perspective
views. Rendering copies bounded evaluated meshes into an isolated temporary scene,
uses a private camera/world/light rig and returns PNG base64 within the existing
frame budget. Wireframe builds curves from evaluated edges; silhouette uses flat
black geometry. Finally cleanup removes all owned datablocks and temporary files.
The source scene, revisions, cursors and selection handles are preserved. Only the
native global Render Result is replaceable. See OBSERVATION.md for mesh/evaluation
scope and backend limitations.

Milestone 12 adds public-API exercises under benchmarks rather than extending the
runtime tool set. The manual stool drives BlenderClient directly; the local
JSON-line bridge lets one external AI agent inspect/discover/model through the
same client. The harness owns a transaction, evaluates explicit seat/leg UUIDs,
saves diagnostic PNGs and commits supported technical results or rolls back.
Disconnect and command-budget exhaustion restore the checkpoint. Structured tool
rejections remain visible for repair; lifecycle/transport failures terminate the
exercise. Reports distinguish supported technical results, confirmed interface
gaps and unverified visual criteria. See STOOL_BENCHMARK.md for actual Codex evidence.


Milestone 13 enables MaterialControl alongside object control. Two general tools
create opaque Principled PBR materials and assign them to an entire mesh. Material
UUIDs are persistent custom properties and resolved afresh across checkpoint
reloads. Assignment stages a detached mesh and publishes a single DATA slot,
preserving linked users and restoring slots/data on failure. Full-file recovery
includes material datablocks; object diffs now hash base face assignments and slots.
The stool baseline creates a brown PBR material and can render with EEVEE for
material assessment. See MATERIALS.md for exact scope and limitations.

Milestone 14 makes real-Blender conformance a reportable acceptance gate. The
repository runner reuses the integration fixtures and adds fixed API descriptor
compatibility, warm IPC latency, large-scene ground-truth inspection and repeated
full-file recovery cases. Reports keep individual outcomes and timings, and skips
cannot produce a passing acceptance result. The compatibility baseline is static
and reviewed separately from measured evidence. No public tools are added; see
CONFORMANCE.md for coverage, budgets and supported environment limits.
