# Diagnostic observation — API 1.0

Milestone 11 provides `observe.camera`, `observe.render` and
`observe.render_multiview`. The persistent server enables them; in-process owners
opt in with `RuntimeAPI(..., observation=True)` and live object, scene, view-layer
and dependency-graph providers. Mutation and recovery are independent options.
Discovery reports `deterministic_cameras` and `diagnostic_rendering`, typed inputs,
outputs and limits. These tools are read-only and transaction safe: neither
successful nor rejected calls advance revisions or expire handles/cursors.

All three accept optional `object_ids` (1–100 unique UUIDs), `width`, `height`
(default 384 each; 32–768), and `padding` (default 1.15; 1.05–3). Omitted IDs select
visible, render-enabled meshes in the active scene/view layer. Explicit targets
must be managed meshes in that scene, visible and render enabled. Other scene
objects, cameras, lights and non-mesh content are omitted. An empty target or
vertex set rejects rather than producing a misleading empty image.

Camera and single-view render accept `view`, default `perspective`. Views are
`front`, `back`, `left`, `right`, `top`, `bottom`, `perspective`. Multiview accepts
`views` (1–6 unique views) and defaults to front, back, left, right, top, perspective
in that order. Target UUIDs are sorted. Cameras fit the combined world AABB of the
current evaluated mesh vertices, including viewport modifier results and world
transforms. Numeric coordinates use metres. Perspective uses a 50 mm lens and
36 mm horizontal sensor; the other views are orthographic. Framing accounts for
aspect ratio and corner depth. Front observes from −Y toward +Y with +Z up;
back from +Y; left from −X; right from +X; top from +Z with +Y up; bottom from −Z
with −Y up. Perspective observes from the (+X, −Y, +Z) diagonal with +Z up.

`observe.camera` returns `object_ids`, `bounds`, `geometry_source` (currently
`evaluated_viewport_mesh`) and `camera`. The latter contains `view`, `projection`,
world `location`, `target`, a row-major 4×4 `world_matrix`, `ortho_scale`, `lens_mm`,
`sensor_width_mm`, `clip_start`, `clip_end`, `width`, and `height`. It describes a
virtual camera; no persistent camera object or UUID is created.

Render tools also accept `engine` (`WORKBENCH`, default, or `EEVEE`) and `mode`
(`solid`, default, `wireframe`, or `silhouette`). Wireframe and silhouette require
Workbench. Workbench solid uses a fixed studio light and grey geometry on white.
Silhouette uses black unlit geometry on white. Wireframe builds thin black tubes
along evaluated mesh edges, including loose edges, on white; hidden/back edges
are shown and triangulation diagonals are absent. Tube width approximates one
pixel using the largest fitted view width in that batch. Wireframe is an edge
inspection image, not a surface occlusion pass. EEVEE solid preserves evaluated
mesh material slots/UVs and uses a fixed world and two area lights, with output
Standard colour management. It observes material appearance under this diagnostic
rig, rather than the source scene lighting.

Render results contain the common target fields, `engine`, `mode`, and `images`.
Each image has `camera`, `mime_type: "image/png"`, `png_base64`, and `byte_count`.
Single-view returns one image; multiview uses one evaluated snapshot for all views.
No caller-supplied output path is accepted. Decode PNGs on the controller:

```python
import base64
from pathlib import Path
from controller.client import BlenderClient

with BlenderClient(request_timeout=60) as client:
    response = client.call("observe.render_multiview")
    if response["success"]:
        for image in response["result"]["images"]:
            name = image["camera"]["view"]
            Path(f"{name}.png").write_bytes(base64.b64decode(image["png_base64"]))
```

Rendering creates an isolated temporary scene, evaluated mesh copies, camera,
world and optional edge curves/lights. It does not change source geometry,
materials, camera, frame, selection, render settings or colour management.
Allocated datablocks and temporary PNG files are removed in `finally`, including
failed renders and PNG budget failures. The controller-owned temporary root also
covers forced termination. Blender's global Render Result may be replaced, as with
any native render; this is outside tracked scene state. Trusted handlers installed
by external code may run during rendering and are outside the isolation guarantee.

Limits are 100 objects, 200,000 total evaluated vertices+edges+faces, 1,048,576
combined pixels, six views and 700,000 combined raw PNG bytes. PNG base64 plus
bounded metadata fits the existing 1 MiB transport frame. Pixel/geometry budgets
reject with `OBSERVATION_LIMIT_EXCEEDED`; PNG overflow returns
`RESPONSE_TOO_LARGE` and discards the batch. Reduce size or views and retry.
`RENDER_FAILED` reports engine/render/file failures without private exception text.
Other preflight errors include `INVALID_ARGUMENT`, identity errors,
`OBJECT_NOT_IN_SCENE`, `UNSUPPORTED_OBJECT_TYPE`, `OBJECT_NOT_VISIBLE`,
`EMPTY_OBSERVATION`, `INVALID_GEOMETRY`, `OBJECT_NOT_EVALUATED`,
`UNSUPPORTED_OBJECT_MODE` and `UNSUPPORTED_INSTANCING`.

Scope: Object mode, meshes and viewport-evaluated geometry. Instances of selected
meshes are rejected; non-mesh content is not converted. This does not provide
render-time subdivision, simulation, cryptomatte, normals/depth, final lighting,
or Cycles output. External material resources must remain available. Coordinates
must be finite and within one million metres. Dependency-graph evaluation and GPU
work precede/exceed the scan budget; the controller deadline bounds the process,
not the geometry scan. Increase the client timeout for EEVEE startup on software
renderers. Unsupported GPU backends can fail natively and require a new client.
Camera metadata is deterministic for the same evaluated bounds/options. Volatile
PNG timestamp/filename stamp fields and dithering are disabled. Raster pixels are
not guaranteed identical across Blender versions, GPUs or drivers.

Blender API references: [Camera](https://docs.blender.org/api/5.2/bpy.types.Camera.html),
[View3DShading](https://docs.blender.org/api/5.2/bpy.types.View3DShading.html), and
[render operator](https://docs.blender.org/api/5.2/bpy.ops.render.html).

Milestone 15 raises the isolated EEVEE diagnostic scene from 16 to 128 render
samples to reduce cavity shadow noise. Source scene sample settings stay intact;
Workbench and public render budgets are unchanged. Higher samples increase
render time; the existing transport timeout and renderer cleanup still apply.
