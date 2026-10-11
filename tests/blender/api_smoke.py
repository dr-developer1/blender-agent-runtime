"""Verify the public API inside a fresh isolated Blender interpreter."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.schemas import validate_response

api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects,
                 scene=lambda: bpy.context.scene, view_layer=lambda: bpy.context.view_layer,
                 depsgraph=lambda: bpy.context.evaluated_depsgraph_get())
objects_before = tuple(bpy.data.objects)
query_arguments = {'object_id': bpy.data.objects['Cube']['bar_uuid'], 'element_type': 'EDGE',
                   'selectors': [{'kind': 'top'}]}
selection = api.execute({'api_version': '1.0', 'tool': 'mesh.query', 'arguments': query_arguments,
                         'session_id': api.state.session_id, 'expected_revision': api.state.revision})
assert selection['success'], selection
for name in api.registry.names():
    arguments = {'name': name} if name == 'runtime.describe_tool' else {}
    if name == 'scene.inspect_objects':
        arguments = {'object_ids': [bpy.context.scene.objects[0]['bar_uuid']]}
    if name == 'mesh.query':
        arguments = query_arguments
    if name == 'mesh.inspect_selection':
        arguments = {'selection_handle': selection['result']['selection_handle']}
    if name.startswith('validate.'):
        cube_id = bpy.data.objects['Cube']['bar_uuid']
        arguments = {'object_ids': [cube_id]}
        if name == 'validate.dimensions':
            arguments['expected'] = [2,2,2]
        if name == 'validate.assembly':
            arguments['checks'] = [{'kind': 'component_count', 'expected': 1}]
    response = api.execute({'api_version': '1.0', 'tool': name, 'arguments': arguments,
                            'session_id': api.state.session_id, 'expected_revision': api.state.revision})
    validate_response(response)
    assert response['success'], response
assert tuple(bpy.data.objects) == objects_before, 'Discovery mutated the scene'
print('BAR_API_HEADLESS_OK')
