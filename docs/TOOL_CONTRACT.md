# Tool contract — API 1.0 foundation

Public requests contain exactly `api_version` (string), `tool` (nonempty string),
and `arguments` (object). The private IPC envelope also adds `id` for correlation.
Call `client.call(tool, arguments, api_version="1.0")` to use this API.

Success contains `success: true`, `api_version: "1.0"`, `result` (object),
`created_ids`, `modified_ids`, `deleted_ids`, `warnings` (arrays), `metrics`
(object with `duration_ms`), and `validation` (currently null). Failure contains
`success: false`, `api_version: "1.0"` and an `error` with `code`, `message`,
`details`. IPC responses also contain `id`. Unsupported-version failures report
the runtime response version and list supported versions in error details.

This milestone exposes only read-only discovery. Session IDs, expected revisions
and revision response fields are introduced in Milestone 3; they are deliberately
absent now. The foundation contract must not be used for scene mutations.

Validation rejects missing/extra envelope and argument fields, wrong types and
unsupported API versions before executing a tool. All discovery tools take `{}`
except `runtime.describe_tool`, which requires a nonempty string `name`.
Tool descriptors expose input/output JSON schemas, version, side effects,
supports and transaction safety. The current argument validator supports object
schemas with required string properties and no additional properties.

Errors: `INVALID_REQUEST`, `UNSUPPORTED_API_VERSION`, `UNKNOWN_TOOL`,
`INVALID_ARGUMENT`, `INTERNAL_ERROR`. Internal exception text is not returned.
Transport errors remain `BlenderProcessError` and terminate the connection.

`client.request` and `process.*` remain private Milestone 1 lifecycle scaffolding.
They are not advertised as public tools. Use `close()` for shutdown.

One JSON log event is emitted per public call with request ID, tool name,
API version, outcome, error code and duration. Arguments, results, credentials
and exception text are excluded. Logs share the captured Blender output stream.
