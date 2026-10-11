# Current milestone

Milestone 2 — API Foundation (steps 7–13): complete.

Implemented: typed request/response contracts; strict argument schemas; structured
errors; API 1.0 version validation; a shared capability registry; seven read-only
discovery tools; JSON call metadata logging; documented axes, units, angles,
rotation order and evaluated dimension conventions. The controller exposes public
calls via `client.call()` while retaining private lifecycle `request()`/`close()`.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 17 unit tests, 11
integration tests, 11 conformance checks reusing the integration suite, and an
isolated headless API smoke check. Includes all Milestone 1 lifecycle regressions.
Exact commands are in README.md. Tool contracts are in TOOL_CONTRACT.md.

Limits: read-only discovery; schema validator currently handles only the object/
string argument subset used by discovery. Public envelopes intentionally omit
session and revision fields until the next milestone. No modeling tools, recovery,
AI integration or adapters have been added.

Next: Milestone 3 — State Model (steps 14–16): session IDs, monotonic revisions,
and stale-state protection. Extend the API 1.0 foundation to the planned state
contract before adding identity or scene operations.
