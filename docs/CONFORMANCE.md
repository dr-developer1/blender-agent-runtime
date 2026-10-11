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
Blender check that all seven tools return valid success envelopes and leave scene
objects unchanged. This supplements the persistent-process integration suite.

Milestone 3 covers session bootstrap, new sessions after process restart, stale
revision and old-session rejection, malformed state fields and recovery. A real
Blender scene fixture creates and removes an object while verifying that restoring
contents advances the timeline. Unit tests additionally cover conservative revision
advancement after failure, concurrent stale edits, read stability, and client
rejection of corrupt state responses. The state fixture can also run directly with
`python3 -m controller.headless tests/blender/state_smoke.py`.
