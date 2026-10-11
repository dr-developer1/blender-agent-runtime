# Blender Agent Runtime

A model-independent machine interface to Blender, implemented incrementally from
[the canonical plan](BLENDER_AGENT_RUNTIME_CANONICAL_MASTER_PLAN_V2.md).

Milestones 1–4 provide a persistent headless Blender process, synchronous structured
IPC, shutdown/death detection, isolated headless testing, and a versioned, typed
read-only discovery API with structured errors, call logging, session IDs and
monotonic revision preconditions. Objects receive persistent UUIDs with collision
detection and resolution. No modeling tools yet.
Requires Python 3.10+ and a Blender executable on PATH. No Python dependencies are
needed to run the controller or tests.

From the repository root:

```bash
python3 -m unittest discover -s tests/unit -v
python3 -m unittest discover -s tests/integration -v
python3 -m unittest discover -s conformance -v
python3 -m controller.headless tests/blender/smoke.py
python3 -m controller.headless tests/blender/api_smoke.py
python3 -m controller.headless tests/blender/state_smoke.py
python3 -m controller.headless tests/blender/identity_smoke.py
```

Choose a different Blender for integration/conformance tests with
`BLENDER_EXECUTABLE=/absolute/path/to/blender`. The headless runner accepts
`--blender /absolute/path/to/blender` and `--timeout 60`.

Try the persistent process:

```python
from controller.client import BlenderClient

with BlenderClient(executable="blender") as client:
    print(client.request("process.ping"))
    print(client.request("process.ping"))  # same PID, next execution sequence
    print(client.session_id, client.revision)  # initialized by startup handshake
    print(client.call("runtime.get_version"))
    print(client.call("runtime.list_tools"))
    print(client.call("runtime.describe_tool", {"name": "runtime.get_limits"}))
```

`close()` requests shutdown, waits for process exit, and cleans temporary resources.
Lifecycle failures raise `BlenderProcessError`; rejected commands return structured
error responses. Captured Blender output is available as `client.log_output` after
cleanup. After a timeout or protocol failure the client terminates Blender and
becomes unusable; create a new client to restart. Commands are never retried.

See [architecture](docs/ARCHITECTURE.md), [current milestone](docs/CURRENT_MILESTONE.md),
[tool contract](docs/TOOL_CONTRACT.md), [conventions](docs/CONVENTIONS.md),
[object identity](docs/IDENTITY.md), and [conformance](docs/CONFORMANCE.md).

Limitations: background mode only; local single-controller TCP transport; no scene
recovery or transactions yet. API 1.0 is limited to read-only discovery.
State preconditions guard every public call; mutation and restore hooks are tested
with private fixtures. Identity helpers are internal; scene listing follows in
Milestone 5. External scene edits are not automatically tracked.
Loopback and a launch token restrict accidental attachment; this is not a sandbox
against other processes running as the same user. Headless test scripts are trusted
local code. Integration tests skip if Blender is unavailable. A hung process is
terminated after its deadline, so graceful shutdown is not guaranteed in that case.

Available public tools: `runtime.get_version`, `runtime.get_supported_versions`,
`runtime.list_tools`, `runtime.describe_tool`, `runtime.describe_capabilities`,
`runtime.get_supported_features`, and `runtime.get_limits`. Tool schemas and
metadata are returned by discovery. Only `runtime.describe_tool` takes an argument
(`name`); the other tools take an empty object. Unsupported API versions and bad
arguments return structured failures while keeping the process usable.
