import unittest

from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.errors import ToolError
from runtime.objects import CREATE_SCHEMA, TRANSFORM_SCHEMA, primitive_geometry
from runtime.schemas import MutationResult, validate_arguments


class ObjectContractTests(unittest.TestCase):
    def test_mutation_envelope_reports_ids_and_revision(self):
        api = RuntimeAPI(blender_version='test')
        api.registry.register(ToolSpec('test.create', 'fixture', side_effects=('object_creation',)),
                              lambda args: MutationResult({'object_id': 'fixture'}, created_ids=['fixture']))
        response = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                                'expected_revision': 0, 'tool': 'test.create', 'arguments': {}})
        self.assertTrue(response['success'])
        self.assertEqual(response['created_ids'], ['fixture'])
        self.assertEqual(response['result'], {'object_id': 'fixture'})
        self.assertEqual((response['revision_before'], response['revision_after']), (0, 1))

    def test_strict_mutation_schemas(self):
        validate_arguments({'primitive': 'CYLINDER', 'segments': 256, 'unit': 'mm'}, CREATE_SCHEMA)
        for args in ({'primitive': 'SPHERE'}, {'primitive': 'CUBE', 'size': 0},
                     {'primitive': 'CONE', 'segments': 257}, {'primitive': 'PLANE', 'location': [0, 0]},
                     {'primitive': 'CUBE', 'scale': [1, float('inf'), 1]}):
            with self.assertRaises(ToolError):
                validate_arguments(args, CREATE_SCHEMA)
        with self.assertRaises(ToolError):
            validate_arguments({'object_id': 'id', 'rotation': [False, 0, 0]}, TRANSFORM_SCHEMA)

    def test_closed_primitive_edges_have_two_opposite_uses(self):
        for kind in ('CUBE', 'CYLINDER', 'CONE'):
            vertices, faces = primitive_geometry(kind, 2, 17)
            incidence = {}
            for face in faces:
                for a, b in zip(face, face[1:] + face[:1]):
                    self.assertTrue(0 <= a < len(vertices))
                    incidence.setdefault(tuple(sorted((a, b))), []).append((a, b))
            for uses in incidence.values():
                self.assertEqual(len(uses), 2)
                self.assertEqual(uses[0], tuple(reversed(uses[1])))

    def test_object_tools_require_explicit_live_backend(self):
        api = RuntimeAPI(blender_version='test')
        self.assertNotIn('object.transform', api.registry.names())
        self.assertFalse(api.features['scene_mutation'])
        with self.assertRaises(ValueError):
            RuntimeAPI(blender_version='test', object_control=True)
