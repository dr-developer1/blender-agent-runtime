# Architecture

The external controller owns one long-lived, isolated headless Blender subprocess.
Blender connects to an ephemeral loopback TCP listener using a random launch token.
A bounded newline-delimited JSON protocol carries one request and one response at a
time. A controller lock serializes callers; the Blender Python entrypoint executes
all commands on its main thread. No worker thread accesses bpy.

Milestone 1 lifecycle commands `process.ping` and `process.shutdown` remain private
scaffolding. Milestone 2 adds a public API 1.0 envelope (`api_version`, `tool`,
`arguments`) and seven read-only discovery tools, invoked with `client.call()`.
Both envelope types carry a private correlation ID over the same serialized channel.
No script execution or modeling operation is available over IPC.

The Blender-independent API dispatcher validates the request, resolves a tool in
one capability registry, validates its arguments and returns a typed success/error
response. Discovery uses the same registry and reports only available tools. Every
public call emits structured metadata without arguments or results. Internal errors
are redacted. The controller validates public responses before returning them.
Session/revision fields are reserved for Milestone 3, rather than simulated now.

The controller owns process lifetime, deadlines, log capture and cleanup. A timeout
or broken protocol poisons the connection and terminates the child: an uncertain
command is never automatically retried. A separate headless runner launches a fresh
factory-startup Blender for each local test script.

The current executor runs in background mode. Interactive UI integration will need
a main-thread timer/queue executor; the blocking loop must not run inside a GUI.
