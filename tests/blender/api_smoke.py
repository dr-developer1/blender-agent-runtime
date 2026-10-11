"""Verify the public API inside a fresh isolated Blender interpreter."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.schemas import validate_response

api = RuntimeAPI(blender_version=bpy.app.version_string)
objects_before = tuple(bpy.data.objects)
for name in api.registry.names():
    arguments = {'name': name} if name == 'runtime.describe_tool' else {}
    response = api.execute({'api_version': '1.0', 'tool': name, 'arguments': arguments,
                            'session_id': api.state.session_id, 'expected_revision': api.state.revision})
    validate_response(response)
    assert response['success'], response
assert tuple(bpy.data.objects) == objects_before, 'Discovery mutated the scene'
print('BAR_API_HEADLESS_OK')
