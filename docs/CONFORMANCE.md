# Conformance

Milestone 1 reuses the integration acceptance tests against real isolated Blender
processes. Run `python3 -m unittest discover -s conformance -v` from the repo root.
No AI model is involved. Future capability conformance will live in this directory.

Checks cover persistent process identity, contiguous execution sequence under
concurrent controller callers, execution on the Blender main thread, structured
command rejection and subsequent recovery, clean exit, forced process death,
missing executable, and independent headless script success/failure propagation.
Transport unit tests check framing, non-finite/malformed JSON, bounds and disconnects.


Milestone 2 adds real-process API discovery, descriptor lookup, version rejection,
invalid-argument rejection, unknown-tool handling, subsequent-call recovery and
captured JSON logs. Unit tests independently check strict schemas, version contracts,
response validation, registry consistency, descriptor isolation, non-JSON outputs,
internal-error redaction and omission of arguments/results from logs.

Run `python3 -m controller.headless tests/blender/api_smoke.py` for an isolated
Blender check that all advertised tools return valid success envelopes and leave scene
objects unchanged. This supplements the persistent-process integration suite.

Milestone 3 covers session bootstrap, new sessions after process restart, stale
revision and old-session rejection, malformed state fields and recovery. A real
Blender scene fixture creates and removes an object while verifying that restoring
contents advances the timeline. Unit tests additionally cover conservative revision
advancement after failure, concurrent stale edits, read stability, and client
rejection of corrupt state responses. The state fixture can also run directly with
`python3 -m controller.headless tests/blender/state_smoke.py`.

Milestone 4 verifies startup identity capability reporting, UUID assignment,
rename-safe resolution, Blender data-block and operator duplication, collision and
malformed-ID detection, deletion and name reuse, and save/load with live-reference
reacquisition. A second check writes a .blend file in one isolated process and
resolves the same UUIDs in another process with a different session. Unit tests
also cover read-only objects, write failures, generation collisions, and rejection
of unmanaged or removed objects. Run the lifecycle fixture directly with
`python3 -m controller.headless tests/blender/identity_smoke.py`.

Milestone 5 checks scene summary and paginated UUID listing over persistent IPC.
A real Blender fixture adds 253 objects and verifies type, collection, visibility,
name, tag and world-origin region filters, bounded complete pagination, exclusion
visibility, collision-free resolution, and read-only state. It rejects tampered,
filter-mismatched, edited-scene and old-revision cursors. Orphans and other-scene
objects remain excluded. Unit checks also cover empty scenes, nested invalid
arguments, schema rejection, response size limits and subsequent-call recovery.
Run `python3 -m controller.headless tests/blender/scene_smoke.py` directly.

Targeted inspection tests compare original mesh counts with array/mirror/solidify
results and verify evaluated world bounds under parenting, rotation and negative
scale. Geometry-free objects have nullable dimensions. Hierarchy checks paginate
parent UUID edges and reject cross-endpoint and reparented cursors. Inspection
checks UUID order, duplicate/unknown/malformed IDs, excluded evaluation, base-mesh
preservation and absence of temporary mesh data-block leaks. Run
`python3 -m controller.headless tests/blender/geometry_smoke.py` directly.
