# Recovery — API 1.0

Milestone 10 adds `scene.diff`, `transaction.begin`, `transaction.commit` and
`transaction.rollback`. The server advertises 31 tools and package version
0.10.0. Recovery is available when object control and evaluated scene providers
are enabled. Discovery reports `transactions`, `scene_diff`, and recovery limits.
Object and mesh tools advertise transaction support and safety when this backend
is attached: their scene changes can be restored by the checkpoint. They remain
usable outside transactions. No mutation automatically begins or rolls back one.

## Lifecycle and state

`transaction.begin` takes `{}`. It checks Object mode, managed identities,
bounded active-scene measurements and saves a private full-file `.blend` copy.
A successful call returns:

```json
{"transaction_id": "<runtime-generated UUID>", "baseline_revision": 1}
```

The snapshot is created automatically during begin; there is no separate snapshot
endpoint or caller-supplied path. Only one transaction may be active. Nested begin
returns `TRANSACTION_ACTIVE`. IDs are scoped to the current checkpoint/session and
cannot be used after commit, rollback, restart or a later begin.

Begin, commit and rollback declare side effects and advance once before execution,
including schema-valid rejected attempts. This follows the existing conservative
mutation rule and expires selection handles. `baseline_revision` is the revision
at successful begin, after that advance. Reads such as `scene.diff` and validation
leave the revision unchanged. All tools require the current session and revision;
stale requests, unknown tools and argument-schema rejection consume no revision.
Failed edits do not close a transaction. Commit does not validate automatically;
run the validators and decide whether to keep or restore changes.

`scene.diff`, `transaction.commit` and `transaction.rollback` require:

```json
{"transaction_id": "<ID returned by begin>"}
```

No active checkpoint returns `NO_ACTIVE_TRANSACTION`; a wrong/expired ID while
another transaction is active returns `INVALID_TRANSACTION`. IDs are opaque to
callers. A successful commit keeps current contents and removes the checkpoint.
A successful rollback reloads the saved file, removes the checkpoint, preserves
the runtime session and advances the timeline. For example, begin at revision 1,
edit at 2, edit at 3, rollback at 4 restores the contents from 1 with revision 4.
The runtime state is never serialized into the `.blend` file.

## Scene diff

`scene.diff` returns `transaction_id`, `baseline_revision` and `diff`. Diff contains
sorted `created_ids`, `modified_ids`, `deleted_ids` and UUID-sorted `changes`.
Each change contains:

```json
{
  "object_id": "<UUID>",
  "kind": "modified",
  "fields": ["world_matrix", "world_origin"],
  "before": {"object_id": "<UUID>", "world_matrix": []},
  "after": {"object_id": "<UUID>", "world_matrix": []}
}
```

The example abbreviates the observation records and matrices. Actual before/after
records include object name/type, collection membership, parent UUID, visibility,
render enablement, string tags, world origin/matrix, base and evaluated geometry
counts (vertices, edges, faces, triangles), evaluated bounds/dimensions and their
method, base `geometry_fingerprint`, and ordered `modifiers`. Created objects have
`before: null`; deleted objects have `after: null`. `fields` lists every changed
record key, or every present key for creation/deletion. Comparisons are exact.

The geometry fingerprint hashes base vertex coordinates and edge/polygon indices,
so same-count shape/topology edits are visible. Modifier records contain name,
type, writable scalar/array RNA settings and pointer target labels; object targets
also carry UUIDs. Read-only evaluation timing and other runtime diagnostics are
excluded. Collection-valued settings, Geometry Nodes inputs/internal graphs,
materials, UVs, custom normals and non-mesh datablock contents are not compared.
Parent relationships and some observation metadata are included, but this is not
an exhaustive Blender change audit.

Diff scope is the active scene's objects. Unlinking an object from that scene
counts as deletion and linking an existing object counts as creation, even when
its Blender datablock still exists. Other scenes and orphan datablocks are outside
the report. The full-file snapshot has a broader restore scope. External bpy edits
are visible in tracked diff fields, but do not automatically advance revisions.
There is no permanent diff history or standalone baseline store.

## Commit and rollback results

Both return `transaction_id`, `status` (`committed` or `rolled_back`), `diff` and
`diff_error`. Commit compares the begin baseline to current contents. Rollback
compares pre-restore current contents to the begin baseline, so its change arrays
describe the restoration: objects deleted since begin appear in `created_ids`,
and newly created objects appear in `deleted_ids`. These arrays are also copied to
the success envelope. Commit's arrays summarize the transaction's accumulated
changes, rather than additional scene edits at commit time.

Commit requires a readable, bounded diff. If it fails, the checkpoint remains
active. Rollback attempts a diff but can proceed when the current scene has UUID
collisions, nonfinite geometry, exceeded budgets or another measurement failure.
In that case rollback succeeds with `diff: null`, `diff_error: "<error code>"`, and
empty envelope change arrays. Empty arrays in this case mean unknown changes.
They do not imply that restoration changed nothing.

Rollback checks the private file's SHA-256 before loading. A missing/corrupted file
returns `SNAPSHOT_UNAVAILABLE` and keeps the transaction active. Save/load errors
return `SNAPSHOT_FAILED` / `ROLLBACK_FAILED`. Failed begin cleans its partial files;
failed rollback retains the checkpoint for retry. Rollback requires Object mode,
even if its preliminary diff failed; it does not force a mode change.

## Snapshot behavior and limitations

The snapshot uses Blender's save-copy and file-load operators on the main thread.
Begin preserves the current filepath, scene, frame and selection. Reload restores
saved scenes, objects, linked mesh relationships, material/UV/hierarchy/modifier
data, and saved active object/selection. All live Python datablock references from
before reload are invalid; every subsequent runtime tool reacquires objects by
UUID using live providers. Selection handles and scene cursors from older revisions
are invalid even when restored geometry exactly matches their original contents.

This is full-file restoration, including other scenes and saved orphan data,
according to Blender's normal `.blend` persistence rules. It does not restore
external files, unsaved image pixels, simulations, addon state, arbitrary Python
state or process configuration. Embedded scripts are disabled during reload.
External resources must remain available. Snapshot save rebases relative resource
paths; reload converts those paths to absolute targets before deleting the private
checkpoint directory. Absolute conversion changes path spelling while retaining
the target. The current Blender filepath becomes the private checkpoint filename,
which is removed after rollback: Blender's filepath property is read-only. The
original `.blend` file is never overwritten to restore its filename. Use an
explicit export/save facility when one becomes available to choose a new filename.

Limits: one active transaction, at most 1,000 objects across all Blender data,
200,000 active-scene base plus evaluated mesh elements (vertices, edges, faces and
loops; shared meshes count per object), and a 256 MiB saved file. Evaluated objects
must be available in the current dependency graph; all global objects require
valid, unique managed UUIDs. Empty/geometry-free objects can have null dimensions.
Reports must fit the existing transport budget; oversized diffs return
`RESPONSE_TOO_LARGE`. The disk budget is checked after save, so it bounds retained
checkpoints rather than peak write size. Dependency graph evaluation cost is not
bounded by the mesh scan budget.

Checkpoint paths are runtime-owned and never accepted from the API. Commit,
rollback, direct `api.close()` and graceful server disconnect/shutdown remove them.
Controller launches place checkpoints inside the controller-owned temporary
workspace, which is also removed when the client is disposed after crashes,
timeouts or forced termination.
A direct in-process caller should close its API; recovery is not crash-durable and
cannot resume across process sessions. There is no transaction isolation from
trusted external code or automatic rollback after process death.

## Example

```python
started = client.call("transaction.begin")
if started["success"]:
    transaction = {"transaction_id": started["result"]["transaction_id"]}
    edit = client.call("object.transform", {"object_id": object_id, "location": [0, 0, 1]})
    report = client.call("validate.geometry", {"object_ids": [object_id]})
    print(client.call("scene.diff", transaction))
    keep = edit["success"] and report["success"] and report["result"]["passed"]
    finished = client.call("transaction.commit" if keep else "transaction.rollback", transaction)
    print(finished)
```

Run `python3 -m controller.headless tests/blender/recovery_smoke.py` for the
isolated Blender acceptance fixture. Blender operator details:
[save/load operators](https://docs.blender.org/api/5.0/bpy.ops.wm.html),
[BlendData filepath](https://docs.blender.org/api/5.2/bpy.types.BlendData.html).
