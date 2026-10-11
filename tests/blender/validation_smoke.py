"""Validation correctness and read-only behavior against actual Blender data."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from runtime.api import RuntimeAPI
from runtime.schemas import validate_arguments
from runtime.identity import UUID_PROPERTY
import runtime.validation as validation

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
    scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
    depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True)

def call(tool, args, error=None):
    before = api.state.revision
    result = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
        'expected_revision': before, 'tool': tool, 'arguments': args})
    if error:
        assert not result['success'] and result['error']['code'] == error, result
    else:
        assert result['success'], result
        if tool.startswith('validate.'):
            assert result['revision_after'] == before and not result['modified_ids'], result
            validate_arguments(result['result'], validation.REPORT_SCHEMA)
    return result

def create(**args):
    oid = call('object.create_primitive', {'primitive': 'CUBE', **args})['result']['object_id']
    return oid, api.identities.resolve(oid)

def findings(oid, **args):
    result = call('validate.geometry', {'object_ids': [oid], **args})['result']
    return result, {c['code']: c for c in result['checks']}

oid, obj = create()
handle = call('mesh.query', {'object_id': oid, 'element_type': 'FACE',
    'selectors': [{'kind': 'top'}]})['result']['selection_handle']
original_data = obj.data
active = bpy.context.view_layer.objects.active
selected = list(bpy.context.selected_objects)
counts = (len(bpy.data.objects), len(bpy.data.meshes))
assert findings(oid)[0]['passed']
call('mesh.inspect_selection', {'selection_handle': handle})
assert obj.data == original_data and counts == (len(bpy.data.objects), len(bpy.data.meshes))
# Defects are successful evaluations with failed findings, not execution failures.
call('object.transform', {'object_id': oid, 'scale': [-1,1,1]})
assert not findings(oid)[1]['NEGATIVE_SCALE']['passed']
obj.scale = (0,1,1)
bpy.context.view_layer.update()
assert not findings(oid)[1]['INVALID_DIMENSIONS']['passed']
call('object.transform', {'object_id': oid, 'scale': [1,1,1]})
# Open geometry is permitted only with an explicit policy.
plane = call('object.create_primitive', {'primitive': 'PLANE'})['result']['object_id']
assert not findings(plane)[0]['passed']
assert findings(plane, require_closed=False)[0]['passed']
# Controlled broken topology contains a seam, loose geometry and a zero-area face.
bad_id, bad = create()
bad.data.clear_geometry()
bad.data.from_pydata([(0,0,0), (1,0,0), (2,0,0), (0,1,0), (0,0,0), (9,9,9), (8,8,8)],
    [(5,6)], [(0,1,2), (4,1,3)])
result, checks = findings(bad_id, require_closed=False)
assert not result['passed']
for code in ('DEGENERATE_FACES', 'LOOSE_EDGES', 'COINCIDENT_VERTICES'):
    assert not checks[code]['passed'], checks
# Duplicate faces and same-direction shared edges are separate diagnostics.
bad.data.clear_geometry()
bad.data.from_pydata([(0,0,0), (1,0,0), (0,1,0)], [], [(0,1,2), (0,1,2)])
_, checks = findings(bad_id, require_closed=False)
assert checks['COINCIDENT_FACES']['details']['count'] == 1
assert checks['INCONSISTENT_WINDING']['details']['count'] == 3
# An empty mesh is reported as a geometry defect.
empty_id, empty = create()
empty.data.clear_geometry()
assert not findings(empty_id)[1]['EMPTY_MESH']['passed']
call('validate.dimensions', {'object_ids': [empty_id], 'expected': [0,0,0]}, error='INVALID_GEOMETRY')
# Nonfinite coordinates yield JSON-safe findings.
bad.data.vertices[0].co.x = float('nan')
assert not findings(bad_id)[1]['NONFINITE_GEOMETRY']['passed']
# Dimensions include modifiers and world transforms, rather than base dimensions.
modifier = obj.modifiers.new('Array', 'ARRAY')
modifier.count = 2
modifier.relative_offset_displace = (1,0,0)
bpy.context.view_layer.update()
assert call('validate.dimensions', {'object_ids': [oid], 'expected': [4000,2000,2000],
    'unit': 'mm', 'tolerance': .01})['result']['passed']
assert not call('validate.dimensions', {'object_ids': [oid], 'expected': [2,2,2]})['result']['passed']
assert findings(oid, geometry='evaluated')[1]['COINCIDENT_VERTICES']['details']['count'] == 4
obj.modifiers.remove(modifier)
call('object.transform', {'object_id': oid, 'rotation': [0,0,45]})
assert call('validate.dimensions', {'object_ids': [oid], 'expected': [2**1.5,2**1.5,2],
    'tolerance': .00001})['result']['passed']
# Relations cover support, ground, overlap, symmetry, count and disconnected parts.
leg_id, leg = create(size=1, location=[0,0,.5])
seat_id, seat = create(size=1, location=[0,0,1.5])
checks = [{'kind': 'ground', 'object_id': leg_id},
    {'kind': 'contact', 'object_id': leg_id, 'other_id': seat_id},
    {'kind': 'support', 'object_id': leg_id, 'other_id': seat_id},
    {'kind': 'no_overlap', 'object_id': leg_id, 'other_id': seat_id},
    {'kind': 'symmetry', 'object_id': leg_id, 'other_id': leg_id, 'axis': 'X'},
    {'kind': 'component_count', 'expected': 2}, {'kind': 'connected'}]
assert call('validate.assembly', {'object_ids': [leg_id, seat_id], 'checks': checks})['result']['passed']
assert not call('validate.assembly', {'object_ids': [leg_id, seat_id], 'checks': [
    {'kind': 'clearance', 'object_id': leg_id, 'other_id': seat_id, 'minimum': 1,
    }], 'unit': 'mm', 'tolerance': 0})['result']['passed']
call('object.transform', {'object_id': seat_id, 'location': [0,0,2]})
assert not call('validate.assembly', {'object_ids': [leg_id, seat_id], 'checks': checks})['result']['passed']
call('object.transform', {'object_id': seat_id, 'location': [0,0,.75]})
assert not call('validate.assembly', {'object_ids': [leg_id, seat_id], 'checks': [
    {'kind': 'no_overlap', 'object_id': leg_id, 'other_id': seat_id}]})['result']['passed']
# Asset validation composes findings and checks actual face material slots.
asset = {'object_ids': [leg_id], 'dimensions': {'expected': [1000,1000,1000], 'unit': 'mm'},
         'assembly': {'checks': [{'kind': 'ground', 'object_id': leg_id}]}, 'require_materials': True}
assert not call('validate.asset', asset)['result']['passed']
material = bpy.data.materials.new('Assigned')
leg.data.materials.append(material)
assert call('validate.asset', asset)['result']['passed']
# Strict errors never advance the timeline or change current selections.
call('validate.geometry', {'object_ids': [leg_id, leg_id]}, error='INVALID_ARGUMENT')
call('validate.geometry', {'object_ids': ['00000000-0000-4000-8000-999999999999']}, error='OBJECT_NOT_FOUND')
call('validate.assembly', {'object_ids': [leg_id], 'checks': [
    {'kind': 'contact', 'object_id': leg_id}]}, error='INVALID_ARGUMENT')
call('validate.geometry', {'object_ids': [bpy.data.objects['Camera'][UUID_PROPERTY]]}, error='OBJECT_NOT_MESH')
old_budget = validation.MAX_VALIDATION_ELEMENTS
validation.MAX_VALIDATION_ELEMENTS = 10
try:
    call('validate.geometry', {'object_ids': [leg_id]}, error='VALIDATION_LIMIT_EXCEEDED')
finally:
    validation.MAX_VALIDATION_ELEMENTS = old_budget
assert counts == (len(bpy.data.objects)-5, len(bpy.data.meshes)-5)
# Collisions are structured resolver errors and must never be silently repaired.
old_id = seat[UUID_PROPERTY]
seat[UUID_PROPERTY] = leg_id
call('validate.geometry', {'object_ids': [leg_id]}, error='UUID_COLLISION')
seat[UUID_PROPERTY] = old_id
bpy.context.view_layer.objects.active = leg
leg.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
call('validate.geometry', {'object_ids': [leg_id]}, error='UNSUPPORTED_OBJECT_MODE')
bpy.ops.object.mode_set(mode='OBJECT')
leg.select_set(False)
bpy.context.view_layer.objects.active = active
assert list(bpy.context.selected_objects) == selected
assert findings(leg_id)[0]['passed']
print('BAR_VALIDATION_HEADLESS_OK')
