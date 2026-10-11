import unittest
from unittest.mock import Mock

from benchmarks.stool import Exercise, ToolRejected, evaluate
from controller.lifecycle import BlenderProcessError


class BenchmarkTraceTests(unittest.TestCase):
    def test_geometry_failure_is_not_misclassified_as_missing_materials(self):
        passed = {'passed': True, 'checks': []}
        geometry = {'passed': False, 'checks': [{'code': 'NON_MANIFOLD_EDGES', 'passed': False}]}
        asset = {'passed': False, 'checks': geometry['checks'] +
                 [{'code': 'MATERIAL_ASSIGNMENT', 'passed': True}]}
        e = Mock()
        e.call.side_effect = [geometry, passed, passed, passed, asset]
        report = evaluate(e, {'seat': 'seat', 'legs': ['a', 'b', 'c', 'd']})
        self.assertFalse(report['supported_technical_passed'])
        self.assertEqual([f['criterion'] for f in report['failures']], ['geometry'])

    def test_missing_materials_is_now_a_recipe_failure(self):
        passed = {'passed': True, 'checks': []}
        asset = {'passed': False, 'checks': [{'code': 'MATERIAL_ASSIGNMENT', 'passed': False}]}
        e = Mock()
        e.call.side_effect = [passed, passed, passed, passed, asset]
        report = evaluate(e, {'seat': 'seat', 'legs': ['a', 'b', 'c', 'd']})
        self.assertFalse(report['supported_technical_passed'])
        self.assertEqual(report['failures'][0]['classification'], 'model_or_recipe')

    def test_trace_copies_arguments_and_omits_png_without_changing_response(self):
        response = {'success': True, 'result': {'images': [{'png_base64': 'payload', 'byte_count': 5}]}}
        client = Mock()
        client.call.return_value = response
        e = Exercise(client)
        arguments = {'views': ['front']}
        result = e.call('observe.render_multiview', arguments)
        arguments['views'].append('back')
        self.assertEqual(e.trace[0]['arguments'], {'views': ['front']})
        self.assertNotIn('png_base64', e.trace[0]['response']['result']['images'][0])
        self.assertEqual(result['images'][0]['png_base64'], 'payload')

    def test_api_rejection_is_recorded_and_transport_failure_propagates(self):
        client = Mock()
        client.call.side_effect = [
            {'success': False, 'error': {'code': 'INVALID_ARGUMENT'}},
            BlenderProcessError('connection lost')]
        e = Exercise(client)
        with self.assertRaises(ToolRejected):
            e.call('object.create_primitive')
        with self.assertRaises(BlenderProcessError):
            e.call('scene.summary')
        self.assertEqual(len(e.trace), 1)
        self.assertEqual(e.trace[0]['response']['error']['code'], 'INVALID_ARGUMENT')
