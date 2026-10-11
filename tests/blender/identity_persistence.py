"""Cross-process .blend persistence fixture; mode/path supplied by test wrapper."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from runtime.api import RuntimeAPI
from runtime.identity import UUID_PROPERTY

blend_path = str(Path(path) / 'persistent.blend')
metadata_path = Path(path) / 'identity.json'
if mode == 'read':
    bpy.ops.wm.open_mainfile(filepath=blend_path)
api = RuntimeAPI(blender_version=bpy.app.version_string, objects=lambda: bpy.data.objects)
if mode == 'write':
    source = bpy.data.objects['Cube']
    source.name = 'Persistent label'
    metadata_path.write_text(json.dumps({'session_id': api.state.session_id,
                                        'objects': {obj[UUID_PROPERTY]: obj.name for obj in bpy.data.objects}}))
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
else:
    metadata = json.loads(metadata_path.read_text())
    assert api.state.session_id != metadata['session_id']
    assert api.state.revision == 0
    assert api.identities.ensure_all() == []
    assert len(bpy.data.objects) == len(metadata['objects'])
    for object_id, name in metadata['objects'].items():
        assert api.identities.resolve(object_id).name == name
    print('BAR_IDENTITY_PERSISTENCE_OK')
