"""Deterministic large-scene accuracy and bounded performance acceptance fixture."""
from pathlib import Path
import json
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.identity import UUID_PROPERTY
from runtime.schemas import validate_response, validate_arguments

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
collection = bpy.context.scene.collection
for index in range(2000):
    obj = bpy.data.objects.new(f'Fixture_{index:04d}', None)
    collection.objects.link(obj)
    obj.location = (index, 0, 0)
    obj['bar_tags'] = {'parity': 'even' if index % 2 == 0 else 'odd'}
    obj.hide_render = index % 2 == 0
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
    scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
    depsgraph=lambda: bpy.context.evaluated_depsgraph_get(), object_control=True)
measurements = {}


def call(tool, args=None):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
        'expected_revision': api.state.revision, 'tool': tool, 'arguments': args or {}})
    validate_response(response)
    assert response['success'], response
    validate_arguments(response['result'], api.registry.describe(tool)['output_schema'])
    return response['result']


def timed(name, action, budget=30):
    started = time.perf_counter()
    result = action()
    elapsed = time.perf_counter() - started
    measurements[name] = {'seconds': elapsed, 'budget_seconds': budget}
    assert elapsed < budget, (name, elapsed, budget)
    return result


def pages(tool, filters=None):
    args = {'limit': 100, **(filters or {})}
    rows = []
    while True:
        result = call(tool, args)
        page = result['nodes' if tool == 'scene.get_hierarchy' else 'objects']
        assert len(page) <= 100
        rows.extend(page)
        if result['next_cursor'] is None:
            break
        args['cursor'] = result['next_cursor']
    ids = [row['object_id'] for row in rows]
    assert ids == sorted(set(ids))
    return rows


try:
    summary = timed('summary_2001', lambda: call('scene.summary'))
    assert summary['object_count'] == 2001
    assert summary['object_types'] == {'EMPTY': 2000, 'MESH': 1}
    assert summary['render_enabled_count'] == 1001
    rows = timed('pagination_2001', lambda: pages('scene.list_objects'))
    assert len(rows) == 2001
    assert {row['object_id']: row['name'] for row in rows} == {
        obj[UUID_PROPERTY]: obj.name for obj in bpy.context.scene.objects}
    even = timed('filtered_pagination_1000', lambda: pages('scene.list_objects',
        {'object_type': 'EMPTY', 'tags': {'parity': 'even'}}))
    assert {row['name'] for row in even} == {f'Fixture_{i:04d}' for i in range(0, 2000, 2)}
    hierarchy = timed('hierarchy_2001', lambda: pages('scene.get_hierarchy'))
    assert len(hierarchy) == 2001 and all(row['parent_id'] is None for row in hierarchy)
    inspected = timed('inspect_100', lambda: call('scene.inspect_objects',
        {'object_ids': [row['object_id'] for row in even[:100]]}))
    assert len(inspected['objects']) == 100
    for row in inspected['objects']:
        index = int(row['name'].split('_')[1])
        assert row['world_origin'] == [float(index), 0.0, 0.0]
        assert row['evaluated_dimensions'] is None
    assert api.state.revision == 0
    rejected = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
        'expected_revision': api.state.revision, 'tool': 'transaction.begin', 'arguments': {}})
    validate_response(rejected)
    assert rejected['error']['code'] == 'RECOVERY_LIMIT_EXCEEDED'
    assert api.recovery.active is None
    # Recovery explicitly supports at most 1,000 objects; inspection has a wider scope.
    for obj in list(bpy.data.objects):
        if obj.type == 'EMPTY' and int(obj.name.split('_')[1]) >= 999:
            bpy.data.objects.remove(obj, do_unlink=True)
    assert call('scene.summary')['object_count'] == 1000
    rejected = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
        'expected_revision': api.state.revision, 'tool': 'transaction.begin', 'arguments': {}})
    validate_response(rejected)
    assert rejected['error']['code'] == 'RESPONSE_TOO_LARGE'
    assert api.recovery.active is None
    # Full snapshots also have a byte budget, so count alone does not imply support.
    for obj in list(bpy.data.objects):
        if obj.type == 'EMPTY' and int(obj.name.split('_')[1]) >= 249:
            bpy.data.objects.remove(obj, do_unlink=True)
    assert call('scene.summary')['object_count'] == 250
    cube_id = bpy.data.objects['Cube'][UUID_PROPERTY]
    baseline = call('scene.inspect_objects', {'object_ids': [cube_id]})
    session = api.state.session_id

    def recover():
        for index in range(5):
            transaction = call('transaction.begin')
            checkpoint = api.recovery.active.path
            args = {'transaction_id': transaction['transaction_id']}
            call('object.transform', {'object_id': cube_id, 'location': [index + 10, 0, 1]})
            handle = call('mesh.query', {'object_id': cube_id, 'element_type': 'FACE',
                'selectors': [{'kind': 'top'}]})
            assert handle['matched_count'] == 1
            call('mesh.extrude', {'selection_handle': handle['selection_handle'], 'offset': [0, 0, .25]})
            created = call('object.duplicate', {'object_id': cube_id})['object_id']
            diff = call('scene.diff', args)['diff']
            assert diff['modified_ids'] == [cube_id] and diff['created_ids'] == [created]
            before = api.state.revision
            call('transaction.rollback', args)
            assert api.state.revision == before + 1 and api.state.session_id == session
            assert call('scene.inspect_objects', {'object_ids': [cube_id]}) == baseline
            assert call('scene.summary')['object_count'] == 250
            assert not checkpoint.exists()

    timed('five_full_file_rollbacks_250', recover)
    print('BAR_CONFORMANCE_METRICS ' + json.dumps({'blender_version': bpy.app.version_string,
        'object_count': 2001, 'recovery_object_count': 250,
        'rollback_cycles': 5, 'measurements': measurements}, sort_keys=True))
finally:
    api.close()
print('BAR_CONFORMANCE_STRESS_OK')
