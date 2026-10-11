"""Targeted inspection, hierarchy, modifiers and evaluated world geometry."""
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.identity import UUID_PROPERTY
from runtime.schemas import validate_response

scene = bpy.context.scene
parent = bpy.data.objects.new('Parent', None)
scene.collection.objects.link(parent)
parent.location = (10, 20, 30)
parent.scale = (2, -3, 4)
parent.rotation_euler.z = math.pi / 2
cube = bpy.data.objects['Cube']
cube.parent = parent
array = cube.modifiers.new('Copies', 'ARRAY')
array.count = 3
array.relative_offset_displace = (1, 0, 0)
mirror = cube.modifiers.new('Mirrored copies', 'MIRROR')
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 10))
plane = bpy.context.object
solidify = plane.modifiers.new('Thickness', 'SOLIDIFY')
solidify.thickness = 0.2
solidify.offset = 0
api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
                 scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
                 depsgraph=lambda: bpy.context.evaluated_depsgraph_get())


def call(tool, arguments):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                            'expected_revision': api.state.revision, 'tool': tool, 'arguments': arguments})
    validate_response(response)
    return response


cube_id, plane_id, parent_id = (obj[UUID_PROPERTY] for obj in (cube, plane, parent))
mesh_count = len(bpy.data.meshes)
response = call('scene.inspect_objects', {'object_ids': [plane_id, cube_id, parent_id]})
assert response['success'], response
inspected_plane, inspected_cube, inspected_parent = response['result']['objects']
assert [obj['object_id'] for obj in response['result']['objects']] == [plane_id, cube_id, parent_id]
assert inspected_cube['parent_id'] == parent_id
assert inspected_cube['base_geometry'] == {'vertices': 8, 'edges': 12, 'faces': 6, 'triangles': 12}
assert inspected_cube['evaluated_geometry']['vertices'] == 48
assert inspected_cube['evaluated_geometry']['triangles'] == 72
for actual, expected in zip(inspected_cube['evaluated_dimensions'], (6, 20, 8)):
    assert math.isclose(actual, expected, abs_tol=1e-4), inspected_cube
for actual, expected in zip(inspected_cube['evaluated_bounds']['min'], (7, 10, 26)):
    assert math.isclose(actual, expected, abs_tol=1e-4), inspected_cube
assert inspected_cube['bounds_method'] == 'evaluated_vertices'
assert inspected_plane['base_geometry']['vertices'] == 4
assert inspected_plane['evaluated_geometry']['vertices'] == 8
assert math.isclose(inspected_plane['evaluated_dimensions'][2], 0.2, abs_tol=1e-4)
assert inspected_parent['evaluated_bounds'] is None, inspected_parent
assert inspected_parent['evaluated_geometry'] is None
assert api.state.revision == 0
assert len(bpy.data.meshes) == mesh_count
assert len(cube.data.vertices) == 8
assert len(plane.data.vertices) == 4

nodes = []
arguments = {'limit': 2}
while True:
    page = call('scene.get_hierarchy', arguments)['result']
    nodes.extend(page['nodes'])
    if page['next_cursor'] is None:
        break
    arguments['cursor'] = page['next_cursor']
assert len(nodes) == len(scene.objects)
assert next(node for node in nodes if node['object_id'] == cube_id)['parent_id'] == parent_id
assert call('scene.inspect_objects', {'object_ids': [cube_id, cube_id]})['error']['code'] == 'INVALID_ARGUMENT'
assert call('scene.inspect_objects', {'object_ids': ['malformed']})['error']['code'] == 'INVALID_OBJECT_UUID'
assert call('scene.inspect_objects', {'object_ids': ['00000000-0000-4000-8000-999999999999']})['error']['code'] == 'OBJECT_NOT_FOUND'
print('BAR_GEOMETRY_HEADLESS_OK')
