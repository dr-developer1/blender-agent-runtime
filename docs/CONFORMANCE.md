# Conformance

Milestone 1 reuses the integration acceptance tests against real isolated Blender
processes. Run `python3 -m unittest discover -s conformance -v` from the repo root.
No AI model is involved. Future capability conformance will live in this directory.

Checks cover persistent process identity, contiguous execution sequence under
concurrent controller callers, execution on the Blender main thread, structured
command rejection and subsequent recovery, clean exit, forced process death,
missing executable, and independent headless script success/failure propagation.
Transport unit tests check framing, non-finite/malformed JSON, bounds and disconnects.
