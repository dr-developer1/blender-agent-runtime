# Architecture

The external controller owns one long-lived, isolated headless Blender subprocess.
Blender connects to an ephemeral loopback TCP listener using a random launch token.
A bounded newline-delimited JSON protocol carries one request and one response at a
time. A controller lock serializes callers; the Blender Python entrypoint executes
all commands on its main thread. No worker thread accesses bpy.

Milestone 1 exposes only `process.ping` and `process.shutdown`. The transport is
private scaffolding, not the versioned public tool API (Milestone 2). No script
execution or modeling operation is available over IPC.

The controller owns process lifetime, deadlines, log capture and cleanup. A timeout
or broken protocol poisons the connection and terminates the child: an uncertain
command is never automatically retried. A separate headless runner launches a fresh
factory-startup Blender for each local test script.

The current executor runs in background mode. Interactive UI integration will need
a main-thread timer/queue executor; the blocking loop must not run inside a GUI.
