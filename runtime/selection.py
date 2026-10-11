"""Read-only base-mesh addressing and bounded, runtime-local selection handles."""
from collections import OrderedDict
from dataclasses import dataclass
import math
import secrets

from .errors import ToolError
from .identity import object_key
from .scene import VECTOR, SHORT_STRING, digest
from .schemas import object_schema

MAX_HANDLES = 256
MAX_MESH_ELEMENTS = 200000
MAX_SELECTION_INDICES = 10000
ELEMENT = {'type': 'string', 'enum': ['VERTEX', 'EDGE', 'FACE']}
KINDS = ['top', 'bottom', 'left', 'right', 'front', 'back', 'within_bbox',
         'height_range', 'nearest_point', 'normal_direction', 'length_range',
         'area_range', 'dihedral_angle', 'boundary', 'manifold', 'non_manifold', 'connected_to',
         'outer_boundary', 'cap_faces', 'side_faces']
SELECTOR_SCHEMA = object_schema({
    'kind': {'type': 'string', 'enum': KINDS},
    'tolerance': {'type': 'number', 'minimum': 0},
    'min': VECTOR, 'max': VECTOR, 'point': VECTOR, 'direction': VECTOR,
    'minimum': {'type': 'number'}, 'maximum': {'type': 'number'},
    'angle_degrees': {'type': 'number', 'minimum': 0, 'maximum': 180},
    'seed_index': {'type': 'integer', 'minimum': 0}}, ('kind',))
QUERY_SCHEMA = object_schema({
    'object_id': SHORT_STRING, 'element_type': ELEMENT,
    'space': {'type': 'string', 'enum': ['WORLD', 'LOCAL']},
    'selectors': {'type': 'array', 'items': SELECTOR_SCHEMA, 'minItems': 1, 'maxItems': 16}},
    ('object_id', 'element_type', 'selectors'))
HANDLE_SCHEMA = object_schema({'selection_handle': SHORT_STRING}, ('selection_handle',))
RESULT_PROPERTIES = {'selection_handle': SHORT_STRING, 'object_id': SHORT_STRING,
    'element_type': ELEMENT, 'matched_count': {'type': 'integer', 'minimum': 0},
    'valid_at_revision': {'type': 'integer', 'minimum': 0},
    'space': {'type': 'string', 'enum': ['WORLD', 'LOCAL']},
    'geometry': {'type': 'string', 'enum': ['BASE']}}
QUERY_OUTPUT = object_schema(RESULT_PROPERTIES, tuple(RESULT_PROPERTIES))
INSPECT_OUTPUT = object_schema({**RESULT_PROPERTIES,
    'indices': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0},
                'maxItems': MAX_SELECTION_INDICES}}, (*RESULT_PROPERTIES, 'indices'))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def length(a):
    return math.hypot(*a)


def unit(a):
    size = length(a)
    return tuple(x / size for x in a) if size else (0., 0., 0.)


@dataclass
class MeshSnapshot:
    """Plain numeric geometry; no Blender references are kept in handles."""
    vertices: list
    edges: list
    faces: list
    fingerprint: str = ''

    def __post_init__(self):
        self.fingerprint = self.fingerprint or digest([self.vertices, self.edges, self.faces])
        self.edge_faces = [[] for _ in self.edges]
        edge_map = {tuple(sorted(edge)): i for i, edge in enumerate(self.edges)}
        self.face_edges = []
        for face_id, face in enumerate(self.faces):
            indices = []
            for a, b in zip(face, face[1:] + face[:1]):
                edge_id = edge_map.get(tuple(sorted((a, b))))
                if edge_id is not None:
                    indices.append(edge_id)
                    self.edge_faces[edge_id].append(face_id)
            self.face_edges.append(indices)
        self.normals, self.areas = [], []
        for face in self.faces:
            points = [self.vertices[i] for i in face]
            # Newell vector: normal and area for planar base polygons.
            vector = [0., 0., 0.]
            for a, b in zip(points, points[1:] + points[:1]):
                vector[0] += (a[1] - b[1]) * (a[2] + b[2])
                vector[1] += (a[2] - b[2]) * (a[0] + b[0])
                vector[2] += (a[0] - b[0]) * (a[1] + b[1])
            self.normals.append(unit(vector))
            self.areas.append(length(vector) / 2)

    def elements(self, kind):
        return ([[i] for i in range(len(self.vertices))] if kind == 'VERTEX' else
                self.edges if kind == 'EDGE' else self.faces)

    def centers(self, kind):
        return [tuple(sum(self.vertices[i][axis] for i in element) / len(element)
                      for axis in range(3)) for element in self.elements(kind)]

    def connected(self, kind, seed):
        elements = self.elements(kind)
        if seed >= len(elements):
            raise ToolError('INVALID_ARGUMENT', 'Seed index is outside the current base mesh.')
        # Faces connect across edges; edges/vertices connect through shared vertices.
        buckets = {}
        for i, element in enumerate(self.face_edges if kind == 'FACE' else elements):
            for key in element:
                buckets.setdefault(key, []).append(i)
        if kind == 'VERTEX':
            adjacency = [[] for _ in elements]
            for a, b in self.edges:
                adjacency[a].append(b)
                adjacency[b].append(a)
        else:
            adjacency = None
        found, pending, used = {seed}, [seed], set()
        while pending:
            i = pending.pop()
            if adjacency is not None:
                neighbors = adjacency[i]
            else:
                neighbors = []
                for key in elements[i] if kind == 'EDGE' else self.face_edges[i]:
                    if key not in used:
                        used.add(key)
                        neighbors.extend(buckets[key])
            for neighbor in neighbors:
                if neighbor not in found:
                    found.add(neighbor)
                    pending.append(neighbor)
        return found

    def match(self, kind, selector):
        name = selector['kind']
        fields = {
            **{key: {'tolerance'} for key in ('top', 'bottom', 'left', 'right', 'front', 'back')},
            'within_bbox': {'min', 'max', 'tolerance'}, 'height_range': {'minimum', 'maximum', 'tolerance'},
            'nearest_point': {'point', 'tolerance'}, 'normal_direction': {'direction', 'angle_degrees'},
            'length_range': {'minimum', 'maximum'}, 'area_range': {'minimum', 'maximum'},
            'dihedral_angle': {'minimum', 'maximum'},
            'connected_to': {'seed_index'}, 'cap_faces': {'angle_degrees'}, 'side_faces': {'angle_degrees'},
            'boundary': set(), 'outer_boundary': set(), 'manifold': set(), 'non_manifold': set()}
        required = {'within_bbox': {'min', 'max'}, 'height_range': {'minimum', 'maximum'},
                    'nearest_point': {'point'}, 'normal_direction': {'direction'},
                    'length_range': {'minimum', 'maximum'}, 'area_range': {'minimum', 'maximum'},
                    'dihedral_angle': {'minimum', 'maximum'}, 'connected_to': {'seed_index'}}.get(name, set())
        actual = set(selector) - {'kind'}
        if actual - fields[name] or required - actual:
            raise ToolError('INVALID_ARGUMENT', 'Selector fields do not match its kind.', {'kind': name})
        if name in ('normal_direction', 'area_range', 'cap_faces', 'side_faces') and kind != 'FACE':
            raise ToolError('INVALID_ARGUMENT', 'This selector requires FACE elements.')
        if name in ('length_range', 'dihedral_angle', 'boundary', 'outer_boundary', 'manifold', 'non_manifold') and kind != 'EDGE':
            raise ToolError('INVALID_ARGUMENT', 'This selector requires EDGE elements.')
        if 'minimum' in selector and (selector['minimum'] > selector['maximum'] or
                (name in ('length_range', 'area_range') and selector['minimum'] < 0)):
            raise ToolError('INVALID_ARGUMENT', 'Invalid selector range.')
        if name == 'within_bbox' and any(a > b for a, b in zip(selector['min'], selector['max'])):
            raise ToolError('INVALID_ARGUMENT', 'Invalid bounding box.')
        if name == 'normal_direction' and length(selector['direction']) == 0:
            raise ToolError('INVALID_ARGUMENT', 'Normal direction must be nonzero.')
        if name == 'dihedral_angle' and (selector['minimum'] < 0 or selector['maximum'] > 180):
            raise ToolError('INVALID_ARGUMENT', 'Dihedral angles must be between 0 and 180 degrees.')
        tolerance = selector.get('tolerance', 1e-6)
        elements = self.elements(kind)
        if name == 'connected_to':
            return self.connected(kind, selector['seed_index'])
        if name == 'dihedral_angle':
            matched = set()
            for i, faces in enumerate(self.edge_faces):
                if len(faces) == 2:
                    a, b = (self.normals[face] for face in faces)
                    if length(a) and length(b):
                        angle = math.degrees(math.acos(max(-1., min(1., dot(a, b)))))
                        if selector['minimum'] <= angle <= selector['maximum']:
                            matched.add(i)
            return matched
        if name in ('boundary', 'outer_boundary', 'manifold', 'non_manifold'):
            # Basic semantic outer_boundary means every open boundary, including holes.
            return {i for i, faces in enumerate(self.edge_faces) if
                    (len(faces) == 1 if name in ('boundary', 'outer_boundary') else
                     len(faces) == 2 if name == 'manifold' else len(faces) != 2)}
        if not self.vertices:
            return set()
        extremes = {'top': (2, True), 'bottom': (2, False), 'left': (0, False),
                    'right': (0, True), 'front': (1, False), 'back': (1, True)}
        if name in extremes:
            axis, high = extremes[name]
            target = (max if high else min)(v[axis] for v in self.vertices)
            return {i for i, element in enumerate(elements) if
                    all(abs(self.vertices[v][axis] - target) <= tolerance for v in element)}
        centers = self.centers(kind)
        if name == 'nearest_point':
            distances = [length(sub(center, selector['point'])) for center in centers]
            nearest = min(distances, default=math.inf)
            return {i for i, distance in enumerate(distances) if distance <= nearest + tolerance}
        if name in ('normal_direction', 'cap_faces', 'side_faces'):
            angle = selector.get('angle_degrees', 5.)
            direction = unit(selector.get('direction', [0, 0, 1]))
            cosine = math.cos(math.radians(angle))
            if name == 'side_faces' and angle > 90:
                raise ToolError('INVALID_ARGUMENT', 'Side-face tolerance cannot exceed 90 degrees.')
            return {i for i, normal in enumerate(self.normals) if length(normal) > 0 and
                    (abs(normal[2]) <= math.sin(math.radians(angle)) + 1e-12 if name == 'side_faces' else
                     abs(normal[2]) + 1e-12 >= cosine if name == 'cap_faces' else
                     dot(normal, direction) + 1e-12 >= cosine)}
        if name == 'length_range':
            values = [length(sub(self.vertices[a], self.vertices[b])) for a, b in self.edges]
        elif name == 'area_range':
            values = self.areas
        elif name == 'height_range':
            return {i for i, element in enumerate(elements) if all(
                selector['minimum'] - tolerance <= self.vertices[v][2] <= selector['maximum'] + tolerance
                for v in element)}
        else:  # within_bbox requires every vertex to be contained.
            return {i for i, element in enumerate(elements) if all(
                all(a - tolerance <= value <= b + tolerance for a, value, b in
                    zip(selector['min'], self.vertices[v], selector['max'])) for v in element)}
        return {i for i, value in enumerate(values) if selector['minimum'] <= value <= selector['maximum']}


class SelectionService:
    def __init__(self, *, identities, state, scene, view_layer=None, snapshot=None):
        self.identities, self.state = identities, state
        self.scene, self.view_layer = scene, view_layer
        self.snapshot = snapshot or self._blender_snapshot
        self._handles = OrderedDict()
        self._revision = state.revision

    def _blender_snapshot(self, obj, space):
        mesh = obj.data
        if mesh.is_editmode:
            raise ToolError('UNSUPPORTED_OBJECT_MODE', 'Base mesh queries require Object mode.')
        if len(mesh.vertices) + len(mesh.edges) + len(mesh.polygons) + len(mesh.loops) > MAX_MESH_ELEMENTS:
            raise ToolError('SELECTION_LIMIT_EXCEEDED', 'Base mesh exceeds the query budget.')
        local = [tuple(float(x) for x in v.co) for v in mesh.vertices]
        world_matrix = [list(row) for row in obj.matrix_world]
        vertices = ([tuple(float(x) for x in obj.matrix_world @ v.co) for v in mesh.vertices]
                    if space == 'WORLD' else local)
        edges = [list(e.vertices) for e in mesh.edges]
        faces = [list(p.vertices) for p in mesh.polygons]
        if any(not math.isfinite(x) for v in vertices for x in v):
            raise ToolError('INVALID_GEOMETRY', 'Mesh coordinates must be finite.')
        return MeshSnapshot(vertices, edges, faces, digest([local, edges, faces, world_matrix]))

    def _read(self, object_id, space):
        obj = self.identities.resolve(object_id)
        if not any(object_key(candidate) == object_key(obj) for candidate in self.scene().objects):
            raise ToolError('OBJECT_NOT_IN_SCENE', 'Object is outside the active scene.')
        if obj.type != 'MESH':
            raise ToolError('OBJECT_NOT_MESH', 'Selection requires a mesh object.')
        if self.view_layer is not None:
            self.view_layer().update()
        return self.snapshot(obj, space)

    def _expire(self):
        if self._revision != self.state.revision:
            self._handles.clear()
            self._revision = self.state.revision

    def query(self, arguments):
        self._expire()
        kind, space = arguments['element_type'], arguments.get('space', 'WORLD')
        mesh = self._read(arguments['object_id'], space)
        indices = set(range(len(mesh.elements(kind))))
        for selector in arguments['selectors']:
            indices &= mesh.match(kind, selector)
        if len(indices) > MAX_SELECTION_INDICES:
            raise ToolError('SELECTION_LIMIT_EXCEEDED', 'Selection exceeds the index budget.')
        token = 'sel_' + secrets.token_urlsafe(24)
        result = {'selection_handle': token, 'object_id': arguments['object_id'], 'element_type': kind,
                  'matched_count': len(indices), 'valid_at_revision': self.state.revision,
                  'space': space, 'geometry': 'BASE'}
        self._handles[token] = (result, sorted(indices), mesh.fingerprint)
        if len(self._handles) > MAX_HANDLES:
            self._handles.popitem(last=False)
        return dict(result)

    def resolve(self, token):
        """Resolve before a future mutation advances revision; never retain bpy refs."""
        self._expire()
        if token not in self._handles:
            raise ToolError('INVALID_SELECTION_HANDLE', 'Selection handle expired or belongs to another runtime.')
        result, indices, fingerprint = self._handles[token]
        mesh = self._read(result['object_id'], result['space'])
        if mesh.fingerprint != fingerprint:
            del self._handles[token]
            raise ToolError('STALE_SELECTION', 'Base mesh or transform changed since the query.')
        return {**result, 'indices': list(indices)}

    def inspect(self, arguments):
        return self.resolve(arguments['selection_handle'])
