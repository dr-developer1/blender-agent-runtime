import io
from types import SimpleNamespace
import unittest

from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.identity import UUID_PROPERTY
from runtime.logging import EventLogger
from runtime.schemas import validate_response, validate_schema, object_schema


class Object(dict):
    def __init__(self, number, name, kind='MESH', visible=True, origin=(0, 0, 0), tags=None):
        super().__init__({UUID_PROPERTY: f'00000000-0000-4000-8000-{number:012d}', 'bar_tags': tags or {}})
        self.name, self.type, self.visible = name, kind, visible
        self.hide_render = not visible
        self.matrix_world = SimpleNamespace(translation=origin)

    def visible_get(self, **kwargs):
        return self.visible


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.objects = [Object(3, 'Bolt_A', origin=(1, 2, 3), tags={'role': 'bolt', 'batch': 'one'}),
                        Object(1, 'Lamp', 'LIGHT', False, origin=(10, 0, 0)),
                        Object(2, 'Bolt_B', tags={'role': 'bolt'})]
        child = SimpleNamespace(name='Parts', objects=[self.objects[0], self.objects[2]], children=[])
        self.scene = SimpleNamespace(name='Fixture', objects=self.objects, frame_current=1,
                                     collection=SimpleNamespace(name='Root', objects=[self.objects[1]], children=[child]))
        self.api = RuntimeAPI(blender_version='fixture', objects=lambda: self.objects,
                              scene=lambda: self.scene, logger=EventLogger(io.StringIO()))

    def call(self, tool='scene.list_objects', arguments=None, **fields):
        message = {'api_version': '1.0', 'session_id': self.api.state.session_id,
                   'expected_revision': self.api.state.revision, 'tool': tool,
                   'arguments': {} if arguments is None else arguments, **fields}
        result = self.api.execute(message)
        validate_response(result)
        return result

    def test_summary_counts_and_read_only_identity(self):
        before = [dict(obj) for obj in self.objects]
        summary = self.call('scene.summary')['result']
        self.assertEqual(summary, {'scene_name': 'Fixture', 'object_count': 3,
                                  'object_types': {'LIGHT': 1, 'MESH': 2}, 'collection_count': 2,
                                  'visible_count': 2, 'render_enabled_count': 2, 'frame': 1})
        self.assertEqual(before, self.objects)
        self.assertEqual(self.api.state.revision, 0)
        self.assertTrue(self.api.features['scene_observation'])
        self.assertEqual(len(self.api.registry.names()), 12)

    def test_each_filter_and_combination(self):
        for filters, names in (({'object_type': 'LIGHT'}, ['Lamp']),
                               ({'collection': 'Parts'}, ['Bolt_B', 'Bolt_A']),
                               ({'visible': False}, ['Lamp']),
                               ({'name_pattern': 'Bolt_?'}, ['Bolt_B', 'Bolt_A']),
                               ({'name_pattern': 'bolt_*'}, []),
                               ({'tags': {'role': 'bolt', 'batch': 'one'}}, ['Bolt_A']),
                               ({'region': {'min': [1, 2, 3], 'max': [1, 2, 3]}}, ['Bolt_A']),
                               ({'object_type': 'MESH', 'visible': True, 'collection': 'Parts',
                                 'tags': {'role': 'bolt'}, 'name_pattern': '*B'}, ['Bolt_B']),
                               ({'collection': 'missing'}, [])):
            with self.subTest(filters=filters):
                result = self.call(arguments=filters)['result']
                self.assertEqual([row['name'] for row in result['objects']], names)
                self.assertEqual(result['total'], len(names))

    def test_pagination_sorted_unique_and_page_size_can_change(self):
        first = self.call(arguments={'limit': 1})['result']
        self.assertEqual(first['objects'][0]['name'], 'Lamp')
        self.assertTrue(first['next_cursor'])
        second = self.call(arguments={'limit': 2, 'cursor': first['next_cursor']})['result']
        self.assertEqual([row['name'] for row in second['objects']], ['Bolt_B', 'Bolt_A'])
        self.assertEqual(second['total'], 3)
        self.assertIsNone(second['next_cursor'])
        repeat = self.call(arguments={'limit': 2, 'cursor': first['next_cursor']})['result']
        self.assertEqual(second, repeat)

    def test_empty_scene_and_bounded_default_pages(self):
        self.objects.clear()
        self.scene.collection.objects.clear()
        self.scene.collection.children.clear()
        self.assertEqual(self.call()['result'], {'objects': [], 'total': 0, 'next_cursor': None})
        self.assertEqual(self.call('scene.summary')['result']['object_types'], {})
        self.objects.extend(Object(i + 1, f'Object_{i}') for i in range(253))
        page = self.call()['result']
        self.assertEqual(len(page['objects']), 50)
        gathered = []
        arguments = {'limit': 100}
        while True:
            page = self.call(arguments=arguments)['result']
            gathered.extend(row['object_id'] for row in page['objects'])
            if page['next_cursor'] is None:
                break
            arguments['cursor'] = page['next_cursor']
        self.assertEqual(len(gathered), 253)
        self.assertEqual(len(set(gathered)), 253)

    def test_strict_argument_and_nested_schema_validation(self):
        invalid = ({'limit': 0}, {'limit': 101}, {'limit': True}, {'limit': 1.0}, {'limit': 10**1000},
                   {'visible': 1}, {'unknown': 'x'}, {'tags': {'role': 1}}, {'tags': []},
                   {'region': {'min': [0, 0], 'max': [1, 1, 1]}},
                   {'region': {'min': [2, 0, 0], 'max': [1, 1, 1]}},
                   {'region': {'min': [False, 0, 0], 'max': [1, 1, 1]}},
                   {'region': {'min': [float('nan'), 0, 0], 'max': [1, 1, 1]}},
                   {'region': {'min': [0, 0, 0], 'max': [1, 1, 1], 'extra': 1}},
                   {'object_type': ''}, {'name_pattern': 'x' * 257}, {'cursor': ''})
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                self.assertEqual(self.call(arguments=arguments)['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.call('scene.summary', {'limit': 1})['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.api.state.revision, 0)

    def test_cursor_tampering_filter_changes_and_wrong_runtime(self):
        cursor = self.call(arguments={'limit': 1})['result']['next_cursor']
        for bad in ('nonsense', 'x.é', cursor + 'x', 'x' + cursor):
            self.assertEqual(self.call(arguments={'cursor': bad})['error']['code'], 'INVALID_CURSOR')
        self.assertEqual(self.call(arguments={'cursor': cursor, 'visible': True})['error']['code'], 'INVALID_CURSOR')
        other = RuntimeAPI(blender_version='other', objects=lambda: self.objects, scene=lambda: self.scene,
                           logger=EventLogger(io.StringIO()))
        result = other.execute({'api_version': '1.0', 'session_id': other.state.session_id,
                                'expected_revision': 0, 'tool': 'scene.list_objects', 'arguments': {'cursor': cursor}})
        self.assertEqual(result['error']['code'], 'INVALID_CURSOR')

    def test_cursor_stale_after_revision_and_untracked_scene_changes(self):
        cursor = self.call(arguments={'limit': 1})['result']['next_cursor']
        self.api.registry.register(ToolSpec('test.edit', 'fixture', side_effects=('scene',)), lambda args: {})
        self.call('test.edit')
        self.assertEqual(self.call(arguments={'cursor': cursor})['error']['code'], 'STALE_SCENE_STATE')
        self.assertEqual(self.call(expected_revision=0)['error']['code'], 'STALE_SCENE_STATE')
        for change in (lambda: setattr(self.objects[0], 'name', 'Renamed'),
                       lambda: setattr(self.objects[0], 'visible', False),
                       lambda: self.objects.pop()):
            cursor = self.call(arguments={'limit': 1})['result']['next_cursor']
            change()
            self.assertEqual(self.call(arguments={'cursor': cursor})['error']['code'], 'STALE_SCENE_STATE')

    def test_unmanaged_collision_and_malformed_identity_fail_without_writes(self):
        self.objects.append(Object(4, 'New'))
        del self.objects[-1][UUID_PROPERTY]
        self.assertEqual(self.call()['error']['code'], 'OBJECT_NOT_MANAGED')
        self.assertNotIn(UUID_PROPERTY, self.objects[-1])
        self.objects[-1][UUID_PROPERTY] = self.objects[0][UUID_PROPERTY]
        self.assertEqual(self.call()['error']['code'], 'UUID_COLLISION')
        self.objects[-1][UUID_PROPERTY] = 'broken'
        self.assertEqual(self.call('scene.summary')['error']['code'], 'INVALID_OBJECT_UUID')
        self.assertEqual(self.api.state.revision, 0)

    def test_response_budget_rejection_keeps_api_usable(self):
        self.objects[0]['bar_tags'] = {'huge': 'x' * (1024 * 1024)}
        self.assertEqual(self.call()['error']['code'], 'RESPONSE_TOO_LARGE')
        self.assertTrue(self.call('scene.summary')['success'])

    def test_registration_rejects_unenforced_nested_schemas(self):
        for rule in ({'type': 'string', 'pattern': 'x'}, {'type': ['string']},
                     {'type': 'array'}, {'type': 'integer', 'minimum': True},
                     {'type': 'string', 'minLength': 2, 'maxLength': 1},
                     {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': {'type': 'bad'}}):
            with self.subTest(rule=rule):
                with self.assertRaises(ValueError):
                    validate_schema(object_schema({'field': rule}))

    def test_hierarchy_pagination_and_cursor_endpoint_binding(self):
        self.objects[0].parent = self.objects[1]
        first = self.call('scene.get_hierarchy', {'limit': 1})['result']
        second = self.call('scene.get_hierarchy', {'limit': 100, 'cursor': first['next_cursor']})['result']
        nodes = first['nodes'] + second['nodes']
        by_id = {node['object_id']: node for node in nodes}
        self.assertEqual(by_id[self.objects[0][UUID_PROPERTY]]['parent_id'], self.objects[1][UUID_PROPERTY])
        self.assertIsNone(by_id[self.objects[1][UUID_PROPERTY]]['parent_id'])
        self.assertEqual(len(nodes), 3)
        self.assertEqual(self.call(arguments={'cursor': first['next_cursor']})['error']['code'], 'INVALID_CURSOR')
        self.assertEqual(self.call('scene.get_hierarchy', {'object_type': 'MESH'})['error']['code'], 'INVALID_ARGUMENT')
        self.objects[0].parent = None
        self.assertEqual(self.call('scene.get_hierarchy', {'cursor': first['next_cursor']})['error']['code'], 'STALE_SCENE_STATE')

    def evaluated_api(self):
        class Matrix(list):
            @property
            def translation(self):
                return [self[axis][3] for axis in range(3)]
        matrix = Matrix([[2, 0, 0, 10], [0, -3, 0, 20], [0, 0, 4, 30], [0, 0, 0, 1]])
        def mesh(points, edges, faces, triangles):
            return SimpleNamespace(vertices=[SimpleNamespace(co=point) for point in points],
                edges=[None] * edges, polygons=[None] * faces, loop_triangles=[None] * triangles,
                calc_loop_triangles=lambda: None)
        obj = self.objects[0]
        obj.data = mesh([(-1, -1, -1), (1, 1, 1)], 1, 1, 1)
        evaluated = SimpleNamespace(type='MESH', matrix_world=matrix, is_evaluated=True,
                                    data=mesh([(-1, -1, -1), (3, 1, 1)], 2, 2, 2))
        obj.evaluated_get = lambda depsgraph: evaluated
        api = RuntimeAPI(blender_version='fixture', objects=lambda: self.objects, scene=lambda: self.scene,
                         depsgraph=lambda: object(), logger=EventLogger(io.StringIO()))
        return api, evaluated

    def test_targeted_evaluated_geometry_and_world_bounds(self):
        self.api, _ = self.evaluated_api()
        object_id = self.objects[0][UUID_PROPERTY]
        result = self.call('scene.inspect_objects', {'object_ids': [object_id]})['result']['objects'][0]
        self.assertEqual(result['object_id'], object_id)
        self.assertEqual(result['base_geometry']['vertices'], 2)
        self.assertEqual(result['evaluated_geometry']['faces'], 2)
        self.assertEqual(result['evaluated_bounds'], {'min': [8, 17, 26], 'max': [16, 23, 34]})
        self.assertEqual(result['evaluated_dimensions'], [8, 6, 8])
        self.assertEqual(result['world_origin'], [10, 20, 30])
        self.assertEqual(self.api.state.revision, 0)

    def test_inspection_preflight_and_missing_evaluation(self):
        self.assertEqual(self.call('scene.inspect_objects', {'object_ids': []})['error']['code'], 'UNKNOWN_TOOL')
        self.api, evaluated = self.evaluated_api()
        object_id = self.objects[0][UUID_PROPERTY]
        for ids, code in (([], 'INVALID_ARGUMENT'), ([object_id] * 2, 'INVALID_ARGUMENT'),
                          ([object_id] * 101, 'INVALID_ARGUMENT'), (['invalid'], 'INVALID_OBJECT_UUID'),
                          (['00000000-0000-4000-8000-999999999999'], 'OBJECT_NOT_FOUND')):
            self.assertEqual(self.call('scene.inspect_objects', {'object_ids': ids})['error']['code'], code)
        evaluated.is_evaluated = False
        self.assertEqual(self.call('scene.inspect_objects', {'object_ids': [object_id]})['error']['code'], 'OBJECT_NOT_EVALUATED')
        self.scene = SimpleNamespace(name='Empty', objects=[], frame_current=1,
                                     collection=SimpleNamespace(name='Root', objects=[], children=[]))
        self.assertEqual(self.call('scene.inspect_objects', {'object_ids': [object_id]})['error']['code'], 'OBJECT_NOT_IN_SCENE')

    def test_non_geometry_bounds_are_nullable(self):
        self.api, evaluated = self.evaluated_api()
        self.objects[0].type = 'EMPTY'
        evaluated.type = 'EMPTY'
        evaluated.bound_box = [(0, 0, 0)] * 8
        result = self.call('scene.inspect_objects', {'object_ids': [self.objects[0][UUID_PROPERTY]]})['result']['objects'][0]
        for field in ('base_geometry', 'evaluated_geometry', 'evaluated_bounds', 'evaluated_dimensions', 'bounds_method'):
            self.assertIsNone(result[field])
