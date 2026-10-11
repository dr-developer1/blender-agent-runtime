"""Test runtime state hooks against real scene edits; no public modeling tools."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.schemas import validate_response

api = RuntimeAPI(blender_version=bpy.app.version_string)
created = []


def create(args):
    obj = bpy.data.objects.new('StateFixture', None)
    bpy.context.scene.collection.objects.link(obj)
    created.append(obj)
    return {}


def restore(args):
    for obj in created:
        bpy.data.objects.remove(obj, do_unlink=True)
    created.clear()
    return {}


api.registry.register(ToolSpec('test.create', 'Scene fixture', side_effects=('scene',)), create)
api.registry.register(ToolSpec('test.restore', 'Restore fixture', side_effects=('scene',)), restore)


def call(tool, revision):
    response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                            'expected_revision': revision, 'tool': tool, 'arguments': {}})
    validate_response(response)
    return response


count = len(bpy.data.objects)
assert call('test.create', 0)['revision_after'] == 1
assert len(bpy.data.objects) == count + 1
assert call('test.create', 0)['error']['code'] == 'STALE_SCENE_STATE'
assert len(bpy.data.objects) == count + 1
assert call('test.restore', 1)['revision_after'] == 2
assert len(bpy.data.objects) == count
assert call('test.create', 0)['error']['code'] == 'STALE_SCENE_STATE'
print('BAR_STATE_HEADLESS_OK')
