# Current milestone

Milestone 1 — Process Foundation (steps 1–6): complete.

Implemented: persistent headless Blender process; private structured IPC;
serialized synchronous execution on Blender's main thread; clean shutdown;
process-death and timeout detection; isolated headless script runner.

Verified on Linux with Python 3.12.3 and Blender 5.2.2 LTS. Five transport unit
tests and ten real-process acceptance tests cover persistence, concurrent callers,
main-thread execution, invalid requests/arguments, recovery after command rejection,
shutdown, crashes, early exit, missing executable and timeout cleanup. The headless
runner verifies factory scene startup and propagates script failure/timeout.
The conformance entrypoint reuses these process acceptance tests.

Next: Milestone 2 — schemas, structured errors, API versioning, capability registry,
tool discovery, logging and conventions. The current IPC envelope is private;
Milestone 2 will introduce the public tool contract from the canonical plan.
Session IDs and scene revisions follow in Milestone 3. Do not add modeling tools,
AI integration or adapters ahead of their canonical milestones.
