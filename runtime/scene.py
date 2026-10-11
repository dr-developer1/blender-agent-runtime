"""Bounded, read-only scene observations with revision-bound opaque cursors."""
import base64
from collections import Counter
import fnmatch
import hashlib
import hmac
import json
import secrets

from .errors import ToolError
from .identity import UUID_PROPERTY, object_key, validate_uuid
from .schemas import object_schema

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
STRING = {'type': 'string'}
NULLABLE_STRING = {'type': ['string', 'null']}
PAGE_INPUT_SCHEMA = object_schema({
    'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_PAGE_SIZE},
    'cursor': {'type': 'string', 'minLength': 1, 'maxLength': 2048}})
SHORT_STRING = {'type': 'string', 'minLength': 1, 'maxLength': 256}
VECTOR = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}
TAGS = object_schema()
TAGS['additionalProperties'] = STRING
FILTER_SCHEMA = object_schema({
    'object_type': SHORT_STRING, 'collection': SHORT_STRING, 'visible': {'type': 'boolean'},
    'name_pattern': SHORT_STRING, 'tags': TAGS,
    'region': object_schema({'min': VECTOR, 'max': VECTOR}, ('min', 'max'))})
LIST_INPUT_SCHEMA = object_schema({**FILTER_SCHEMA['properties'],
    'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_PAGE_SIZE},
    'cursor': {'type': 'string', 'minLength': 1, 'maxLength': 2048}})
OBJECT_SCHEMA = object_schema({
    'object_id': STRING, 'name': STRING, 'object_type': STRING,
    'collections': {'type': 'array', 'items': STRING}, 'visible': {'type': 'boolean'},
    'render_enabled': {'type': 'boolean'}, 'tags': TAGS, 'world_origin': VECTOR,
    'parent_id': NULLABLE_STRING},
    ('object_id', 'name', 'object_type', 'collections', 'visible', 'render_enabled', 'tags', 'world_origin', 'parent_id'))
HIERARCHY_NODE_SCHEMA = object_schema({'object_id': STRING, 'name': STRING, 'parent_id': NULLABLE_STRING},
                                    ('object_id', 'name', 'parent_id'))
HIERARCHY_OUTPUT_SCHEMA = object_schema({'nodes': {'type': 'array', 'items': HIERARCHY_NODE_SCHEMA},
    'total': {'type': 'integer'}, 'next_cursor': NULLABLE_STRING}, ('nodes', 'total', 'next_cursor'))
INSPECT_INPUT_SCHEMA = object_schema({'object_ids': {'type': 'array', 'items': SHORT_STRING,
    'minItems': 1, 'maxItems': MAX_PAGE_SIZE}}, ('object_ids',))
MESH_COUNTS_SCHEMA = {'type': ['object', 'null'], 'properties': {
    name: {'type': 'integer'} for name in ('vertices', 'edges', 'faces', 'triangles')},
    'required': ['vertices', 'edges', 'faces', 'triangles'], 'additionalProperties': False}
INSPECTION_SCHEMA = object_schema({**OBJECT_SCHEMA['properties'],
    'world_matrix': {'type': 'array', 'items': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 4, 'maxItems': 4}, 'minItems': 4, 'maxItems': 4},
    'base_geometry': MESH_COUNTS_SCHEMA, 'evaluated_geometry': MESH_COUNTS_SCHEMA,
    'evaluated_bounds': {'type': ['object', 'null'], 'properties': {'min': VECTOR, 'max': VECTOR},
                         'required': ['min', 'max'], 'additionalProperties': False},
    'evaluated_dimensions': {'type': ['array', 'null'], 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3},
    'bounds_method': NULLABLE_STRING}, tuple(OBJECT_SCHEMA['required']) +
    ('world_matrix', 'base_geometry', 'evaluated_geometry', 'evaluated_bounds', 'evaluated_dimensions', 'bounds_method'))
INSPECT_OUTPUT_SCHEMA = object_schema({'objects': {'type': 'array', 'items': INSPECTION_SCHEMA}}, ('objects',))

COUNTS = object_schema()
COUNTS['additionalProperties'] = {'type': 'integer', 'minimum': 0}
SUMMARY_OUTPUT_SCHEMA = object_schema({
    'scene_name': STRING, 'object_count': {'type': 'integer'}, 'object_types': COUNTS,
    'collection_count': {'type': 'integer'}, 'visible_count': {'type': 'integer'},
    'render_enabled_count': {'type': 'integer'}, 'frame': {'type': 'integer'}},
    ('scene_name', 'object_count', 'object_types', 'collection_count', 'visible_count',
     'render_enabled_count', 'frame'))
LIST_OUTPUT_SCHEMA = object_schema({
    'objects': {'type': 'array', 'items': OBJECT_SCHEMA}, 'total': {'type': 'integer'},
    'next_cursor': {'type': ['string', 'null']}}, ('objects', 'total', 'next_cursor'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class SceneObserver:
    def __init__(self, *, scene, view_layer, identities, state, depsgraph=None):
        self._scene = scene
        self._view_layer = view_layer
        self._identities = identities
        self._state = state
        self._depsgraph = depsgraph
        self._cursor_key = secrets.token_bytes(32)

    def _snapshot(self):
        scene = self._scene()
        index = self._identities.index()
        memberships = {}
        collection_keys = set()
        pending = [scene.collection]
        while pending:
            collection = pending.pop()
            key = object_key(collection)
            if key in collection_keys:
                continue
            collection_keys.add(key)
            pending.extend(collection.children)
            for obj in collection.objects:
                memberships.setdefault(object_key(obj), set()).add(collection.name)
        view_layer = self._view_layer() if self._view_layer else None
        if view_layer is not None:
            view_layer.update()
        rows = []
        for obj in scene.objects:
            if UUID_PROPERTY not in obj or obj[UUID_PROPERTY] not in index:
                raise ToolError('OBJECT_NOT_MANAGED', 'Scene object has no managed identity.')
            tags = obj.get('bar_tags', {})
            tags = {key: value for key, value in tags.items() if isinstance(value, str)} if hasattr(tags, 'items') else {}
            parent = getattr(obj, 'parent', None)
            if parent is not None and (UUID_PROPERTY not in parent or parent[UUID_PROPERTY] not in index):
                raise ToolError('OBJECT_NOT_MANAGED', 'Parent object has no managed identity.')
            rows.append({'parent_id': parent[UUID_PROPERTY] if parent is not None else None, 'object_id': obj[UUID_PROPERTY], 'name': obj.name, 'object_type': obj.type,
                         'collections': sorted(memberships.get(object_key(obj), ())),
                         'visible': bool(obj.visible_get(view_layer=view_layer) if view_layer is not None
                                         else obj.visible_get()),
                         'render_enabled': not obj.hide_render, 'tags': tags,
                         'world_origin': [float(value) for value in obj.matrix_world.translation]})
        rows.sort(key=lambda row: row['object_id'])
        return scene, rows, len(collection_keys)

    def summary(self, arguments):
        scene, rows, count = self._snapshot()
        return {'scene_name': scene.name, 'object_count': len(rows),
                'object_types': dict(sorted(Counter(row['object_type'] for row in rows).items())),
                'collection_count': count, 'visible_count': sum(row['visible'] for row in rows),
                'render_enabled_count': sum(row['render_enabled'] for row in rows), 'frame': scene.frame_current}

    def _matches(self, row, filters):
        return (('object_type' not in filters or row['object_type'] == filters['object_type']) and
                ('collection' not in filters or filters['collection'] in row['collections']) and
                ('visible' not in filters or row['visible'] == filters['visible']) and
                ('name_pattern' not in filters or fnmatch.fnmatchcase(row['name'], filters['name_pattern'])) and
                all(row['tags'].get(key) == value for key, value in filters.get('tags', {}).items()) and
                ('region' not in filters or all(low <= value <= high for low, value, high in
                 zip(filters['region']['min'], row['world_origin'], filters['region']['max']))))

    def _decode_cursor(self, token):
        try:
            encoded, signature = token.split('.')
            expected = hmac.new(self._cursor_key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError('Bad signature')
            payload = json.loads(base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True))
            if (not isinstance(payload, dict) or set(payload) != {'session', 'revision', 'query', 'snapshot', 'after'} or
                    type(payload['revision']) is not int or payload['revision'] < 0 or
                    any(not isinstance(payload[key], str) for key in ('session', 'query', 'snapshot', 'after'))):
                raise ValueError('Bad payload')
            return payload
        except (ValueError, UnicodeError, TypeError):
            raise ToolError('INVALID_CURSOR', 'Cursor is invalid or belongs to another runtime.') from None

    def _encode_cursor(self, payload):
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
        return encoded + '.' + hmac.new(self._cursor_key, encoded.encode(), hashlib.sha256).hexdigest()

    def list_objects(self, arguments, *, purpose='objects'):
        filters = {key: value for key, value in arguments.items() if key not in ('cursor', 'limit')}
        if 'region' in filters and any(low > high for low, high in zip(filters['region']['min'], filters['region']['max'])):
            raise ToolError('INVALID_ARGUMENT', 'Region minimum must not exceed maximum.')
        query = digest({'purpose': purpose, 'filters': filters})
        cursor = self._decode_cursor(arguments['cursor']) if 'cursor' in arguments else None
        if cursor:
            if cursor['session'] != self._state.session_id or cursor['revision'] != self._state.revision:
                raise ToolError('STALE_SCENE_STATE', 'Cursor belongs to an older runtime state.')
            if cursor['query'] != query:
                raise ToolError('INVALID_CURSOR', 'Cursor filters differ from this request.')
        scene, rows, _ = self._snapshot()
        rows = [row for row in rows if self._matches(row, filters)]
        snapshot = digest({'scene': scene.name, 'rows': rows})
        if cursor and cursor['snapshot'] != snapshot:
            raise ToolError('STALE_SCENE_STATE', 'Observed scene data changed since the previous page.')
        remaining = rows if cursor is None else [row for row in rows if row['object_id'] > cursor['after']]
        limit = arguments.get('limit', DEFAULT_PAGE_SIZE)
        page = remaining[:limit]
        next_cursor = None
        if len(remaining) > limit:
            next_cursor = self._encode_cursor({'session': self._state.session_id, 'revision': self._state.revision,
                                              'query': query, 'snapshot': snapshot, 'after': page[-1]['object_id']})
        return {'objects': page, 'total': len(rows), 'next_cursor': next_cursor}

    def hierarchy(self, arguments):
        page = self.list_objects(arguments, purpose='hierarchy')
        return {'nodes': [{key: row[key] for key in ('object_id', 'name', 'parent_id')} for row in page['objects']],
                'total': page['total'], 'next_cursor': page['next_cursor']}

    def inspect_objects(self, arguments):
        object_ids = arguments['object_ids']
        if len(set(object_ids)) != len(object_ids):
            raise ToolError('INVALID_ARGUMENT', 'Object IDs must be unique.')
        for object_id in object_ids:
            validate_uuid(object_id)
        index = self._identities.index()
        for object_id in object_ids:
            if object_id not in index:
                raise ToolError('OBJECT_NOT_FOUND', 'No current object has this UUID.', {'object_id': object_id})
        _, rows, _ = self._snapshot()
        rows = {row['object_id']: row for row in rows}
        if any(object_id not in rows for object_id in object_ids):
            raise ToolError('OBJECT_NOT_IN_SCENE', 'Requested object is not linked to the active scene.')
        depsgraph = self._depsgraph()
        inspected = []
        for object_id in object_ids:
            obj = index[object_id]
            evaluated = obj.evaluated_get(depsgraph)
            if not getattr(evaluated, 'is_evaluated', True):
                raise ToolError('OBJECT_NOT_EVALUATED', 'Object is excluded from the active dependency graph.')
            matrix = [[float(value) for value in row] for row in evaluated.matrix_world]
            def transformed(coordinates):
                return [sum(matrix[axis][column] * coordinates[column] for column in range(3)) + matrix[axis][3]
                        for axis in range(3)]
            base_counts = mesh_counts(obj)
            evaluated_counts = mesh_counts(evaluated)
            bounds = None
            dimensions = None
            bounds_method = None
            if evaluated.type == 'MESH':
                coordinates = (vertex.co for vertex in evaluated.data.vertices)
                bounds_method = 'evaluated_vertices'
            else:
                corners = list(evaluated.bound_box)
                has_geometry = evaluated.type in {'CURVE', 'SURFACE', 'FONT', 'META', 'VOLUME',
                                                   'POINTCLOUD', 'CURVES', 'GREASEPENCIL', 'GPENCIL'}
                coordinates = (corners if has_geometry and
                               not all(tuple(corner) == (-1, -1, -1) for corner in corners) else [])
                bounds_method = 'evaluated_bounding_box'
            low, high = [float('inf')] * 3, [-float('inf')] * 3
            found = False
            for coordinates_row in coordinates:
                point = transformed(coordinates_row)
                found = True
                low = [min(a, b) for a, b in zip(low, point)]
                high = [max(a, b) for a, b in zip(high, point)]
            if found:
                bounds = {'min': low, 'max': high}
                dimensions = [b - a for a, b in zip(low, high)]
            else:
                bounds_method = None
            inspected.append({**rows[object_id], 'world_matrix': matrix,
                              'world_origin': [matrix[axis][3] for axis in range(3)],
                              'base_geometry': base_counts, 'evaluated_geometry': evaluated_counts,
                              'evaluated_bounds': bounds, 'evaluated_dimensions': dimensions,
                              'bounds_method': bounds_method})
        return {'objects': inspected}


def mesh_counts(obj):
    if obj.type != 'MESH':
        return None
    mesh = obj.data
    mesh.calc_loop_triangles()
    return {'vertices': len(mesh.vertices), 'edges': len(mesh.edges),
            'faces': len(mesh.polygons), 'triangles': len(mesh.loop_triangles)}
