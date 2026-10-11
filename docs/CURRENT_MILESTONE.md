# Current milestone

Milestone 10 — Recovery (steps 50–56): complete.

Implemented `scene.diff`, `transaction.begin`, `transaction.commit` and
`transaction.rollback`. Begin automatically saves a private full-file `.blend`
checkpoint; only one transaction is active per runtime. The server advertises 31
public tools. Runtime package version: 0.10.0; public API version: 1.0.

Diff captures bounded plain active-scene observations keyed by UUID, base mesh
fingerprints and writable scalar/array modifier settings. It reports sorted
created/modified/deleted IDs and before/after records with changed field names.
Same-count geometry edits and modifier parameter changes are visible. Commit
keeps edits, reports accumulated changes and discards the checkpoint. Rollback
checks its checksum, restores saved contents and reports the reverse diff. It can
restore even when collisions, nonfinite geometry, oversized observations or other
measurement failures prevent a diff; in that case `diff` is null and `diff_error`
explains why envelope change arrays are unknown.

Transaction controls declare side effects and use the existing conservative
revision rule. Every schema-valid attempt advances once, including failures;
precondition/schema failures do not. Rollback restores contents without rewinding
RuntimeState or changing session. Existing selection handles and scene cursors
expire. All runtime object access reacquires current datablocks by UUID, including
objects deleted and then restored. Object and mesh tools advertise transaction
support/safety when recovery is attached, and work normally outside transactions.
There is no automatic begin, validation, commit or rollback.

Snapshots live inside the controller-owned temporary workspace. Successful commit,
rollback and direct API/server shutdown discard them; controller disposal also
cleans files after child death or deadlines. Failed begin removes partial files;
failed rollback retains its checkpoint. No public caller supplies a snapshot path.
Recovery requires the explicit mutation backend and evaluated providers. Limits:
one transaction, 1,000 global objects, 200,000 active-scene base plus evaluated mesh
elements and 256 MiB retained checkpoint size, plus the existing response budget.

Verification on Linux, Python 3.12.3 and Blender 5.2.2 LTS: 83 unit tests, 29
real-Blender integration cases and the same 29 conformance checks passed. The
isolated recovery and API fixtures also passed. Coverage includes full-file restore,
commit persistence, lifecycle/state/ID failures, shape and modifier diffs, native
mesh extrusion and copy-on-write restoration, UUID re-resolution, handle/cursor
expiry, saved materials/UV/shared mesh/hierarchy/selection/frame state, other scenes
and saved orphan data, relative resource resolution, corrupt files, unsupported
Edit mode, observation/disk/response budgets, save/load failures and forced-death
cleanup. Commands are in README.md and the full contract in RECOVERY.md.

Limits: Object mode, one runtime-local transaction, no durable restart recovery,
no automatic validation/rollback, and no isolation from trusted external code.
Diff only covers tracked active-scene fields, not materials, UVs, node graph inputs,
non-mesh content or all Blender state. The snapshot restores a broader full-file
scope according to normal Blender persistence, including other scenes; it does
not restore external files, unsaved image pixels, simulation/addon/Python state.
External resources must remain available. Relative paths become absolute after
reload. Blender's read-only current filepath becomes the private checkpoint name,
which is removed after rollback; the original file is never overwritten to restore
its name. External edits are not automatically revision tracked. Disk limits are
checked after save and dependency graph evaluation costs remain unbounded by the
mesh scan budget. Direct in-process owners must close their API.

Next: Milestone 11 — Observation (steps 57–62): deterministic cameras, Workbench
rendering, multi-view rendering, optional EEVEE, wireframe and silhouette.
