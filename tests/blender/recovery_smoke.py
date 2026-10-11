"""Actual full-file restore, live UUID re-resolution, and numeric scene diffs."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.schemas import validate_response, validate_arguments

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
    scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
    depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True)


def call(tool, args=None, error=None, **state):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
        'expected_revision': api.state.revision, 'tool': tool, 'arguments': args or {}, **state})
    validate_response(response)
    if error:
        assert not response['success'] and response['error']['code'] == error, response
    else:
        assert response['success'], response
    return response


def begin():
    response = call('transaction.begin')
    return {'transaction_id': response['result']['transaction_id']}


def inspect(oid):
    return call('scene.inspect_objects', {'object_ids': [oid]})['result']['objects'][0]


features = call('runtime.get_supported_features')['result']
assert features['transactions'] and features['scene_diff']
assert len(api.registry.names()) == 33
for name in ('object.transform', 'mesh.extrude', 'mesh.query'):
    descriptor = call('runtime.describe_tool', {'name': name})['result']
    assert descriptor['supports']['transactions'] and descriptor['transaction_safe']

cube_id = bpy.data.objects['Cube']['bar_uuid']
cube = api.identities.resolve(cube_id)
# Preserve shared mesh, UVs, materials, hierarchy, modifier settings, UI state,
# objects outside the active scene and orphan data, beyond diff's active-scene scope.
linked = call('object.duplicate', {'object_id': cube_id, 'linked_data': True})['result']['object_id']
parent_id = call('object.create_primitive', {'primitive': 'CUBE', 'location': [5, 0, 0]})['result']['object_id']
call('object.set_parent', {'object_id': linked, 'parent_id': parent_id})
cube.data.materials.clear()
material = bpy.data.materials.new('Checkpoint material')
cube.data.materials.append(material)
uv = cube.data.uv_layers.active or cube.data.uv_layers.new(name='Checkpoint UV')
uv.data[0].uv = (.123, .456)
modifier = cube.modifiers.new('Checkpoint array', 'ARRAY')
modifier.count = 2
modifier.relative_offset_displace = (1.5, 0, 0)
other_scene = bpy.data.scenes.new('Checkpoint other scene')
other = bpy.data.objects.new('Checkpoint outside active scene', None)
other_scene.collection.objects.link(other)
other_id = api.identities.ensure(other)
orphan_mesh = bpy.data.meshes.new('Checkpoint orphan mesh')
orphan_mesh.use_fake_user = True
for obj in bpy.context.view_layer.objects:
    obj.select_set(False)
cube.select_set(True)
bpy.context.view_layer.objects.active = cube
bpy.context.scene.frame_set(7)
original_filepath = bpy.data.filepath
baseline = inspect(cube_id)
cursor = call('scene.list_objects', {'limit': 1})['result']['next_cursor']

args = begin()
path = api.recovery.active.path
assert path.exists() and bpy.data.filepath == original_filepath
assert tuple(bpy.context.selected_objects) == (cube,)
assert bpy.context.view_layer.objects.active == cube
assert bpy.context.scene.frame_current == 7
assert call('scene.diff', args)['result']['diff']['changes'] == []
revision = api.state.revision
call('transaction.begin', error='TRANSACTION_ACTIVE')
assert api.state.revision == revision + 1
call('transaction.rollback', {'transaction_id': 'wrong'}, error='INVALID_TRANSACTION')
revision = api.state.revision
call('transaction.rollback', args, expected_revision=revision - 1, error='STALE_SCENE_STATE')
assert api.state.revision == revision

# Shape changes with equal topology counts and modifier parameter changes are visible.
cube.data.vertices[0].co.x -= .25
cube.modifiers[0].count = 3
bpy.context.view_layer.update()
shape_diff = call('scene.diff', args)['result']['diff']
fields = next(item['fields'] for item in shape_diff['changes'] if item['object_id'] == cube_id)
assert 'geometry_fingerprint' in fields and 'modifiers' in fields, fields
call('object.transform', {'object_id': cube_id, 'location': [1, 2, 3]})
cube.modifiers.clear()
edit_handle = call('mesh.query', {'object_id': cube_id, 'element_type': 'FACE',
    'selectors': [{'kind': 'top'}]})['result']['selection_handle']
call('mesh.extrude', {'selection_handle': edit_handle, 'offset': [0, 0, .5]})
assert api.identities.resolve(cube_id).data != api.identities.resolve(linked).data
assert inspect(cube_id)['base_geometry']['vertices'] > baseline['base_geometry']['vertices']
created = call('object.create_primitive', {'primitive': 'CONE', 'segments': 12})['result']['object_id']
call('object.delete', {'object_id': parent_id})
api.identities.resolve(cube_id).data.materials.clear()
bpy.data.objects.remove(other, do_unlink=True)
bpy.data.meshes.remove(orphan_mesh)
bpy.context.scene.frame_set(25)
diff_response = call('scene.diff', args)
validate_arguments(diff_response['result'], api.registry.describe('scene.diff')['output_schema'])
diff = diff_response['result']['diff']
assert diff['created_ids'] == [created] and diff['deleted_ids'] == [parent_id], diff
assert cube_id in diff['modified_ids'] and linked in diff['modified_ids']
handle = call('mesh.query', {'object_id': cube_id, 'element_type': 'FACE',
    'selectors': [{'kind': 'top'}]})['result']['selection_handle']
old_revision, session = api.state.revision, api.state.session_id
old_cube = api.identities.resolve(cube_id)
restored = call('transaction.rollback', args)
assert restored['revision_after'] == old_revision + 1 and api.state.session_id == session
assert restored['created_ids'] == [parent_id] and restored['deleted_ids'] == [created]
assert restored['result']['diff_error'] is None and not path.parent.exists()
assert api.recovery.active is None
cube = api.identities.resolve(cube_id)
assert inspect(cube_id) == baseline
assert cube.data == api.identities.resolve(linked).data
assert api.identities.resolve(linked).parent == api.identities.resolve(parent_id)
assert len(cube.data.materials) == 1 and cube.data.materials[0].name == 'Checkpoint material'
assert abs(cube.data.uv_layers.active.data[0].uv.x - .123) < 1e-6
assert cube.modifiers[0].count == 2
assert api.identities.resolve(other_id).name == 'Checkpoint outside active scene'
assert 'Checkpoint orphan mesh' in bpy.data.meshes
assert bpy.context.scene.frame_current == 7
assert bpy.data.filepath == str(path)
assert bpy.context.view_layer.objects.active == cube and tuple(bpy.context.selected_objects) == (cube,)
try:
    old_cube.name
except ReferenceError:
    pass
else:
    raise AssertionError('Old references survived full-file rollback')
call('mesh.inspect_selection', {'selection_handle': handle}, error='INVALID_SELECTION_HANDLE')
call('scene.list_objects', {'limit': 1, 'cursor': cursor}, error='STALE_SCENE_STATE')
call('object.transform', {'object_id': created, 'location': [0, 0, 0]}, error='OBJECT_NOT_FOUND')
call('object.transform', {'object_id': cube_id, 'location': [0, 0, 0]}, expected_revision=old_revision,
     error='STALE_SCENE_STATE')
call('transaction.rollback', args, error='NO_ACTIVE_TRANSACTION')

# Commit keeps edits; snapshots and identities are fresh for the next transaction.
args = begin()
path = api.recovery.active.path
call('object.transform', {'object_id': cube_id, 'location': [9, 0, 0]})
committed = call('transaction.commit', args)
assert cube_id in committed['modified_ids'] and not path.parent.exists()
assert abs(api.identities.resolve(cube_id).location.x - 9) < 1e-6
args2 = begin()
call('transaction.commit', args, error='INVALID_TRANSACTION')
call('transaction.rollback', args2)

# Invalid identity, non-finite geometry and excessive post-edit budgets must not
# strand a known-good checkpoint. Change arrays are unknown when diff fails.
args = begin()
collision = api.identities.resolve(cube_id).copy()
bpy.context.scene.collection.objects.link(collision)
call('transaction.commit', args, error='UUID_COLLISION')
restored = call('transaction.rollback', args)
assert restored['result']['diff'] is None and restored['result']['diff_error'] == 'UUID_COLLISION'
assert api.identities.resolve(cube_id).name == 'Cube'
args = begin()
api.identities.resolve(cube_id).data.vertices[0].co.x = float('nan')
restored = call('transaction.rollback', args)
assert restored['result']['diff_error'] == 'INVALID_GEOMETRY'
args = begin()
with patch('runtime.recovery.MAX_DIFF_ELEMENTS', 1):
    call('scene.diff', args, error='RECOVERY_LIMIT_EXCEEDED')
    restored = call('transaction.rollback', args)
    assert restored['result']['diff_error'] == 'RECOVERY_LIMIT_EXCEEDED'

# Snapshot corruption is caught before file replacement, then a retry can restore.
args = begin()
path = api.recovery.active.path
bytes_before = path.read_bytes()
path.write_bytes(b'corrupt checkpoint')
call('transaction.rollback', args, error='SNAPSHOT_UNAVAILABLE')
assert api.recovery.active is not None
path.write_bytes(bytes_before)
call('transaction.rollback', args)

# Begin rejects unsupported/budgeted scenes without creating a transaction.
with patch('runtime.recovery.MAX_DIFF_OBJECTS', 1):
    call('transaction.begin', error='RECOVERY_LIMIT_EXCEEDED')
with patch('runtime.recovery.MAX_SNAPSHOT_BYTES', 1):
    call('transaction.begin', error='RECOVERY_LIMIT_EXCEEDED')
assert api.recovery.active is None
cube = api.identities.resolve(cube_id)
bpy.context.view_layer.objects.active = cube
bpy.ops.object.mode_set(mode='EDIT')
call('transaction.begin', error='UNSUPPORTED_OBJECT_MODE')
assert bpy.context.mode == 'EDIT_MESH'
bpy.ops.object.mode_set(mode='OBJECT')
args = begin()
bpy.ops.object.mode_set(mode='EDIT')
call('transaction.rollback', args, error='UNSUPPORTED_OBJECT_MODE')
assert api.recovery.active is not None
bpy.ops.object.mode_set(mode='OBJECT')
call('transaction.rollback', args)

# Relative external resources retain their target after restoring filepath.
with tempfile.TemporaryDirectory(prefix='bar-relative-fixture-') as directory:
    original = Path(directory) / 'original.blend'
    image_path = Path(directory) / 'texture.png'
    image = bpy.data.images.new('Checkpoint relative image', width=1, height=1)
    image.filepath_raw = str(image_path)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    image = bpy.data.images.load(str(image_path))
    image.name = 'Checkpoint relative image'
    image.use_fake_user = True
    bpy.ops.wm.save_as_mainfile(filepath=str(original))
    image.filepath = '//texture.png'
    args = begin()
    call('transaction.rollback', args)
    image = bpy.data.images['Checkpoint relative image']
    assert bpy.data.filepath != str(original)
    assert original.exists()
    assert Path(bpy.path.abspath(image.filepath)).resolve() == image_path.resolve(), image.filepath
    assert len(image.pixels) == 4
    assert image.has_data

args = begin()
path = api.recovery.active.path
api.close()
assert not path.parent.exists()
print('BAR_RECOVERY_HEADLESS_OK')
