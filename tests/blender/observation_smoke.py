"""Pixel content, framing, cleanup, and recovery for actual diagnostic renders."""
import base64
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest.mock import patch
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from runtime.api import RuntimeAPI
from runtime.logging import EventLogger
from runtime.observation import CAMERA_OUTPUT, RENDER_OUTPUT, DEFAULT_VIEWS
from runtime.schemas import validate_arguments
import runtime.observation as observation

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
    scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
    depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True, observation=True,
    logger=EventLogger(io.StringIO()))

def call(tool, args=None, error=None):
    before = api.state.revision
    r = api.execute({'api_version':'1.0','session_id':api.state.session_id,'expected_revision':before,
        'tool':tool,'arguments':args or {}})
    if error:
        assert not r['success'] and r['error']['code'] == error, r
    else:
        assert r['success'], {k:v for k,v in r.items() if k != 'result'}
        if tool.startswith('observe.'):
            assert r['revision_before'] == r['revision_after'] == before
            assert not (r['created_ids'] or r['modified_ids'] or r['deleted_ids'])
            validate_arguments(r['result'], CAMERA_OUTPUT if tool == 'observe.camera' else RENDER_OUTPUT)
    return r.get('result') if error is None else r

def pixels(image):
    data = base64.b64decode(image['png_base64'],validate=True)
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) == image['byte_count']
    assert b'Date\x00' not in data and b'File\x00' not in data
    assert struct.unpack('>II',data[16:24]) == (image['camera']['width'],image['camera']['height'])
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'check.png'
        path.write_bytes(data)
        loaded = bpy.data.images.load(str(path),check_existing=False)
        try:
            return list(loaded.pixels[:])
        finally:
            bpy.data.images.remove(loaded)

cube = bpy.data.objects['Cube']
oid = cube['bar_uuid']
args = {'object_ids':[oid], 'view':'front', 'width':96, 'height':64}
# Deliberately hostile source rendering settings must have no effect on diagnostics.
bpy.context.scene.render.resolution_x = 111
bpy.context.scene.render.resolution_percentage = 17
bpy.context.scene.render.film_transparent = True
bpy.context.scene.render.use_border = True
bpy.context.scene.render.filepath = '/do/not/write/here'
bpy.context.scene.view_settings.exposure = 3
bpy.context.scene.frame_set(7)
cube.display_type = 'WIRE'
cube.show_in_front = True
# Keep factory-startup orphan materials in the saved recovery baseline.
for material in bpy.data.materials:
    if not material.users:
        material.use_fake_user = True

def source_state():
    scene, layer = bpy.context.scene, bpy.context.view_layer
    return (scene.as_pointer(), scene.camera.as_pointer(), layer.objects.active.as_pointer(),
        tuple(obj.as_pointer() for obj in bpy.context.selected_objects), scene.frame_current,
        scene.render.engine, scene.render.resolution_x, scene.render.resolution_y,
        scene.render.resolution_percentage, scene.render.filepath, scene.render.use_border,
        scene.render.film_transparent, scene.view_settings.exposure,
        cube.data.as_pointer(), tuple(cube.matrix_world[0]), cube.display_type, cube.show_in_front,
        tuple((name,len(getattr(bpy.data,name))) for name in
              ('objects','meshes','curves','cameras','lights','worlds','scenes','materials')))

before = source_state()
handle = call('mesh.query', {'object_id':oid,'element_type':'FACE','selectors':[{'kind':'top'}]})['selection_handle']
page = call('scene.list_objects',{'limit':1})
transaction = call('transaction.begin')
transaction_args = {'transaction_id': transaction['transaction_id']}
# Transaction begin expires old handles; capture new ones for render preservation.
handle = call('mesh.query', {'object_id':oid,'element_type':'FACE','selectors':[{'kind':'top'}]})['selection_handle']
page = call('scene.list_objects',{'limit':1})
camera = call('observe.camera',args)
assert camera['bounds'] == {'min':[-1,-1,-1], 'max':[1,1,1]}
assert camera == call('observe.camera',args)
solid = call('observe.render',args)
assert source_state() == before
assert solid['images'][0]['camera'] == camera['camera']
# Fixed width/height and pixel content: foreground occupies a framed region.
p = pixels(solid['images'][0])
assert max(p[::4]) - min(p[::4]) > .1
repeat = call('observe.render',args)
assert pixels(repeat['images'][0]) == pixels(solid['images'][0])
assert repeat['images'][0]['png_base64'] == solid['images'][0]['png_base64']
silhouette = call('observe.render',{**args,'mode':'silhouette'})
p = pixels(silhouette['images'][0])
assert min(p[::4]) == 0 and max(p[::4]) == 1
assert p[:3] == [1,1,1] and p[(32*96+48)*4:(32*96+48)*4+3] == [0,0,0], (p[:3],p[(32*96+48)*4:(32*96+48)*4+3])
wire = call('observe.render',{**args,'mode':'wireframe'})
p = pixels(wire['images'][0])
assert min(p[::4]) < .1 and max(p[::4]) == 1
# Wireframe leaves a white centre where silhouette contains the solid face.
assert p[(32*96+48)*4:(32*96+48)*4+3] == [1,1,1]
multi = call('observe.render_multiview',{'object_ids':[oid], 'width':64, 'height':64})
assert [image['camera']['view'] for image in multi['images']] == list(DEFAULT_VIEWS)
for image in multi['images']:
    assert max(pixels(image)[::4]) - min(pixels(image)[::4]) > .1
bottom = call('observe.render',{**args,'view':'bottom'})
assert bottom['images'][0]['camera']['projection'] == 'ORTHO'
assert call('scene.diff',transaction_args)['diff']['modified_ids'] == []
call('mesh.inspect_selection',{'selection_handle':handle})
call('scene.list_objects',{'limit':1,'cursor':page['next_cursor']})
assert source_state() == before
assert not list(Path(os.environ['BAR_RECOVERY_ROOT']).glob('bar-observation-*'))
# Rejected and failed attempts are read-only, clean up, and retain their transaction.
for tool, arguments, error in (
    ('observe.render',{'view':'invalid'},'INVALID_ARGUMENT'),
    ('observe.render_multiview',{'views':['front','front']},'INVALID_ARGUMENT'),
    ('observe.render_multiview',{'width':768,'height':768},'OBSERVATION_LIMIT_EXCEEDED'),
    ('observe.render',{'engine':'EEVEE','mode':'silhouette'},'INVALID_ARGUMENT'),
    ('observe.camera',{'object_ids':[oid,oid]},'INVALID_ARGUMENT'),
    ('observe.camera',{'object_ids':[str(uuid.uuid4())]},'OBJECT_NOT_FOUND'),
    ('observe.camera',{'object_ids':[bpy.data.objects['Camera']['bar_uuid']]},'UNSUPPORTED_OBJECT_TYPE')):
    call(tool,arguments,error=error)
    assert source_state() == before
with patch.object(observation,'MAX_RENDER_BYTES',1):
    call('observe.render',args,error='RESPONSE_TOO_LARGE')
assert source_state() == before
assert not list(Path(os.environ['BAR_RECOVERY_ROOT']).glob('bar-observation-*'))
with patch.object(api.observation,'_write_render', side_effect=RuntimeError('private traceback')):
    r = call('observe.render',args,error='RENDER_FAILED')
    assert 'private traceback' not in str(r)
assert source_state() == before
# Bounds reflect modifiers and transforms, not the base mesh or current camera.
modifier = cube.modifiers.new('evaluated geometry','SOLIDIFY')
modifier.thickness = .2
modifier.offset = 1
cube.location = (4,5,6)
bpy.context.view_layer.update()
assert call('observe.camera',args)['bounds']['max'][2] > 7
cube.hide_render = True
call('observe.camera',args,error='OBJECT_NOT_VISIBLE')
call('observe.camera',error='EMPTY_OBSERVATION')
cube.hide_render = False
with patch.object(observation,'MAX_OBSERVATION_ELEMENTS',1):
    call('observe.camera',args,error='OBSERVATION_LIMIT_EXCEEDED')
with patch.object(observation,'MAX_OBSERVATION_OBJECTS',0):
    call('observe.camera',args,error='OBSERVATION_LIMIT_EXCEEDED')
# Source state is restored with original UUID and the service re-resolves it.
call('transaction.rollback',transaction_args)
cube = api.identities.resolve(oid)
assert call('observe.camera',args)['bounds'] == camera['bounds']
assert source_state()[-1] == before[-1], (source_state()[-1],before[-1])
# Edit mode rejection also leaves the scene intact.
bpy.context.view_layer.objects.active = cube
bpy.ops.object.mode_set(mode='EDIT')
call('observe.render',args,error='UNSUPPORTED_OBJECT_MODE')
bpy.ops.object.mode_set(mode='OBJECT')
# Identity, membership, visibility, empty geometry and instance preflight.
cube.hide_set(True)
call('observe.camera',args,error='OBJECT_NOT_VISIBLE')
cube.hide_set(False)
orphan = bpy.data.objects.new('outside active scene',cube.data)
orphan_id = api.identities.ensure(orphan)
call('observe.camera',{'object_ids':[orphan_id]},error='OBJECT_NOT_IN_SCENE')
bpy.data.objects.remove(orphan,do_unlink=True)
duplicate = cube.copy()
call('observe.camera',args,error='UUID_COLLISION')
bpy.data.objects.remove(duplicate,do_unlink=True)
unmanaged = bpy.data.objects.new('unmanaged mesh',cube.data)
bpy.context.scene.collection.objects.link(unmanaged)
call('observe.camera',error='OBJECT_NOT_MANAGED')
bpy.data.objects.remove(unmanaged,do_unlink=True)
empty_mesh = bpy.data.meshes.new('empty observation mesh')
empty = bpy.data.objects.new('empty observation object',empty_mesh)
bpy.context.scene.collection.objects.link(empty)
empty_id = api.identities.ensure(empty)
call('observe.camera',{'object_ids':[empty_id]},error='EMPTY_OBSERVATION')
bpy.data.objects.remove(empty,do_unlink=True)
bpy.data.meshes.remove(empty_mesh)
child = bpy.data.objects.new('instanced child',cube.data)
bpy.context.scene.collection.objects.link(child)
api.identities.ensure(child)
child.parent = cube
cube.instance_type = 'VERTS'
call('observe.camera',args,error='UNSUPPORTED_INSTANCING')
cube.instance_type = 'NONE'
bpy.data.objects.remove(child,do_unlink=True)
assert source_state()[-1] == before[-1]
# Optional appearance rendering uses copied evaluated materials and deterministic lights.
material = bpy.data.materials.new('red test material')
material.use_nodes = True
material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (1,0,0,1)
cube.data.materials.clear()
cube.data.materials.append(material)
counts = source_state()[-1]
e = call('observe.render',{**args,'width':32,'height':32,'engine':'EEVEE'})
p = pixels(e['images'][0])
assert any(r > g*2 and r > .05 for r,g in zip(p[::4],p[1::4]))
assert source_state()[-1] == counts
api.close()
print('BAR_OBSERVATION_HEADLESS_OK')
