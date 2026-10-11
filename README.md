# Blender Agent Runtime

A model-independent machine interface to Blender, implemented incrementally from
[the canonical plan](BLENDER_AGENT_RUNTIME_CANONICAL_MASTER_PLAN_V2.md).

Milestones 1–11 provide a persistent headless Blender process, synchronous structured
IPC, shutdown/death detection, isolated headless testing, and a versioned, typed
discovery API with structured errors, call logging, session IDs and
monotonic revision preconditions. Objects receive persistent UUIDs with collision
detection and resolution. Scene summaries and filtered object pages provide
read-only observation. Targeted inspection reports evaluated geometry and world
bounds; hierarchy pages expose parent UUIDs. Semantic base-mesh queries create temporary
revision-bound selection handles. Basic object tools create primitives, set transforms,
duplicate, delete and parent by UUID with revision and change tracking. Core mesh
tools extrude, inset, bevel, boolean and clean up base geometry. Read-only validators
report geometry defects, evaluated dimension mismatches, approximate assembly
relationships and asset checks. Single transactions save private full-file checkpoints,
report scene diffs, and commit or roll back with monotonic revisions. Diagnostic
observation adds deterministic fitted cameras and isolated Workbench/EEVEE PNG
renders, including multi-view, wireframe and silhouette modes.
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
python3 -m controller.headless tests/blender/object_smoke.py
python3 -m controller.headless tests/blender/mesh_smoke.py
python3 -m controller.headless tests/blender/validation_smoke.py
python3 -m controller.headless tests/blender/recovery_smoke.py
python3 -m controller.headless tests/blender/observation_smoke.py --timeout 90
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
[semantic selection](docs/SELECTION_LANGUAGE.md), [object control](docs/OBJECT_CONTROL.md), [mesh control](docs/MESH_CONTROL.md), [validation](docs/VALIDATION.md), [recovery](docs/RECOVERY.md), [diagnostic observation](docs/OBSERVATION.md), and [conformance](docs/CONFORMANCE.md).

Limitations: background mode only; local single-controller TCP transport; single active transaction; full-file rollback
changes Blender’s current filepath to its private checkpoint name. API 1.0 provides discovery, scene reads, semantic base-mesh queries, basic object control, core mesh edits, technical validation, recovery and diagnostic renders.
State preconditions guard every public call; public object mutations report UUID changes; transaction diffs summarize tracked fields and rollback restores saved contents. Identity writes remain internal; observations do not
initialize new IDs. External scene edits are not automatically tracked.
Loopback and a launch token restrict accidental attachment; this is not a sandbox
against other processes running as the same user. Headless test scripts are trusted
local code. Integration tests skip if Blender is unavailable. A hung process is
terminated after its deadline, so graceful shutdown is not guaranteed in that case.

Available public tools: `runtime.get_version`, `runtime.get_supported_versions`,
`runtime.list_tools`, `runtime.describe_tool`, `runtime.describe_capabilities`,
`runtime.get_supported_features`, `runtime.get_limits`, `scene.summary`,
`scene.list_objects`, `scene.get_hierarchy`, `scene.inspect_objects`, `mesh.query`,
`mesh.inspect_selection`, `object.create_primitive`, `object.transform`,
`object.duplicate`, `object.delete`, `object.set_parent`, `mesh.extrude`, `mesh.inset`,
`mesh.bevel`, `mesh.boolean`, `mesh.cleanup`, `validate.geometry`, `validate.dimensions`, `validate.assembly`,
`validate.asset`, `scene.diff`, `transaction.begin`, `transaction.commit`,
`transaction.rollback`, `observe.camera`, `observe.render`, and
`observe.render_multiview`. Tool schemas and
metadata are returned by discovery. `runtime.describe_tool` takes `name`;
`scene.list_objects` takes filters, `limit` and `cursor`; `scene.get_hierarchy`
takes `limit` and `cursor`; `scene.inspect_objects` takes `object_ids`. Discovery and summary tools without arguments
take `{}`. Unsupported API versions and bad
arguments return structured failures while keeping the process usable.

`mesh.query` takes `object_id`, `element_type`, `selectors` and optional `space`;
`mesh.inspect_selection` takes `selection_handle`. See the selection language doc
for supported kinds, base/evaluated geometry distinctions, limits and invalidation.

Create and position a 450 mm cube:

```python
with BlenderClient() as client:
    created = client.call("object.create_primitive", {"primitive": "CUBE", "size": 450, "unit": "mm"})
    if created["success"]:
        object_id = created["result"]["object_id"]
        print(client.call("object.transform", {"object_id": object_id, "location": [0, 0, 225], "unit": "mm"}))
```

See the object control contract for exact units, parent-local transforms, copy
semantics, child preservation on delete and supported object states.

Extrude the cube's top by 50 mm in object-local +Z:

```python
selection = client.call("mesh.query", {
    "object_id": object_id, "element_type": "FACE", "selectors": [{"kind": "top"}],
})
if selection["success"]:
    print(client.call("mesh.extrude", {
        "selection_handle": selection["result"]["selection_handle"],
        "offset": [0, 0, 50], "unit": "mm",
    }))
```

Mesh edits replace the target's data independently of linked duplicates. Query a
new handle for each edit. See the mesh control contract for local units, supported
object states, native geometry semantics and current repair limitations.

Render the six diagnostic views (384 × 384 Workbench by default):

```python
import base64
from pathlib import Path

with BlenderClient(request_timeout=60) as client:
    response = client.call("observe.render_multiview")
    if response["success"]:
        for image in response["result"]["images"]:
            Path(image["camera"]["view"] + ".png").write_bytes(
                base64.b64decode(image["png_base64"]))
```

Single-view `observe.render` accepts `view`, `mode` and `engine`; `observe.camera`
returns the same framing metadata without rendering. See the observation contract
for target visibility, evaluated mesh scope, image budgets, EEVEE lighting and
resource cleanup. These calls preserve revisions and source scene settings.
