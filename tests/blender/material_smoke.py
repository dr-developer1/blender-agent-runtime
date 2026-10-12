"""Basic PBR creation, independent assignment and checkpoint conformance."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from runtime.api import RuntimeAPI
from runtime.materials import MATERIAL_UUID_PROPERTY

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
                 scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
                 depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True)

def call(tool, args=None, error=None):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                            'expected_revision': api.state.revision, 'tool': tool,
                            'arguments': args or {}})
    if error:
        assert not response['success'] and response['error']['code'] == error, response
    else:
        assert response['success'], response
    return response

assert call('runtime.get_supported_features')['result']['basic_materials']
for tool in ('material.create', 'material.assign'):
    assert call('runtime.describe_tool', {'name': tool})['result']['transaction_safe']
active, selected = bpy.context.view_layer.objects.active, list(bpy.context.selected_objects)
revision = api.state.revision
for args in ({'roughness': -1}, {'metallic': True}, {'base_color': [1, 0, 0]},
             {'base_color': [1, 0, 0, 2]}, {'roughness': float('nan')}):
    call('material.create', args, 'INVALID_ARGUMENT')
assert api.state.revision == revision
created = call('material.create', {'name': 'Wood', 'base_color': [.22, .08, .025, 1],
                                   'roughness': .65, 'metallic': .1})
mid = created['result']['material_id']
assert created['created_ids'] == []  # Envelope IDs always identify objects.
mat = api.materials.resolve(mid)
mat.name = 'Renamed'
assert mat.use_fake_user
nodes = mat.node_tree.nodes
shader = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
assert abs(shader.inputs['Roughness'].default_value - .65) < 1e-6
assert abs(shader.inputs['Metallic'].default_value - .1) < 1e-6
assert all(abs(a-b) < 1e-6 for a,b in zip(shader.inputs['Base Color'].default_value, [.22,.08,.025,1]))
assert any(l.from_node == shader and l.to_node.type == 'OUTPUT_MATERIAL' for l in mat.node_tree.links)
# Bounded procedural finishes use generated coordinates, with explicit grain axes.
procedural_ids = []
for surface in ('wood','coated_metal','ceramic','polymer'):
    args = {'surface':surface,'base_color':[.25,.12,.04,1],'roughness':.4}
    if surface == 'wood':
        args['grain_axis']='Z'
    response=call('material.create',args)['result']
    assert response['surface']==surface
    procedural_ids.append(response['material_id'])
    material=api.materials.resolve(response['material_id'])
    shader=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    assert shader.inputs['Base Color'].is_linked
    assert shader.inputs['Roughness'].is_linked and shader.inputs['Normal'].is_linked
    mapping=next(n for n in material.node_tree.nodes if n.type=='VECT_MATH')
    if surface=='wood':
        assert response['grain_axis']=='Z'
        assert abs(mapping.inputs[1].default_value[2]-1.2)<1e-6
        assert mapping.inputs[1].default_value[0]==18
    assert any(l.from_socket.name=='Generated' for l in material.node_tree.links)
count=len(bpy.data.materials)
for args in ({'surface':'glass'},{'surface':'wood','grain_axis':'invalid'},
             {'surface':'polymer','grain_axis':'X'},{'grain_axis':'Z'}):
    call('material.create',args,'INVALID_ARGUMENT')
assert len(bpy.data.materials)==count
# A recipe failure cleans its newly allocated material before publication.
from unittest.mock import patch
with patch.object(api.materials,'_surface',side_effect=RuntimeError('injected recipe failure')):
    call('material.create',{'surface':'wood'},'INTERNAL_ERROR')
assert len(bpy.data.materials)==count
cube = call('object.create_primitive', {'primitive': 'CUBE'})['result']['object_id']
linked = call('object.duplicate', {'object_id': cube, 'linked_data': True})['result']['object_id']
original_mesh = api.identities.resolve(cube).data
handle = call('mesh.query', {'object_id': cube, 'element_type': 'FACE',
                            'selectors': [{'kind': 'top'}]})['result']['selection_handle']
tx = {'transaction_id': call('transaction.begin')['result']['transaction_id']}
assigned = call('material.assign', {'object_id': cube, 'material_id': mid})
assert assigned['modified_ids'] == [cube]
obj = api.identities.resolve(cube)
assert obj.data != original_mesh and api.identities.resolve(linked).data == original_mesh
assert len(obj.material_slots) == 1 and obj.material_slots[0].material == mat
assert all(p.material_index == 0 for p in obj.data.polygons)
assert not api.identities.resolve(linked).material_slots
assert bpy.context.view_layer.objects.active == active
assert list(bpy.context.selected_objects) == selected
assert call('validate.asset', {'object_ids': [cube], 'require_materials': True})['result']['passed']
assert cube in call('scene.diff', tx)['result']['diff']['modified_ids']
call('mesh.inspect_selection', {'selection_handle': handle}, 'INVALID_SELECTION_HANDLE')
call('transaction.rollback', tx)
assert not api.identities.resolve(cube).material_slots
for procedural_id in procedural_ids:
    material=api.materials.resolve(procedural_id)
    assert any(n.type=='TEX_NOISE' for n in material.node_tree.nodes)
assert api.materials.resolve(mid).name == 'Renamed'
# Unassigned materials survive save/load; materials created after begin disappear.
tx = {'transaction_id': call('transaction.begin')['result']['transaction_id']}
new_mid = call('material.create', {'surface':'wood','grain_axis':'Y'})['result']['material_id']
call('material.assign', {'object_id': cube, 'material_id': new_mid})
call('transaction.rollback', tx)
call('material.assign', {'object_id': cube, 'material_id': new_mid}, 'MATERIAL_NOT_FOUND')
call('material.assign', {'object_id': cube, 'material_id': mid})
# Reassigning replaces slots; duplicate UUIDs reject without writes.
mat = api.materials.resolve(mid)
collision = mat.copy()
call('material.assign', {'object_id': cube, 'material_id': mid}, 'MATERIAL_ID_COLLISION')
bpy.data.materials.remove(collision)
call('material.assign', {'object_id': cube, 'material_id': mid})
assert len(api.identities.resolve(cube).material_slots) == 1
# A failure after publication restores data and object-linked material overrides.
from unittest.mock import Mock
obj = api.identities.resolve(cube)
other = bpy.data.materials.new('Other')
obj.data.materials.append(other)
obj.material_slots[0].link = 'OBJECT'
obj.material_slots[0].material = other
obj.active_material_index = 1
old_mesh = obj.data
mesh_count = len(bpy.data.meshes)
provider = api.objects.view_layer
failing_layer = Mock()
failing_layer.update.side_effect = [None, RuntimeError('injected update failure')]
api.objects.view_layer = lambda: failing_layer
call('material.assign', {'object_id': cube, 'material_id': mid}, 'INTERNAL_ERROR')
api.objects.view_layer = provider
assert obj.data == old_mesh and len(bpy.data.meshes) == mesh_count
assert obj.material_slots[0].link == 'OBJECT' and obj.material_slots[0].material == other
assert obj.active_material_index == 1
call('material.assign', {'object_id': cube, 'material_id': mid})
assert len(obj.material_slots) == 1 and obj.material_slots[0].link == 'DATA'
assert obj.material_slots[0].material == api.materials.resolve(mid)
assert obj.active_material_index == 0
camera = next(o for o in bpy.data.objects if o.type == 'CAMERA')
call('material.assign', {'object_id': camera['bar_uuid'], 'material_id': mid}, 'UNSUPPORTED_OBJECT_TYPE')
obj = api.identities.resolve(cube)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
call('material.create', {}, 'UNSUPPORTED_OBJECT_MODE')
call('material.assign', {'object_id': cube, 'material_id': mid}, 'UNSUPPORTED_OBJECT_MODE')
bpy.ops.object.mode_set(mode='OBJECT')
obj.select_set(False)
bpy.context.view_layer.objects.active = None
api.close()
print('BAR_MATERIAL_HEADLESS_OK')
