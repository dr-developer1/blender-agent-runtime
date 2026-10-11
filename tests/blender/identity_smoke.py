"""Exercise UUID lifecycle against Blender objects, duplication and .blend files."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.errors import ToolError
from runtime.identity import UUID_PROPERTY

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects)
identity = api.identities
assert api.state.revision == 0
assert len({obj[UUID_PROPERTY] for obj in bpy.data.objects}) == len(bpy.data.objects)
source = bpy.data.objects['Cube']
source_id = source[UUID_PROPERTY]
source.name = 'Renamed managed object'
assert identity.resolve(source_id) == source


def expect_error(code, action):
    try:
        action()
    except ToolError as exc:
        assert exc.code == code, exc.as_dict()
    else:
        raise AssertionError('Expected ' + code)


# Exercise the known-copy helper inside a revision-guarded mutation handler.
def copy_object(args):
    duplicate = source.copy()
    bpy.context.scene.collection.objects.link(duplicate)
    assert duplicate[UUID_PROPERTY] == source_id
    expect_error('UUID_COLLISION', lambda: identity.resolve(source_id))
    expect_error('UUID_COLLISION', identity.ensure_all)
    return {'object_id': identity.assign_duplicate(source, duplicate)}


api.registry.register(ToolSpec('test.copy', 'Copy fixture', side_effects=('scene',)), copy_object)
response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                        'expected_revision': 0, 'tool': 'test.copy', 'arguments': {}})
assert response['success'], response
assert response['revision_after'] == 1
duplicate_id = response['result']['object_id']
duplicate = identity.resolve(duplicate_id)
assert source_id != duplicate_id
assert identity.resolve(source_id) == source

# Verify the real duplicate operator also receives an independent persistent ID.
bpy.ops.object.select_all(action='DESELECT')
source.select_set(True)
bpy.context.view_layer.objects.active = source
bpy.ops.object.duplicate()
operator_duplicate = bpy.context.view_layer.objects.active
assert operator_duplicate != source
assert operator_duplicate[UUID_PROPERTY] == source_id
operator_id = identity.assign_duplicate(source, operator_duplicate)
assert len({source_id, duplicate_id, operator_id}) == 3

# Deleting an object makes its UUID unresolved, even if its name is reused.
duplicate_name = duplicate.name
bpy.data.objects.remove(duplicate, do_unlink=True)
expect_error('OBJECT_NOT_FOUND', lambda: identity.resolve(duplicate_id))
expect_error('OBJECT_NOT_FOUND', lambda: identity.ensure(duplicate))
replacement = bpy.data.objects.new(duplicate_name, None)
bpy.context.scene.collection.objects.link(replacement)
replacement_id = identity.ensure(replacement)
assert replacement_id != duplicate_id
expect_error('OBJECT_NOT_FOUND', lambda: identity.resolve(duplicate_id))

# Invalid properties and unknown collisions never silently change identities.
replacement[UUID_PROPERTY] = 'invalid'
expect_error('INVALID_OBJECT_UUID', identity.ensure_all)
replacement[UUID_PROPERTY] = source_id
expect_error('UUID_COLLISION', lambda: identity.resolve(source_id))
replacement[UUID_PROPERTY] = replacement_id

# Save/load changes object references; the existing resolver reacquires live data.
expected = {obj[UUID_PROPERTY]: obj.name for obj in bpy.data.objects}
with tempfile.TemporaryDirectory(prefix='bar-identity-') as directory:
    blend_path = str(Path(directory) / 'identity.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    def reload_scene(args):
        bpy.ops.wm.open_mainfile(filepath=blend_path)
        return {}
    api.registry.register(ToolSpec('test.reload', 'Load fixture', side_effects=('scene',)), reload_scene)
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                            'expected_revision': 1, 'tool': 'test.reload', 'arguments': {}})
    assert response['success'], response
    assert response['revision_after'] == 2
    for object_id, name in expected.items():
        assert identity.resolve(object_id).name == name
    assert identity.ensure_all() == []
    assert api.state.revision == 2
    assert identity.resolve(source_id).name == 'Renamed managed object'
print('BAR_IDENTITY_HEADLESS_OK')
