# Blender Agent Runtime

A model-independent machine interface to Blender, implemented incrementally from
[the canonical plan](BLENDER_AGENT_RUNTIME_CANONICAL_MASTER_PLAN_V2.md).

Milestone 1 provides a persistent headless Blender process, synchronous structured
IPC, shutdown/death detection, and isolated headless testing. No modeling tools yet.
Requires Python 3.10+ and a Blender executable on PATH. No Python dependencies are
needed to run the controller or tests.

From the repository root:

```bash
python3 -m unittest discover -s tests/unit -v
python3 -m unittest discover -s tests/integration -v
python3 -m unittest discover -s conformance -v
python3 -m controller.headless tests/blender/smoke.py
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
```

`close()` requests shutdown, waits for process exit, and cleans temporary resources.
Lifecycle failures raise `BlenderProcessError`; rejected commands return structured
error responses. Captured Blender output is available as `client.log_output` after
cleanup. After a timeout or protocol failure the client terminates Blender and
becomes unusable; create a new client to restart. Commands are never retried.

See [architecture](docs/ARCHITECTURE.md), [current milestone](docs/CURRENT_MILESTONE.md)
and [conformance](docs/CONFORMANCE.md).

Limitations: background mode only; local single-controller TCP transport; no scene
recovery, public API versioning, revisions, object IDs or capability discovery yet.
Loopback and a launch token restrict accidental attachment; this is not a sandbox
against other processes running as the same user. Headless test scripts are trusted
local code. Integration tests skip if Blender is unavailable. A hung process is
terminated after its deadline, so graceful shutdown is not guaranteed in that case.
