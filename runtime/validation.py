"""Read-only technical validation; assembly relationships are explicit AABB checks."""
from collections import Counter, defaultdict
import math

from .capability_registry import ToolSpec
from .errors import ToolError
from .identity import object_key, validate_uuid
from .objects import UNIT
from .scene import INSPECT_INPUT_SCHEMA
from .schemas import object_schema

MAX_VALIDATION_ELEMENTS = 200000
MAX_ASSEMBLY_CHECKS = 200
IDS = INSPECT_INPUT_SCHEMA['properties']['object_ids']
ID = IDS['items']
NONNEGATIVE = {'type': 'number', 'minimum': 0, 'maximum': 1e6}
COMMON = {'object_ids': IDS}
GEOMETRY_OPTIONS = {'geometry': {'type': 'string', 'enum': ['base', 'evaluated']},
                    'require_closed': {'type': 'boolean'}, 'area_epsilon': NONNEGATIVE}
GEOMETRY_SCHEMA = object_schema({**COMMON, **GEOMETRY_OPTIONS}, ('object_ids',))
DIMENSION_OPTIONS = {'expected': {'type': 'array', 'items': NONNEGATIVE, 'minItems': 3, 'maxItems': 3},
                     'tolerance': NONNEGATIVE, 'unit': UNIT}
DIMENSIONS_SCHEMA = object_schema({**COMMON, **DIMENSION_OPTIONS}, ('object_ids', 'expected'))
CHECK_SCHEMA = object_schema({
    'kind': {'type': 'string', 'enum': ['ground', 'contact', 'support', 'no_overlap',
                                       'clearance', 'symmetry', 'component_count', 'connected']},
    'object_id': ID, 'other_id': ID, 'minimum': NONNEGATIVE,
    'expected': {'type': 'integer', 'minimum': 1, 'maximum': 100},
    'axis': {'type': 'string', 'enum': ['X', 'Y', 'Z']},
    'plane': {'type': 'number', 'minimum': -1e6, 'maximum': 1e6}}, ('kind',))
CHECKS = {'type': 'array', 'items': CHECK_SCHEMA, 'minItems': 1, 'maxItems': MAX_ASSEMBLY_CHECKS}
ASSEMBLY_OPTIONS = {'checks': CHECKS, 'tolerance': NONNEGATIVE, 'unit': UNIT}
ASSEMBLY_SCHEMA = object_schema({**COMMON, **ASSEMBLY_OPTIONS}, ('object_ids', 'checks'))
ASSET_SCHEMA = object_schema({**COMMON, **GEOMETRY_OPTIONS, 'dimensions': object_schema(
    DIMENSION_OPTIONS, ('expected',)), 'assembly': object_schema(ASSEMBLY_OPTIONS, ('checks',)),
    'require_materials': {'type': 'boolean'}}, ('object_ids',))
DETAILS_SCHEMA = object_schema()
DETAILS_SCHEMA['additionalProperties'] = True
CHECK_OUTPUT = object_schema({'code': {'type': 'string'}, 'passed': {'type': 'boolean'},
    'object_ids': {'type': 'array', 'items': {'type': 'string'}}, 'details': DETAILS_SCHEMA},
    ('code', 'passed', 'object_ids', 'details'))
REPORT_SCHEMA = object_schema({'passed': {'type': 'boolean'},
    'checks': {'type': 'array', 'items': CHECK_OUTPUT}}, ('passed', 'checks'))


def check(code, passed, ids, **details):
    return {'code': code, 'passed': bool(passed), 'object_ids': list(ids), 'details': details}


def report(checks):
    return {'passed': all(c['passed'] for c in checks), 'checks': checks}


def factor(args):
    return {'m': 1, 'cm': .01, 'mm': .001}[args.get('unit', 'm')]


def finite(rows):
    return all(math.isfinite(v) for row in rows for v in row)


def geometry_checks(data, require_closed, area_epsilon):
    oid = [data['object_id']]
    points, edges, faces = data['points'], data['edges'], data['faces']
    if not finite(points):
        return [check('NONFINITE_GEOMETRY', False, oid)]
    dimensions = [max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)] if points else [0,0,0]
    results = [check('INVALID_DIMENSIONS', all(v > 0 for v in dimensions) if require_closed else any(v > 0 for v in dimensions), oid, measured_m=dimensions),
               check('NONFINITE_GEOMETRY', True, oid),
               check('EMPTY_MESH', bool(points) and bool(faces), oid,
                     vertices=len(points), edges=len(edges), faces=len(faces)),
               check('NEGATIVE_SCALE', not data['negative_scale'], oid)]
    def finding(code, indices):
        results.append(check(code, not indices, oid, count=len(indices), sample_indices=indices[:20]))
    links = Counter()
    directions = defaultdict(list)
    used = set()
    degenerate, zero_area, invalid_normals = [], [], []
    face_keys = set()
    duplicates = []
    for index, face in enumerate(faces):
        used.update(face)
        polygon = [points[i] for i in face]
        # Newell's vector yields twice the area of a planar polygon.
        normal = [0., 0., 0.]
        for a, b in zip(face, face[1:] + face[:1]):
            key = tuple(sorted((a, b)))
            links[key] += 1
            directions[key].append(a < b)
            p, q = points[a], points[b]
            normal[0] += (p[1] - q[1]) * (p[2] + q[2])
            normal[1] += (p[2] - q[2]) * (p[0] + q[0])
            normal[2] += (p[0] - q[0]) * (p[1] + q[1])
        area = math.hypot(*normal) * .5
        if area <= area_epsilon:
            zero_area.append(index)
        if len(set(face)) < 3 or len(set(face)) != len(face) or area <= area_epsilon:
            degenerate.append(index)
        n = data['normals'][index]
        if not finite([n]) or math.hypot(*n) < .5 or math.hypot(*n) > 1.5:
            invalid_normals.append(index)
        # Detect equal coordinate cycles regardless of starting corner or winding.
        cycle = tuple(polygon)
        if cycle:
            start = min(range(len(cycle)), key=cycle.__getitem__)
            forward = cycle[start:] + cycle[:start]
            reverse = tuple(reversed(cycle))
            start = min(range(len(reverse)), key=reverse.__getitem__)
            key = min(forward, reverse[start:] + reverse[:start])
            if key in face_keys:
                duplicates.append(index)
            face_keys.add(key)
    edge_vertices = {i for edge in edges for i in edge}
    finding('LOOSE_VERTICES', [i for i in range(len(points)) if i not in edge_vertices and i not in used])
    finding('LOOSE_EDGES', [i for i, edge in enumerate(edges) if links[tuple(sorted(edge))] == 0])
    finding('NON_MANIFOLD_EDGES', [i for i, edge in enumerate(edges)
        if links[tuple(sorted(edge))] > 2 or (require_closed and links[tuple(sorted(edge))] != 2)])
    finding('INCONSISTENT_WINDING', [i for i, edge in enumerate(edges)
        if len(directions[tuple(sorted(edge))]) == 2 and len(set(directions[tuple(sorted(edge))])) == 1])
    finding('ZERO_AREA_FACES', zero_area)
    finding('DEGENERATE_FACES', degenerate)
    finding('INVALID_NORMALS', invalid_normals)
    seen, coincident = set(), []
    for i, p in enumerate(points):
        if p in seen:
            coincident.append(i)
        seen.add(p)
    finding('COINCIDENT_VERTICES', coincident)
    finding('COINCIDENT_FACES', duplicates)
    # Connected components include loose vertices and face connections.
    parent = list(range(len(points)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in edges:
        parent[root(a)] = root(b)
    components = len({root(i) for i in range(len(points))})
    results.append(check('MESH_COMPONENTS', True, oid, count=components))
    return results


def union_bounds(bounds):
    return {'min': [min(b['min'][i] for b in bounds.values()) for i in range(3)],
            'max': [max(b['max'][i] for b in bounds.values()) for i in range(3)]}


def dimension_checks(bounds, args):
    box = union_bounds(bounds)
    measured = [box['max'][i] - box['min'][i] for i in range(3)]
    expected = [v * factor(args) for v in args['expected']]
    tolerance = args.get('tolerance', .001) * factor(args)
    return [check('EVALUATED_DIMENSIONS', all(abs(a-b) <= tolerance + 1e-12 for a,b in zip(measured, expected)),
                  bounds, measured_m=measured, expected_m=expected, tolerance_m=tolerance,
                  method='evaluated_world_aabb_union')]


def pair_metrics(a, b):
    gaps = [max(a['min'][i] - b['max'][i], b['min'][i] - a['max'][i], 0) for i in range(3)]
    overlap = [min(a['max'][i], b['max'][i]) - max(a['min'][i], b['min'][i]) for i in range(3)]
    return math.hypot(*gaps), overlap


def assembly_checks(bounds, args):
    tolerance = args.get('tolerance', .001) * factor(args)
    output = []
    fields = {'ground': {'object_id', 'plane'}, 'contact': {'object_id', 'other_id'},
              'support': {'object_id', 'other_id'}, 'no_overlap': {'object_id', 'other_id'},
              'clearance': {'object_id', 'other_id', 'minimum'},
              'symmetry': {'object_id', 'other_id', 'axis', 'plane'},
              'component_count': {'expected'}, 'connected': set()}
    required = {'ground': {'object_id'}, 'component_count': {'expected'}, 'connected': set()}
    for item in args['checks']:
        kind = item['kind']
        keys = set(item) - {'kind'}
        needs = required.get(kind, {'object_id', 'other_id'})
        if kind == 'clearance':
            needs = needs | {'minimum'}
        if not needs <= keys or not keys <= fields[kind]:
            raise ToolError('INVALID_ARGUMENT', 'Missing or irrelevant fields for assembly check.', {'kind': kind})
        ids = [item[key] for key in ('object_id', 'other_id') if key in item]
        if any(oid not in bounds for oid in ids):
            raise ToolError('INVALID_ARGUMENT', 'Assembly references must belong to object_ids.')
        if len(ids) == 2 and ids[0] == ids[1] and kind != 'symmetry':
            raise ToolError('INVALID_ARGUMENT', 'Pair checks require distinct objects.')
        details = {'method': 'evaluated_world_aabb', 'tolerance_m': tolerance}
        if kind == 'component_count':
            passed = len(bounds) == item['expected']
            ids = list(bounds)
            details.update(actual=len(bounds), expected=item['expected'])
        elif kind == 'connected':
            ids = list(bounds)
            visited = {ids[0]}
            pending = [ids[0]]
            while pending:
                current = pending.pop()
                for other in ids:
                    if other not in visited and pair_metrics(bounds[current], bounds[other])[0] <= tolerance:
                        visited.add(other)
                        pending.append(other)
            passed = len(visited) == len(ids)
            details['disconnected_ids'] = [oid for oid in ids if oid not in visited]
        elif kind == 'ground':
            plane = item.get('plane', 0) * factor(args)
            gap = bounds[ids[0]]['min'][2] - plane
            passed = abs(gap) <= tolerance
            details.update(bottom_m=bounds[ids[0]]['min'][2], plane_m=plane, gap_m=gap)
        elif kind == 'symmetry':
            axis = 'XYZ'.index(item.get('axis', 'X'))
            plane = item.get('plane', 0) * factor(args)
            mirrored = {k: list(v) for k, v in bounds[ids[0]].items()}
            mirrored['min'][axis] = 2*plane - bounds[ids[0]]['max'][axis]
            mirrored['max'][axis] = 2*plane - bounds[ids[0]]['min'][axis]
            error = max(abs(mirrored[k][i] - bounds[ids[1]][k][i]) for k in mirrored for i in range(3))
            passed = error <= tolerance
            details.update(max_error_m=error, axis=item.get('axis', 'X'), plane_m=plane)
        else:
            a, b = bounds[ids[0]], bounds[ids[1]]
            gap, overlap = pair_metrics(a, b)
            details.update(gap_m=gap, overlap_m=overlap)
            if kind == 'contact':
                passed = gap <= tolerance and min(overlap) >= -tolerance and min(overlap) <= tolerance
            elif kind == 'no_overlap':
                passed = not all(v > tolerance for v in overlap)
            elif kind == 'clearance':
                minimum = item['minimum'] * factor(args)
                passed = gap + tolerance >= minimum
                details['minimum_m'] = minimum
            else:
                # object_id is the lower support, other_id is the supported part.
                vertical_gap = b['min'][2] - a['max'][2]
                passed = abs(vertical_gap) <= tolerance and all(overlap[i] > 0 for i in range(2))
                details['vertical_gap_m'] = vertical_gap
        output.append(check('ASSEMBLY_' + kind.upper(), passed, ids, **details))
    return output


class ValidationService:
    def __init__(self, *, identities, scene, depsgraph):
        self.identities, self.scene, self.depsgraph = identities, scene, depsgraph

    def register(self, registry):
        for name, schema, handler, description in (
            ('geometry', GEOMETRY_SCHEMA, self.geometry, 'Validate bounded base or evaluated mesh topology.'),
            ('dimensions', DIMENSIONS_SCHEMA, self.dimensions, 'Check evaluated world bounds against expected dimensions.'),
            ('assembly', ASSEMBLY_SCHEMA, self.assembly, 'Check declared approximate relationships using evaluated world AABBs.'),
            ('asset', ASSET_SCHEMA, self.asset, 'Combine technical geometry, dimension, assembly and material checks.')):
            registry.register(ToolSpec('validate.' + name, description, input_schema=schema,
                                      output_schema=REPORT_SCHEMA), handler)

    def _resolve(self, args):
        ids = args['object_ids']
        if len(set(ids)) != len(ids):
            raise ToolError('INVALID_ARGUMENT', 'Object IDs must be unique.')
        for oid in ids:
            validate_uuid(oid)
        index = self.identities.index()
        scene_keys = {object_key(obj) for obj in self.scene().objects}
        result = {}
        for oid in ids:
            if oid not in index:
                raise ToolError('OBJECT_NOT_FOUND', 'No current object has this UUID.', {'object_id': oid})
            obj = index[oid]
            if object_key(obj) not in scene_keys:
                raise ToolError('OBJECT_NOT_IN_SCENE', 'Object is not in the active scene.')
            if obj.type != 'MESH':
                raise ToolError('OBJECT_NOT_MESH', 'Validation currently requires mesh objects.')
            if obj.mode != 'OBJECT':
                raise ToolError('UNSUPPORTED_OBJECT_MODE', 'Validation requires Object mode.')
            result[oid] = obj
        return result

    def _snapshots(self, objects, evaluated):
        graph = self.depsgraph() if evaluated else None
        budget = 0
        result = []
        for oid, obj in objects.items():
            source = obj.evaluated_get(graph) if evaluated else obj
            if evaluated and not getattr(source, 'is_evaluated', True):
                raise ToolError('OBJECT_NOT_EVALUATED', 'Object is excluded from the dependency graph.')
            mesh = source.data
            budget += len(mesh.vertices) + len(mesh.edges) + len(mesh.polygons) + len(mesh.loops)
            if budget > MAX_VALIDATION_ELEMENTS:
                raise ToolError('VALIDATION_LIMIT_EXCEEDED', 'Meshes exceed the total validation element budget.')
            matrix = [[float(v) for v in row] for row in source.matrix_world]
            if not finite(matrix):
                raise ToolError('INVALID_GEOMETRY', 'World transform must be finite.')
            points = [tuple(sum(matrix[i][j] * vertex.co[j] for j in range(3)) + matrix[i][3]
                            for i in range(3)) for vertex in mesh.vertices]
            result.append({'object_id': oid, 'points': points,
                'edges': [tuple(edge.vertices) for edge in mesh.edges],
                'faces': [tuple(face.vertices) for face in mesh.polygons],
                'normals': [tuple(face.normal) for face in mesh.polygons],
                'negative_scale': any(v < 0 for v in obj.scale) or source.matrix_world.determinant() < 0})
        return result

    def _bounds(self, objects):
        bounds = {}
        for data in self._snapshots(objects, True):
            points = data['points']
            if not points or not finite(points):
                raise ToolError('INVALID_GEOMETRY', 'Bounds require nonempty finite evaluated meshes.',
                                {'object_id': data['object_id']})
            bounds[data['object_id']] = {'min': [min(p[i] for p in points) for i in range(3)],
                                         'max': [max(p[i] for p in points) for i in range(3)]}
        return bounds

    def _geometry(self, objects, args):
        checks = [check('UUID_UNIQUENESS', True, objects)]
        for data in self._snapshots(objects, args.get('geometry', 'base') == 'evaluated'):
            checks.extend(geometry_checks(data, args.get('require_closed', True), args.get('area_epsilon', 1e-12)))
        return checks

    def geometry(self, args):
        return report(self._geometry(self._resolve(args), args))

    def dimensions(self, args):
        return report(dimension_checks(self._bounds(self._resolve(args)), args))

    def assembly(self, args):
        return report(assembly_checks(self._bounds(self._resolve(args)), args))

    def asset(self, args):
        objects = self._resolve(args)
        checks = self._geometry(objects, args)
        if 'dimensions' in args or 'assembly' in args:
            bounds = self._bounds(objects)
            if 'dimensions' in args:
                checks.extend(dimension_checks(bounds, args['dimensions']))
            if 'assembly' in args:
                checks.extend(assembly_checks(bounds, args['assembly']))
        if args.get('require_materials', False):
            for oid, obj in objects.items():
                slots = obj.material_slots
                missing = sum(1 for face in obj.data.polygons if face.material_index >= len(slots)
                              or slots[face.material_index].material is None)
                checks.append(check('MATERIAL_ASSIGNMENT', missing == 0 and bool(obj.data.polygons),
                                    [oid], unassigned_faces=missing, method='base_face_slots'))
        return report(checks)
