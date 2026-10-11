"""Deterministic semantic addressing fixtures against actual Blender meshes."""
from pathlib import Path
import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.identity import UUID_PROPERTY
from runtime.schemas import validate_arguments
from runtime.selection import QUERY_OUTPUT, INSPECT_OUTPUT

cube = bpy.data.objects['Cube']
bpy.ops.mesh.primitive_plane_add(size=2)
plane = bpy.context.object
mesh = bpy.data.meshes.new('Nonmanifold')
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0),(0,-1,0),(0,0,1),(4,0,0),(5,0,0)],
                 [(5,6)], [(0,1,2),(1,0,3),(0,1,4)])
branch = bpy.data.objects.new('Branch', mesh)
bpy.context.scene.collection.objects.link(branch)
api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
                 scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
                 depsgraph=lambda: bpy.context.evaluated_depsgraph_get())


def call(tool, arguments):
    return api.execute({'api_version':'1.0', 'session_id':api.state.session_id,
                        'expected_revision':api.state.revision, 'tool':tool, 'arguments':arguments})


def query(obj, element, selectors, space='WORLD'):
    response = call('mesh.query', {'object_id':obj[UUID_PROPERTY], 'element_type':element,
                                 'selectors':selectors, 'space':space})
    assert response['success'], response
    result = response['result']
    validate_arguments(result, QUERY_OUTPUT)
    inspected = call('mesh.inspect_selection', {'selection_handle':result['selection_handle']})
    assert inspected['success'], inspected
    validate_arguments(inspected['result'], INSPECT_OUTPUT)
    assert result['matched_count'] == len(inspected['result']['indices'])
    return inspected['result']


def count(obj, element, kind, expected, **parameters):
    result = query(obj, element, [{'kind':kind, **parameters}])
    assert result['matched_count'] == expected, (kind, result)
    return result


# Exact selection benchmark: every endpoint of four edges lies on the top plane.
top = count(cube, 'EDGE', 'top', 4)
assert all(all(cube.data.vertices[v].co.z == 1 for v in cube.data.edges[i].vertices)
           for i in top['indices'])
up = count(cube, 'FACE', 'normal_direction', 1, direction=[0,0,1], angle_degrees=0)
assert cube.data.polygons[up['indices'][0]].normal.z == 1
count(cube, 'EDGE', 'dihedral_angle', 12, minimum=40, maximum=180)
count(cube, 'FACE', 'height_range', 1, minimum=.5, maximum=1)
count(cube, 'FACE', 'cap_faces', 2)
count(cube, 'FACE', 'side_faces', 4)
count(cube, 'EDGE', 'boundary', 0)
count(plane, 'EDGE', 'outer_boundary', 4)
count(plane, 'EDGE', 'manifold', 0)
count(branch, 'EDGE', 'non_manifold', len(branch.data.edges))
count(branch, 'FACE', 'connected_to', 3, seed_index=0)
count(branch, 'VERTEX', 'connected_to', 2, seed_index=5)
assert query(cube, 'EDGE', [{'kind':'top'}, {'kind':'front'}])['matched_count'] == 1
count(cube, 'VERTEX', 'nearest_point', 8, point=[0,0,0])
count(cube, 'EDGE', 'length_range', 12, minimum=2, maximum=2)
count(cube, 'FACE', 'area_range', 6, minimum=4, maximum=4)
count(cube, 'FACE', 'within_bbox', 1, min=[-1,-1,1], max=[1,1,1])

# Modifiers do not expand base selections, change UI selection or allocate mesh data.
mesh_count = len(bpy.data.meshes)
selection_before = [v.select for v in cube.data.vertices]
array = cube.modifiers.new('Array', 'ARRAY')
array.count = 3
count(cube, 'EDGE', 'top', 4)
assert selection_before == [v.select for v in cube.data.vertices]
assert len(bpy.data.meshes) == mesh_count
assert api.state.revision == 0

# Transform-aware world/local selectors, negative scale and area scaling.
old = top['selection_handle']
cube.scale = (2,3,-4)
cube.location = (10,20,30)
bpy.context.view_layer.update()
assert call('mesh.inspect_selection', {'selection_handle':old})['error']['code'] == 'STALE_SELECTION'
world = count(cube, 'FACE', 'top', 1)
assert cube.data.polygons[world['indices'][0]].normal.z == -1
local = query(cube, 'FACE', [{'kind':'top'}], space='LOCAL')
assert cube.data.polygons[local['indices'][0]].normal.z == 1
count(cube, 'EDGE', 'length_range', 4, minimum=4, maximum=4)
count(cube, 'FACE', 'area_range', 2, minimum=24, maximum=24)
cube.rotation_euler.y = math.pi/2
count(cube, 'FACE', 'normal_direction', 1, direction=[0,0,1], angle_degrees=.01)

# Vertex edits invalidate handles even when topology counts do not change.
token = query(plane, 'EDGE', [{'kind':'boundary'}])['selection_handle']
plane.data.vertices[0].co.x += .1
assert call('mesh.inspect_selection', {'selection_handle':token})['error']['code'] == 'STALE_SELECTION'
# Actual topology edit likewise invalidates.
token = query(plane, 'EDGE', [{'kind':'boundary'}])['selection_handle']
plane.data.clear_geometry()
assert call('mesh.inspect_selection', {'selection_handle':token})['error']['code'] == 'STALE_SELECTION'
count(plane, 'FACE', 'top', 0)

# Wrong type, object mode, scene membership, unknown handle and malformed arguments.
light = bpy.data.objects['Light']
assert call('mesh.query', {'object_id':light[UUID_PROPERTY], 'element_type':'FACE',
                          'selectors':[{'kind':'top'}]})['error']['code'] == 'OBJECT_NOT_MESH'
assert call('mesh.inspect_selection', {'selection_handle':'bogus'})['error']['code'] == 'INVALID_SELECTION_HANDLE'
assert call('mesh.query', {'object_id':cube[UUID_PROPERTY], 'element_type':'EDGE',
                          'selectors':[{'kind':'normal_direction','direction':[0,0,1]}]})['error']['code'] == 'INVALID_ARGUMENT'
bpy.context.view_layer.objects.active = cube
bpy.ops.object.mode_set(mode='EDIT')
assert call('mesh.query', {'object_id':cube[UUID_PROPERTY], 'element_type':'FACE',
                          'selectors':[{'kind':'top'}]})['error']['code'] == 'UNSUPPORTED_OBJECT_MODE'
bpy.ops.object.mode_set(mode='OBJECT')
token = query(branch, 'FACE', [{'kind':'top'}])['selection_handle']
bpy.context.scene.collection.objects.unlink(branch)
assert call('mesh.inspect_selection', {'selection_handle':token})['error']['code'] == 'OBJECT_NOT_IN_SCENE'
bpy.context.scene.collection.objects.link(branch)
token = query(branch, 'FACE', [{'kind':'top'}])['selection_handle']
bpy.data.objects.remove(branch, do_unlink=True)
assert call('mesh.inspect_selection', {'selection_handle':token})['error']['code'] == 'OBJECT_NOT_FOUND'

# Revision invalidation uses the same public dispatcher that future mutations use.
token = query(cube, 'FACE', [{'kind':'top'}])['selection_handle']
api.registry.register(ToolSpec('fixture.mutate', 'Test mutation', side_effects=('scene_change',)),
                      lambda args: setattr(cube, 'location', (0,0,0)) or {})
assert call('fixture.mutate', {})['success']
assert api.state.revision == 1
assert call('mesh.inspect_selection', {'selection_handle':token})['error']['code'] == 'INVALID_SELECTION_HANDLE'
print('BAR_SELECTION_HEADLESS_OK')
