# Blender Agent Runtime

A model-independent machine interface to Blender, implemented incrementally from
[the canonical plan](BLENDER_AGENT_RUNTIME_CANONICAL_MASTER_PLAN_V2.md).

Milestones 1–6 provide a persistent headless Blender process, synchronous structured
IPC, shutdown/death detection, isolated headless testing, and a versioned, typed
read-only discovery API with structured errors, call logging, session IDs and
monotonic revision preconditions. Objects receive persistent UUIDs with collision
detection and resolution. Scene summaries and filtered object pages provide
read-only observation. Targeted inspection reports evaluated geometry and world
bounds; hierarchy pages expose parent UUIDs. Semantic base-mesh queries create temporary
revision-bound selection handles. No modeling tools yet.
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
python3 -m controller.headless tests/blender/scene_smoke.py
python3 -m controller.headless tests/blender/geometry_smoke.py
python3 -m controller.headless tests/blender/selection_smoke.py
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
    print(client.call("scene.summary"))
    print(client.call("scene.list_objects", {"object_type": "MESH", "limit": 25}))
    print(client.call("runtime.describe_tool", {"name": "runtime.get_limits"}))
```

`close()` requests shutdown, waits for process exit, and cleans temporary resources.
Lifecycle failures raise `BlenderProcessError`; rejected commands return structured
error responses. Captured Blender output is available as `client.log_output` after
cleanup. After a timeout or protocol failure the client terminates Blender and
becomes unusable; create a new client to restart. Commands are never retried.

See [architecture](docs/ARCHITECTURE.md), [current milestone](docs/CURRENT_MILESTONE.md),
[tool contract](docs/TOOL_CONTRACT.md), [conventions](docs/CONVENTIONS.md),
[object identity](docs/IDENTITY.md), [scene observation](docs/SCENE_OBSERVABILITY.md),
[semantic selection](docs/SELECTION_LANGUAGE.md), and [conformance](docs/CONFORMANCE.md).

Limitations: background mode only; local single-controller TCP transport; no scene
recovery or transactions yet. API 1.0 provides discovery, scene reads and semantic base-mesh queries.
State preconditions guard every public call; mutation and restore hooks are tested
with private fixtures. Identity writes remain internal; observations do not
initialize new IDs. External scene edits are not automatically tracked.
Loopback and a launch token restrict accidental attachment; this is not a sandbox
against other processes running as the same user. Headless test scripts are trusted
local code. Integration tests skip if Blender is unavailable. A hung process is
terminated after its deadline, so graceful shutdown is not guaranteed in that case.

Available public tools: `runtime.get_version`, `runtime.get_supported_versions`,
`runtime.list_tools`, `runtime.describe_tool`, `runtime.describe_capabilities`,
`runtime.get_supported_features`, `runtime.get_limits`, `scene.summary`,
`scene.list_objects`, `scene.get_hierarchy`, `scene.inspect_objects`, `mesh.query`,
and `mesh.inspect_selection`. Tool schemas and
metadata are returned by discovery. `runtime.describe_tool` takes `name`;
`scene.list_objects` takes filters, `limit` and `cursor`; `scene.get_hierarchy`
takes `limit` and `cursor`; `scene.inspect_objects` takes `object_ids`. Discovery and summary tools without arguments
take `{}`. Unsupported API versions and bad
arguments return structured failures while keeping the process usable.

`mesh.query` takes `object_id`, `element_type`, `selectors` and optional `space`;
`mesh.inspect_selection` takes `selection_handle`. See the selection language doc
for supported kinds, base/evaluated geometry distinctions, limits and invalidation.
