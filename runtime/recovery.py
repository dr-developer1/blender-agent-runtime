"""Bounded numeric scene diffs and one runtime-owned full-file checkpoint."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from .capability_registry import ToolSpec
from .errors import ToolError
from .identity import UUID_PROPERTY
from .schemas import MutationResult, object_schema
from .scene import digest

MAX_DIFF_OBJECTS = 1000
MAX_DIFF_ELEMENTS = 200000
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
ID = {'type': 'string', 'minLength': 1, 'maxLength': 64}
TRANSACTION_INPUT = object_schema({'transaction_id': ID}, ('transaction_id',))
STRING = {'type': 'string'}
IDS = {'type': 'array', 'items': STRING}
RECORD = object_schema()
RECORD['additionalProperties'] = True
DIFF_SCHEMA = object_schema({'created_ids': IDS, 'modified_ids': IDS, 'deleted_ids': IDS,
    'changes': {'type': 'array', 'items': RECORD}}, ('created_ids', 'modified_ids', 'deleted_ids', 'changes'))
BEGIN_OUTPUT = object_schema({'transaction_id': STRING, 'baseline_revision': {'type': 'integer'}},
                             ('transaction_id', 'baseline_revision'))
DIFF_OUTPUT = object_schema({'transaction_id': STRING, 'baseline_revision': {'type': 'integer'},
    'diff': DIFF_SCHEMA}, ('transaction_id', 'baseline_revision', 'diff'))
END_OUTPUT = object_schema({'transaction_id': STRING, 'status': STRING,
    'diff': {'type': ['object', 'null']}, 'diff_error': {'type': ['string', 'null']}},
    ('transaction_id', 'status', 'diff', 'diff_error'))


def scene_diff(before, after):
    """Compare UUID-keyed plain values, including same-count geometry edits."""
    created = sorted(after.keys() - before.keys())
    deleted = sorted(before.keys() - after.keys())
    modified = sorted(oid for oid in before.keys() & after.keys() if before[oid] != after[oid])
    changes = []
    for oid in sorted(set(created + deleted + modified)):
        old, new = before.get(oid), after.get(oid)
        fields = sorted(key for key in (old or {}).keys() | (new or {}).keys()
                        if old is None or new is None or old.get(key) != new.get(key))
        changes.append({'object_id': oid, 'kind': 'created' if old is None else 'deleted' if new is None else 'modified',
                        'fields': fields, 'before': old, 'after': new})
    return {'created_ids': created, 'modified_ids': modified, 'deleted_ids': deleted, 'changes': changes}


def bounded_diff(before, after):
    from controller.ipc import MAX_FRAME_BYTES
    result = scene_diff(before, after)
    # End responses also repeat change arrays in the public envelope. Reserve
    # their bytes before dropping a checkpoint or publishing a successful end.
    envelope = {'diff': result, **{key: result[key] for key in
                                  ('created_ids', 'modified_ids', 'deleted_ids')}}
    if len(json.dumps(envelope, allow_nan=False).encode()) > MAX_FRAME_BYTES - 4096:
        raise ToolError('RESPONSE_TOO_LARGE', 'Scene diff exceeds the response budget.')
    return result


@dataclass
class Checkpoint:
    transaction_id: str
    baseline_revision: int
    baseline: dict
    directory: object
    path: Path
    checksum: str


class RecoveryService:
    def __init__(self, *, observer, identities, state, capture=None, save=None, load=None):
        self.observer, self.identities, self.state = observer, identities, state
        self.capture = capture or self._capture
        self.save = save or self._save
        self.load = load or self._load
        self.active = None

    def register(self, registry):
        for name, description, schema, output, effects, handler in (
            ('scene.diff', 'Compare the active scene with the current transaction baseline.', TRANSACTION_INPUT, DIFF_OUTPUT, (), self.diff),
            ('transaction.begin', 'Begin one transaction and save a private full-file checkpoint.', object_schema(), BEGIN_OUTPUT, ('transaction_state',), self.begin),
            ('transaction.commit', 'Keep current contents and discard the checkpoint.', TRANSACTION_INPUT, END_OUTPUT, ('transaction_state',), self.commit),
            ('transaction.rollback', 'Restore the checkpoint without rewinding the runtime timeline.', TRANSACTION_INPUT, END_OUTPUT, ('scene_restore', 'transaction_state'), self.rollback)):
            registry.register(ToolSpec(name, description, input_schema=schema, output_schema=output,
                side_effects=effects, supports={'transactions': True}, transaction_safe=True), handler)

    def _context(self):
        import bpy
        if bpy.context.mode != 'OBJECT':
            raise ToolError('UNSUPPORTED_OBJECT_MODE', 'Recovery requires Object mode.')

    def _capture(self):
        try:
            return self._capture_data()
        except (ValueError, TypeError):
            raise ToolError('INVALID_GEOMETRY', 'Scene measurements must be finite JSON values.') from None

    def _capture_data(self):
        self._context()
        import bpy
        if len(bpy.data.objects) > MAX_DIFF_OBJECTS:
            raise ToolError('RECOVERY_LIMIT_EXCEEDED', 'Object count exceeds the recovery budget.')
        index = self.identities.index()
        if any(UUID_PROPERTY not in obj for obj in bpy.data.objects):
            raise ToolError('OBJECT_NOT_MANAGED', 'All objects must have managed identities before recovery.')
        _, rows, _ = self.observer._snapshot()
        depsgraph = self.observer._depsgraph()
        elements = 0
        for row in rows:
            obj = index[row['object_id']]
            evaluated = obj.evaluated_get(depsgraph)
            if not evaluated.is_evaluated:
                raise ToolError('OBJECT_NOT_EVALUATED', 'Object is excluded from evaluation.')
            for candidate in (obj, evaluated):
                if candidate.type == 'MESH':
                    mesh = candidate.data
                    elements += len(mesh.vertices) + len(mesh.edges) + len(mesh.polygons) + len(mesh.loops)
                    if elements > MAX_DIFF_ELEMENTS:
                        raise ToolError('RECOVERY_LIMIT_EXCEEDED', 'Mesh scan exceeds the recovery budget.')
        inspected_rows = {}
        for offset in range(0, len(rows), 100):
            inspected_rows.update((item['object_id'], item) for item in self.observer.inspect_objects(
                {'object_ids': [row['object_id'] for row in rows[offset:offset + 100]]})['objects'])
        result = {}
        for row in rows:
            obj = index[row['object_id']]
            geometry = None
            if obj.type == 'MESH':
                mesh = obj.data
                geometry = digest([[list(v.co) for v in mesh.vertices], [list(e.vertices) for e in mesh.edges],
                                   [list(p.vertices) for p in mesh.polygons]])
            inspected = inspected_rows[row['object_id']]
            modifiers = []
            for modifier in obj.modifiers:
                properties = {}
                for prop in modifier.bl_rna.properties:
                    if prop.identifier == 'rna_type' or prop.is_readonly:
                        continue
                    value = getattr(modifier, prop.identifier)
                    if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
                        properties[prop.identifier] = list(value) if getattr(prop, 'is_array', False) else sorted(value) if isinstance(value, set) else value
                    elif prop.type == 'POINTER':
                        properties[prop.identifier] = (None if value is None else
                            {'name': value.name, 'object_id': value.get(UUID_PROPERTY)} if isinstance(value, bpy.types.Object)
                            else {'name': getattr(value, 'name', ''), 'type': type(value).__name__})
                modifiers.append({'name': modifier.name, 'type': modifier.type, 'properties': properties})
            material_assignment = digest({
                'slots': [{'link': slot.link, 'material_id': slot.material.get('bar_material_uuid'),
                           'name': slot.material.name} if slot.material else {'link': slot.link, 'material_id': None}
                          for slot in obj.material_slots],
                'face_indices': [p.material_index for p in obj.data.polygons] if obj.type == 'MESH' else []})
            result[row['object_id']] = {**inspected, 'geometry_fingerprint': geometry,
                                      'material_assignment_fingerprint': material_assignment,
                                      'modifiers': modifiers}
        try:
            json.dumps(result, allow_nan=False)
        except (ValueError, TypeError):
            raise ToolError('INVALID_GEOMETRY', 'Scene measurements must be finite JSON values.') from None
        # Ensure even an all-created/all-deleted report fits before publication.
        bounded_diff({}, result)
        return result

    def _save(self, path):
        import bpy
        try:
            outcome = bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False,
                                                copy=True, relative_remap=True)
            if 'FINISHED' not in outcome:
                raise RuntimeError('Save cancelled')
        except (RuntimeError, OSError):
            raise ToolError('SNAPSHOT_FAILED', 'Could not save the recovery checkpoint.') from None

    def _load(self, checkpoint):
        self._context()
        import bpy
        try:
            outcome = bpy.ops.wm.open_mainfile(filepath=str(checkpoint.path), load_ui=True, use_scripts=False)
            if 'FINISHED' not in outcome:
                raise RuntimeError('Load cancelled')
            # Preserve external resource targets after the private directory is
            # removed. Blender keeps the loaded checkpoint filepath (read-only).
            if 'FINISHED' not in bpy.ops.file.make_paths_absolute():
                raise RuntimeError('Path conversion cancelled')
            bpy.context.view_layer.update()
            self.identities.index()  # Reacquire live objects; never retain old refs.
        except (RuntimeError, OSError):
            raise ToolError('ROLLBACK_FAILED', 'Could not restore the recovery checkpoint.') from None

    def _require(self, args):
        if self.active is None:
            raise ToolError('NO_ACTIVE_TRANSACTION', 'There is no active transaction.')
        if args['transaction_id'] != self.active.transaction_id:
            raise ToolError('INVALID_TRANSACTION', 'Transaction belongs to another or expired checkpoint.')
        return self.active

    def begin(self, args):
        if self.active is not None:
            raise ToolError('TRANSACTION_ACTIVE', 'Nested transactions are not supported.')
        baseline = self.capture()
        directory = tempfile.TemporaryDirectory(prefix='bar-recovery-', dir=os.environ.get('BAR_RECOVERY_ROOT'))
        path = Path(directory.name) / 'checkpoint.blend'
        try:
            self.save(path)
            if not path.is_file() or path.stat().st_size == 0:
                raise ToolError('SNAPSHOT_FAILED', 'Checkpoint was not written.')
            if path.stat().st_size > MAX_SNAPSHOT_BYTES:
                raise ToolError('RECOVERY_LIMIT_EXCEEDED', 'Checkpoint exceeds the disk budget.')
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            self.active = Checkpoint(str(uuid.uuid4()), self.state.revision, baseline,
                                     directory, path, checksum)
        except Exception:
            directory.cleanup()
            raise
        return {'transaction_id': self.active.transaction_id, 'baseline_revision': self.active.baseline_revision}

    def diff(self, args):
        checkpoint = self._require(args)
        return {'transaction_id': checkpoint.transaction_id, 'baseline_revision': checkpoint.baseline_revision,
                'diff': bounded_diff(checkpoint.baseline, self.capture())}

    def _finish(self, checkpoint, status, diff, diff_error=None):
        self.active = None
        checkpoint.directory.cleanup()
        return MutationResult({'transaction_id': checkpoint.transaction_id, 'status': status,
            'diff': diff, 'diff_error': diff_error}, **({key: diff[key] for key in
            ('created_ids', 'modified_ids', 'deleted_ids')} if diff is not None else {}))

    def commit(self, args):
        checkpoint = self._require(args)
        diff = bounded_diff(checkpoint.baseline, self.capture())
        return self._finish(checkpoint, 'committed', diff)

    def rollback(self, args):
        checkpoint = self._require(args)
        try:
            if (not checkpoint.path.is_file() or checkpoint.path.stat().st_size > MAX_SNAPSHOT_BYTES or
                    hashlib.sha256(checkpoint.path.read_bytes()).hexdigest() != checkpoint.checksum):
                raise OSError('Checkpoint unavailable')
        except OSError:
            raise ToolError('SNAPSHOT_UNAVAILABLE', 'Checkpoint is missing or corrupted; transaction remains active.') from None
        # Broken identities or excessive post-edit geometry must not block recovery.
        diff_error = None
        try:
            before = self.capture()
            diff = bounded_diff(before, checkpoint.baseline)
        except Exception as exc:
            diff, diff_error = None, exc.code if isinstance(exc, ToolError) else 'INTERNAL_ERROR'
        self.load(checkpoint)
        return self._finish(checkpoint, 'rolled_back', diff, diff_error)

    def close(self):
        if self.active is not None:
            self.active.directory.cleanup()
            self.active = None
