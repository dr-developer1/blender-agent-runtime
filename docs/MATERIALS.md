# Basic materials

Milestone 13 adds `material.create` and `material.assign`, enabled with object
control. The persistent Blender server advertises `basic_materials: true` and 36
public tools. In-process read-only API instances keep the backend disabled.

`material.create` accepts optional `name` (1–63 characters), `base_color` (four
linear RGBA components in [0, 1]), `roughness` and `metallic` (both in [0, 1]).
Defaults are Material, [0.8, 0.8, 0.8, 1], 0.5 and 0. Only opaque alpha 1 is
supported. It creates a Principled BSDF connected to Material Output and mirrors
color/roughness/metallic on the viewport material properties. No texture, UV,
procedural wood grain, transparency, node editing or recipe is provided yet.

The result contains `material_id`, actual Blender `name`, `base_color`,
`roughness`, and `metallic`. The UUID lives in `bar_material_uuid` and persists
across save/load and rename. A fake user retains an unassigned material across
checkpoint reload. Names are display labels; address materials only with UUIDs.
Resolution rescans live datablocks and rejects missing or colliding IDs with
`MATERIAL_NOT_FOUND` or `MATERIAL_ID_COLLISION`. Existing materials are not
assigned IDs at startup, and no material listing/update/delete tool is exposed.

`material.assign` requires `object_id` and `material_id`. It replaces every
base-mesh face's material with a single DATA-linked slot. It prepares an independent
mesh copy, preserving linked duplicates, geometry, transforms and object UUID.
Existing object-linked overrides are replaced. Modifiers may override evaluated
face materials; use asset validation and EEVEE observation to check the result.
Only editable mesh objects in the active scene, in Object mode, without shape keys
or object/mesh animation are supported. Selection and active object are preserved.
The result repeats the two IDs and `modified_ids` contains the target object UUID.
Material UUIDs never enter the envelope's object change arrays.

Both tools advance revision on validated attempts, invalidating cursors and
selection handles; schema rejection does not advance revision. Transaction-safe
metadata is enabled when recovery is available. Full-file rollback restores
materials and assignments and removes materials created after the checkpoint.
Scene diffs include a material assignment fingerprint (slot linkage, material
identity/name and base face indices). Unassigned material creation and shader
contents are outside the object diff's scope, though restored by rollback.

```python
material = client.call('material.create', {
    'name': 'Warm wood', 'base_color': [.22, .08, .025, 1],
    'roughness': .65, 'metallic': 0,
})
if material['success']:
    client.call('material.assign', {
        'object_id': object_id,
        'material_id': material['result']['material_id'],
    })
```

Workbench is the fast shape diagnostic; EEVEE evaluates the PBR shader. Run the materialized stool with:

```bash
python3 -m benchmarks.stool --output artifacts/new-material-stool --engine EEVEE
```
 The exercise now requires material assignment before committing. The six-view material review is recorded in
[evidence](evidence/stool_material_review_m13.json), independently of the retained
pre-material Workbench visual scores. A uniform brown PBR surface is a basic
material approximation, not a realistic wood texture.
