# Tool contract — API 1.0 state model

Public requests contain exactly `api_version` (string), `session_id` (nonempty
string), `expected_revision` (nonnegative integer, excluding booleans), `tool`
(nonempty string), and `arguments` (object). IPC adds `id` for correlation.
The authenticated startup handshake provides the initial session ID and revision.
Direct in-process callers obtain these from `api.state`.

`client.call(tool, arguments, api_version="1.0")` supplies the client's current
session and revision automatically. Optional `session_id` and `expected_revision`
keywords let callers submit a precondition captured with earlier observations.
For edits based on stored observations, explicitly supply that observed revision.
The client tracks revisions from successful and rejected responses, but never
retries rejected requests. A stale rejection is not permission to repeat an edit:
refresh observations before deciding what to do next.

Success contains `success: true`, `api_version: "1.0"`, `session_id`,
`revision_before`, `revision_after`, `result` (object), `created_ids`, `modified_ids`,
`deleted_ids`, `warnings` (arrays), `metrics` (object with `duration_ms`), and
`validation` (currently null). Failure contains `success: false`, `api_version`,
`session_id`, `revision` (current timeline), and `error` with `code`, `message`,
`details`. IPC responses also contain `id`. Unsupported-version failures report
the runtime response version and supported versions in error details.

Every runtime starts with a fresh UUID session and revision zero. All public
calls, including reads, reject a different session with `SESSION_MISMATCH` or a
revision mismatch with `STALE_SCENE_STATE` before tool execution. Stale errors
report expected and current revisions. Session checking precedes revision checking.
The controller rejects responses from another session or a backward timeline.

Reads leave the revision unchanged. The dispatcher serializes state checks and
execution. After argument validation, any tool declaring side effects advances
once immediately before its handler starts. Failed mutation attempts also consume
a revision because they may have partially changed the scene. Invalid arguments,
unknown tools and rejected preconditions do not advance. Future restore/rollback
tools must declare side effects; snapshots restore scene contents, never the
runtime counter. This milestone adds the hooks and verifies them with private
test fixtures; the seven production tools remain read-only discovery. Arbitrary
external bpy edits are not automatically observed by this background runtime.

Validation rejects missing/extra envelope and argument fields, wrong types and
unsupported API versions before executing a tool. Discovery tools take `{}` except
`runtime.describe_tool`, which requires a nonempty string `name`. Descriptors expose
input/output JSON schemas, version, side effects, supports and transaction safety.
The argument validator supports object schemas with required string properties
and no additional properties.

Errors: `INVALID_REQUEST`, `UNSUPPORTED_API_VERSION`, `SESSION_MISMATCH`,
`STALE_SCENE_STATE`, `UNKNOWN_TOOL`, `INVALID_ARGUMENT`, `INTERNAL_ERROR`.
Internal exception text is not returned. Transport errors remain
`BlenderProcessError` and terminate the connection.

`client.request` and `process.*` remain private lifecycle scaffolding without state
preconditions. They are not advertised as public tools. Use `close()` for shutdown.
One JSON log event is emitted per public call with request ID, tool name, API
version, outcome, error code and duration. Arguments, results, credentials and
exception text are excluded. Logs share the captured Blender output stream.

Milestone 4 advertises `object_identity: true` when a live object provider is
attached (including the Blender server). UUID initialization precedes publication
of revision zero. The seven public tools remain discovery only; identity helpers
and their errors are documented in IDENTITY.md for subsequent scene tools.
