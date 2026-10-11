"""Core mesh operation correctness through the public dispatcher."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import bmesh
from runtime.api import RuntimeAPI

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
    scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
    depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True)

def call(tool, args=None, error=None):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
        'expected_revision': api.state.revision, 'tool': tool, 'arguments': args or {}})
    if error:
        assert not response['success'] and response['error']['code'] == error, response
    else:
        assert response['success'], response
    return response

def create(kind='CUBE', **kwargs):
    oid = call('object.create_primitive', {'primitive': kind, **kwargs})['result']['object_id']
    return oid, api.identities.resolve(oid)

def select(oid, kind='FACE', selector=None):
    return call('mesh.query', {'object_id': oid, 'element_type': kind,
        'selectors': [selector or {'kind': 'top'}]})['result']['selection_handle']

def solid(obj, volume):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        assert all(e.is_manifold for e in bm.edges), obj.name
        assert all(f.calc_area() > 1e-8 for f in bm.faces)
        actual = bm.calc_volume(signed=True)
        assert abs(actual - volume) < 1e-4, (actual, volume)
    finally:
        bm.free()

active = bpy.context.view_layer.objects.active
selected = list(bpy.context.selected_objects)
# Extrusion replaces the cap and produces a watertight, outward-wound solid.
oid, obj = create()
linked_id = call('object.duplicate', {'object_id': oid, 'linked_data': True})['result']['object_id']
linked = api.identities.resolve(linked_id)
old_mesh = linked.data
handle = select(oid)
revision = api.state.revision
response = call('mesh.extrude', {'selection_handle': handle, 'offset': [0, 0, 500], 'unit': 'mm'})
assert response['modified_ids'] == [oid] and response['revision_after'] == revision + 1
assert obj.data != old_mesh and linked.data == old_mesh
solid(obj, 10)
assert abs(obj.dimensions.z - 2.5) < 1e-5
call('mesh.inspect_selection', {'selection_handle': handle}, error='INVALID_SELECTION_HANDLE')
# Insets preserve volume, add a four-sided border and interpolate mesh data.
oid, obj = create()
uv = obj.data.uv_layers.new(name='Test UV')
material = bpy.data.materials.new('Test Material')
obj.data.materials.append(material)
for loop in uv.data:
    loop.uv = (.25, .75)
call('mesh.inset', {'selection_handle': select(oid), 'thickness': 200, 'unit': 'mm'})
solid(obj, 8)
assert len(obj.data.polygons) == 10 and obj.data.uv_layers.get('Test UV')
assert obj.data.materials[0] == material
assert all(abs(v.uv.x - .25) < 1e-6 for v in obj.data.uv_layers[0].data)
# Beveling all manifold edges creates rounded corners and reduces solid volume.
oid, obj = create()
call('mesh.bevel', {'selection_handle': select(oid, 'EDGE', {'kind': 'manifold'}),
                    'width': .1, 'segments': 3})
bm = bmesh.new()
bm.from_mesh(obj.data)
assert all(e.is_manifold for e in bm.edges)
assert 7 < bm.calc_volume(signed=True) < 8
bm.free()
assert len(obj.data.polygons) > 6
# Boolean results are baked in target-local coordinates; operand stays intact.
for operation, volume in [('UNION', 12), ('DIFFERENCE', 4), ('INTERSECT', 4)]:
    oid, obj = create(location=[5, 0, 0])
    operand_id, operand = create(location=[6, 0, 0])
    count = len(bpy.data.objects)
    response = call('mesh.boolean', {'object_id': oid, 'operand_id': operand_id, 'operation': operation})
    assert response['modified_ids'] == [oid] and len(bpy.data.objects) == count
    solid(obj, volume)
    solid(operand, 8)
    assert not obj.modifiers and tuple(obj.location) == (5, 0, 0)
# Cleanup welds a seam and corrects inward normals.
oid, obj = create('PLANE')
obj.data.clear_geometry()
obj.data.from_pydata([(0,0,0), (1,0,0), (1,1,0), (0,1,0), (1,0,0), (1,1,0), (2,0,0), (2,1,0)],
    [], [(0,1,2,3), (4,6,7,5)])
call('mesh.cleanup', {'object_id': oid, 'merge_distance': .001})
assert len(obj.data.vertices) == 6 and len(obj.data.edges) == 7
assert all(p.normal.z > .99 for p in obj.data.polygons)
oid, obj = create()
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
bm.to_mesh(obj.data)
bm.free()
call('mesh.cleanup', {'object_id': oid})
solid(obj, 8)
# Handle preflight failures advance once, but never write geometry.
handle = select(oid, 'EDGE')
original = obj.data
revision = api.state.revision
call('mesh.inset', {'selection_handle': handle, 'thickness': .1}, error='INVALID_ARGUMENT')
assert api.state.revision == revision + 1 and obj.data == original
call('mesh.bevel', {'selection_handle': handle, 'width': .1}, error='INVALID_SELECTION_HANDLE')
handle = select(oid, selector={'kind': 'height_range', 'minimum': 10, 'maximum': 11})
call('mesh.extrude', {'selection_handle': handle, 'offset': [0,0,1]}, error='EMPTY_SELECTION')
handle = select(oid)
obj.data.vertices[0].co.x += .01
call('mesh.inset', {'selection_handle': handle, 'thickness': .1}, error='STALE_SELECTION')
assert obj.data == original
# Wrong schemas and stale envelopes reject before handle consumption.
handle = select(oid)
revision = api.state.revision
call('mesh.inset', {'selection_handle': handle, 'thickness': 0}, error='INVALID_ARGUMENT')
assert api.state.revision == revision
response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
    'expected_revision': revision-1, 'tool': 'mesh.inset',
    'arguments': {'selection_handle': handle, 'thickness': .1}})
assert response['error']['code'] == 'STALE_SCENE_STATE' and api.state.revision == revision
call('mesh.inspect_selection', {'selection_handle': handle})
modifier = obj.modifiers.new('Unsupported', 'SUBSURF')
call('mesh.inset', {'selection_handle': handle, 'thickness': .1}, error='UNSUPPORTED_OBJECT_STATE')
assert obj.data == original
obj.modifiers.remove(modifier)
obj.shape_key_add(name='Basis')
call('mesh.cleanup', {'object_id': oid}, error='UNSUPPORTED_OBJECT_STATE')
call('mesh.boolean', {'object_id': linked_id, 'operand_id': linked_id, 'operation': 'UNION'}, error='INVALID_ARGUMENT')
# Output-budget failures discard staged meshes without changing the target.
import runtime.mesh as mesh_module
oid, obj = create()
handle = select(oid, 'EDGE', {'kind': 'manifold'})
original = obj.data
mesh_count = len(bpy.data.meshes)
old_budget = mesh_module.MAX_MESH_ELEMENTS
mesh_module.MAX_MESH_ELEMENTS = 60
try:
    call('mesh.bevel', {'selection_handle': handle, 'width': .1, 'segments': 3},
         error='SELECTION_LIMIT_EXCEEDED')
finally:
    mesh_module.MAX_MESH_ELEMENTS = old_budget
assert obj.data == original and len(bpy.data.meshes) == mesh_count
solid(obj, 8)
# Local edit vectors remain local under nonuniform object scaling.
call('object.transform', {'object_id': oid, 'scale': [1, 2, 3]})
call('mesh.extrude', {'selection_handle': select(oid), 'offset': [0, 0, .5]})
assert abs(obj.dimensions.z - 7.5) < 1e-5
# Boolean empty intersections are valid and temporary objects do not leak.
a, a_obj = create(location=[100, 0, 0])
b, b_obj = create(location=[200, 0, 0])
object_count = len(bpy.data.objects)
call('mesh.boolean', {'object_id': a, 'operand_id': b, 'operation': 'INTERSECT'})
assert not a_obj.data.vertices and len(bpy.data.objects) == object_count
# Edit mode rejects without altering mesh or the active edit session.
bpy.context.view_layer.objects.active = b_obj
b_obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
call('mesh.cleanup', {'object_id': b}, error='UNSUPPORTED_OBJECT_MODE')
assert b_obj.mode == 'EDIT'
bpy.ops.object.mode_set(mode='OBJECT')
b_obj.select_set(False)
bpy.context.view_layer.objects.active = active
assert bpy.context.view_layer.objects.active == active
assert list(bpy.context.selected_objects) == selected
print('BAR_MESH_HEADLESS_OK')
