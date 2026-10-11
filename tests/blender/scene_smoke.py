"""Scene observation acceptance checks against real Blender data and view layers."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.identity import UUID_PROPERTY
from runtime.schemas import validate_response

scene = bpy.context.scene
parts = bpy.data.collections.new('Parts')
scene.collection.children.link(parts)
excluded = bpy.data.collections.new('Excluded')
scene.collection.children.link(excluded)
for i in range(253):
    obj = bpy.data.objects.new(f'Part_{i:03d}', None)
    parts.objects.link(obj)
    obj.location = (i, 0, 0)
    obj['bar_tags'] = {'role': 'even' if i % 2 == 0 else 'odd', 'batch': 'fixture'}
    obj.hide_render = i % 2 == 0
hidden = bpy.data.objects.new('Excluded object', None)
excluded.objects.link(hidden)
bpy.context.view_layer.layer_collection.children['Excluded'].exclude = True
api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
                 scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
                 depsgraph=lambda: bpy.context.evaluated_depsgraph_get())


def call(tool='scene.list_objects', arguments=None):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                            'expected_revision': api.state.revision, 'tool': tool,
                            'arguments': {} if arguments is None else arguments})
    validate_response(response)
    return response


def plain(value):
    if hasattr(value, 'items'):
        return {key: plain(item) for key, item in value.items()}
    if hasattr(value, 'to_list'):
        return value.to_list()
    return value


before = {obj[UUID_PROPERTY]: (obj.name, plain(obj)) for obj in bpy.data.objects}
summary = call('scene.summary')['result']
assert summary['object_count'] == 257, summary
assert summary['object_types'] == {'CAMERA': 1, 'EMPTY': 254, 'LIGHT': 1, 'MESH': 1}
assert summary['collection_count'] == 4
assert summary['visible_count'] == 256
assert summary['render_enabled_count'] == 130

filters = {'collection': 'Parts', 'object_type': 'EMPTY', 'visible': True,
           'name_pattern': 'Part_*', 'tags': {'batch': 'fixture'}}
arguments = {**filters, 'limit': 100}
collected = []
while True:
    page = call(arguments=arguments)['result']
    assert len(page['objects']) <= 100
    assert page['total'] == 253
    collected.extend(page['objects'])
    if page['next_cursor'] is None:
        break
    arguments['cursor'] = page['next_cursor']
assert len(collected) == len({row['object_id'] for row in collected}) == 253
assert [row['object_id'] for row in collected] == sorted(row['object_id'] for row in collected)
for row in collected:
    assert api.identities.resolve(row['object_id']).name == row['name']
spatial = call(arguments={'region': {'min': [10, 0, 0], 'max': [14, 0, 0]},
                          'tags': {'role': 'even'}})['result']
assert {row['name'] for row in spatial['objects']} == {'Part_010', 'Part_012', 'Part_014'}
assert [row['name'] for row in call(arguments={'visible': False})['result']['objects']] == ['Excluded object']
assert call(arguments={'name_pattern': 'missing*'})['result']['objects'] == []
assert call('scene.inspect_objects', {'object_ids': [hidden[UUID_PROPERTY]]})['error']['code'] == 'OBJECT_NOT_EVALUATED'
assert api.state.revision == 0
assert before == {obj[UUID_PROPERTY]: (obj.name, plain(obj)) for obj in bpy.data.objects}

cursor = call(arguments={'collection': 'Parts', 'limit': 1})['result']['next_cursor']
assert call(arguments={'collection': 'Parts', 'cursor': cursor + 'x'})['error']['code'] == 'INVALID_CURSOR'
assert call(arguments={'cursor': cursor})['error']['code'] == 'INVALID_CURSOR'
bpy.data.objects['Part_000'].name = 'Renamed part'
assert call(arguments={'collection': 'Parts', 'cursor': cursor})['error']['code'] == 'STALE_SCENE_STATE'

cursor = call(arguments={'limit': 1})['result']['next_cursor']
api.registry.register(ToolSpec('test.edit', 'Mutation fixture', side_effects=('scene',)), lambda args: {})
assert call('test.edit')['revision_after'] == 1
assert call(arguments={'cursor': cursor})['error']['code'] == 'STALE_SCENE_STATE'
assert call('scene.summary')['success']

# Orphans and objects in other scenes are not included in active-scene listing.
orphan = bpy.data.objects.new('Orphan', None)
api.identities.ensure(orphan)
other_scene = bpy.data.scenes.new('Other scene')
other = bpy.data.objects.new('Other scene object', None)
other_scene.collection.objects.link(other)
api.identities.ensure(other)
assert call('scene.summary')['result']['object_count'] == 257
print('BAR_SCENE_HEADLESS_OK')
