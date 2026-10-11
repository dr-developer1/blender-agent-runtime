"""Basic object control conformance through the public dispatcher."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from runtime.api import RuntimeAPI

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
                 scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
                 depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True)

def call(tool, args=None, error=None):
    before = api.state.revision
    result = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                          'expected_revision': before, 'tool': tool, 'arguments': args or {}})
    if error:
        assert not result['success'] and result['error']['code'] == error, result
    else:
        assert result['success'], result
    return result

def close(a, b):
    assert all(abs(x-y) < 1e-5 for x, y in zip(a, b)), (a, b)

active = bpy.context.view_layer.objects.active
selected = list(bpy.context.selected_objects)
for kind, counts in [('CUBE', (8, 12, 6)), ('PLANE', (4, 4, 1)),
                     ('CYLINDER', (64, 96, 34)), ('CONE', (33, 64, 33))]:
    response = call('object.create_primitive', {'primitive': kind, 'size': 400, 'unit': 'mm'})
    oid = response['result']['object_id']
    assert response['created_ids'] == [oid]
    obj = api.identities.resolve(oid)
    assert (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)) == counts
    bpy.context.view_layer.update()
    close(obj.dimensions, (0.4, 0.4, 0 if kind == 'PLANE' else 0.4))
    assert all(p.area > 0 for p in obj.data.polygons)
    if kind != 'PLANE':
        assert all(p.normal.dot(p.center) > 0 for p in obj.data.polygons)
assert bpy.context.view_layer.objects.active == active
assert list(bpy.context.selected_objects) == selected
cube = call('object.create_primitive', {'primitive': 'CUBE', 'name': 'Child'})['result']['object_id']
obj = api.identities.resolve(cube)
handle = call('mesh.query', {'object_id': cube, 'element_type': 'EDGE',
                            'selectors': [{'kind': 'top'}]})['result']['selection_handle']
response = call('object.transform', {'object_id': cube, 'location': [10, 20, 30],
                                    'rotation': [0, 0, 90], 'scale': [2, 3, 4], 'unit': 'cm'})
assert response['modified_ids'] == [cube]
close(obj.location, (0.1, 0.2, 0.3))
close(obj.rotation_euler, (0, 0, 1.57079632679))
close(obj.scale, (2, 3, 4))
call('mesh.inspect_selection', {'selection_handle': handle}, error='INVALID_SELECTION_HANDLE')
parent = call('object.create_primitive', {'primitive': 'CUBE', 'location': [3, 2, 1]})['result']['object_id']
before = obj.matrix_world.copy()
call('object.set_parent', {'object_id': cube, 'parent_id': parent})
assert obj.parent == api.identities.resolve(parent)
close([v for row in obj.matrix_world for v in row], [v for row in before for v in row])
call('object.set_parent', {'object_id': parent, 'parent_id': cube}, error='PARENT_CYCLE')
copy = call('object.duplicate', {'object_id': cube})
duplicate_id = copy['result']['object_id']
duplicate = api.identities.resolve(duplicate_id)
assert duplicate_id != cube and duplicate.data != obj.data
assert duplicate.parent == obj.parent
assert copy['created_ids'] == [duplicate_id]
duplicate.data.vertices[0].co.x += 1
assert duplicate.data.vertices[0].co != obj.data.vertices[0].co
linked = call('object.duplicate', {'object_id': cube, 'linked_data': True})['result']['object_id']
assert api.identities.resolve(linked).data == obj.data
response = call('object.delete', {'object_id': parent})
assert response['deleted_ids'] == [parent]
assert set(response['modified_ids']) == {cube, duplicate_id, linked}
assert obj.parent is None
close([v for row in obj.matrix_world for v in row], [v for row in before for v in row])
call('object.transform', {'object_id': parent, 'location': [0, 0, 0]}, error='OBJECT_NOT_FOUND')
# Schema failures do not consume a revision; handler rejection does.
revision = api.state.revision
call('object.transform', {'object_id': cube, 'scale': [1, True, 1]}, error='INVALID_ARGUMENT')
assert api.state.revision == revision
call('object.transform', {'object_id': cube, 'scale': [1, 0, 1]}, error='INVALID_ARGUMENT')
assert api.state.revision == revision + 1
close(obj.scale, (2, 3, 4))
revision = api.state.revision
response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                        'expected_revision': revision-1, 'tool': 'object.delete',
                        'arguments': {'object_id': cube}})
assert response['error']['code'] == 'STALE_SCENE_STATE'
assert api.state.revision == revision and api.identities.resolve(cube) == obj
call('object.set_parent', {'object_id': cube, 'parent_id': parent}, error='OBJECT_NOT_FOUND')
# Edit mode is rejected without touching the mesh or UI state.
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
call('object.delete', {'object_id': cube}, error='UNSUPPORTED_OBJECT_MODE')
assert obj.mode == 'EDIT'
bpy.ops.object.mode_set(mode='OBJECT')
# Partial transforms preserve the effective omitted components, including deltas.
obj.rotation_mode = 'QUATERNION'
from mathutils import Quaternion
obj.rotation_quaternion = Quaternion((0, 0, 1), 0.4)
obj.delta_location = (1, 2, 3)
obj.delta_scale = (2, 2, 2)
bpy.context.view_layer.update()
old_location, old_rotation, old_scale = obj.matrix_basis.decompose()
call('object.transform', {'object_id': cube, 'location': [4, 5, 6]})
close(obj.location, (4, 5, 6))
close(obj.scale, old_scale)
close(obj.rotation_euler, old_rotation.to_euler('XYZ'))
close(obj.delta_location, (0, 0, 0))
# Clearing parents and opting into local-space parenting are deterministic.
parent = call('object.create_primitive', {'primitive': 'CUBE', 'location': [2, 0, 0]})['result']['object_id']
call('object.set_parent', {'object_id': cube, 'parent_id': parent, 'keep_world_transform': False})
close(obj.location, (4, 5, 6))
close(obj.matrix_world.translation, (6, 5, 6))
call('object.set_parent', {'object_id': cube})
assert obj.parent is None
close(obj.matrix_world.translation, (6, 5, 6))
# Singular parents, sheared poses and constraints are rejected before scene writes.
parent_obj = api.identities.resolve(parent)
parent_obj.scale = (0, 1, 1)
bpy.context.view_layer.update()
call('object.set_parent', {'object_id': cube, 'parent_id': parent}, error='INVALID_PARENT_TRANSFORM')
assert obj.parent is None
parent_obj.scale = (2, 1, 1)
call('object.set_parent', {'object_id': cube, 'parent_id': parent, 'keep_world_transform': False})
old_matrix = obj.matrix_world.copy()
call('object.set_parent', {'object_id': cube}, error='UNSUPPORTED_OBJECT_STATE')
assert obj.parent == parent_obj
call('object.delete', {'object_id': parent}, error='UNSUPPORTED_OBJECT_STATE')
assert api.identities.resolve(parent) == parent_obj
close([v for row in obj.matrix_world for v in row], [v for row in old_matrix for v in row])
constraint = obj.constraints.new('COPY_LOCATION')
call('object.transform', {'object_id': cube, 'location': [0, 0, 0]}, error='UNSUPPORTED_OBJECT_STATE')
obj.constraints.remove(constraint)
# UUID addressing remains valid after rename; names can be reused after deletion.
obj.name = 'Renamed target'
call('object.delete', {'object_id': cube})
replacement = call('object.create_primitive', {'primitive': 'CUBE', 'name': 'Renamed target'})['result']['object_id']
assert replacement != cube
call('object.delete', {'object_id': cube}, error='OBJECT_NOT_FOUND')
print('BAR_OBJECT_HEADLESS_OK')
