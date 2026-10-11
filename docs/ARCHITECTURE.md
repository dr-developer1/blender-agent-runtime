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
No script execution or modeling operation is available over IPC.

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
rejects different-session or backward-state responses. Public tools remain read-only; test fixtures exercise real edits and scene restoration.

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
