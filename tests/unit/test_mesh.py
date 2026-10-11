import unittest

from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.errors import ToolError
from runtime.mesh import EXTRUDE_SCHEMA, INSET_SCHEMA, BEVEL_SCHEMA, BOOLEAN_SCHEMA
from runtime.schemas import validate_arguments


class MeshContractTests(unittest.TestCase):
    def test_prepare_resolves_before_mutation_and_handler_runs_after(self):
        api = RuntimeAPI(blender_version='test')
        observed = []
        def prepare(args):
            observed.append(api.state.revision)
            return {'indices': [3]}
        def handler(args, selected):
            observed.append(api.state.revision)
            return selected
        api.registry.register(ToolSpec('test.mesh', 'fixture', side_effects=('topology_change',)),
                              handler, prepare=prepare)
        result = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
            'expected_revision': 0, 'tool': 'test.mesh', 'arguments': {}})
        self.assertTrue(result['success'])
        self.assertEqual(observed, [0, 1])
        self.assertEqual(result['result'], {'indices': [3]})

    def test_failed_preparation_consumes_one_revision_without_handler(self):
        api = RuntimeAPI(blender_version='test')
        def prepare(args):
            raise ToolError('STALE_SELECTION', 'fixture')
        def handler(args, selected):
            self.fail('Handler must not run')
        api.registry.register(ToolSpec('test.mesh', 'fixture', side_effects=('topology_change',)),
                              handler, prepare=prepare)
        result = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
            'expected_revision': 0, 'tool': 'test.mesh', 'arguments': {}})
        self.assertEqual(result['error']['code'], 'STALE_SELECTION')
        self.assertEqual(result['revision'], 1)

    def test_bounded_finite_mesh_arguments(self):
        for args, schema in [({'selection_handle': 'h', 'offset': [0,0,float('nan')]}, EXTRUDE_SCHEMA),
            ({'selection_handle': 'h', 'thickness': 0}, INSET_SCHEMA),
            ({'selection_handle': 'h', 'width': 1, 'segments': 17}, BEVEL_SCHEMA),
            ({'selection_handle': 'h', 'width': True}, BEVEL_SCHEMA),
            ({'object_id': 'a', 'operand_id': 'b', 'operation': 'XOR'}, BOOLEAN_SCHEMA)]:
            with self.subTest(args=args), self.assertRaises(ToolError):
                validate_arguments(args, schema)
