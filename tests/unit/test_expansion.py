import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

from benchmarks.catalog import CATALOG
from benchmarks.expansion import evaluate, metrics, object_ids, run_manual
from benchmarks.stool import Exercise


class ExpansionTests(TestCase):
    def test_roles_reject_aliasing_missing_extra_and_non_mapping(self):
        brief = CATALOG['monitor_stand']
        for roles in (None, [], {}, {'top': 'a', 'left': 'a', 'right': 'b'},
                      {'top': 'a', 'left': 'b', 'right': ''},
                      {'top': 'a', 'left': 'b', 'right': 'c', 'extra': 'd'}):
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                object_ids(brief, roles)

    def evaluate_with(self, *, failed_tool=None, extra=False):
        brief = CATALOG['monitor_stand']
        roles = {p.role: str(i) for i,p in enumerate(brief.parts)}
        def call(tool, arguments):
            if tool == 'scene.list_objects':
                return {'objects': [{'object_id': oid} for oid in
                                    list(roles.values()) + (['extra'] if extra else [])],
                        'next_cursor': None}
            return {'passed': tool != failed_tool, 'checks': []}
        e = Mock()
        e.call.side_effect = call
        return evaluate(e, brief, roles)

    def test_failures_are_recipe_criteria_and_quality_is_not_inferred(self):
        report = self.evaluate_with(failed_tool='validate.geometry')
        self.assertFalse(report['supported_technical_passed'])
        self.assertEqual(report['failures'][0]['classification'], 'model_or_recipe')
        self.assertFalse(report['full_benchmark_passed'])
        self.assertIsNone(report['visual_evaluation'])
        self.assertIn('production_readiness', report['unverified'])

    def test_scene_extras_and_missing_materials_fail_acceptance(self):
        self.assertFalse(self.evaluate_with(extra=True)['scene_coverage']['passed'])
        self.assertFalse(self.evaluate_with(failed_tool='validate.asset')['supported_technical_passed'])
        self.assertTrue(self.evaluate_with()['supported_technical_passed'])

    def test_metrics_preserve_error_codes_and_do_not_invent_context_usage(self):
        trace = [{'tool': 'mesh.query', 'seconds': .25,
                  'response': {'success': False, 'error': {'code': 'STALE_SELECTION'}}},
                 {'tool': 'transaction.rollback', 'seconds': .5,
                  'response': {'success': True}}]
        measured = metrics(trace)
        self.assertEqual(measured['structured_rejections'], 1)
        self.assertEqual(measured['selection_rejections'], 1)
        self.assertEqual(measured['rollbacks'], 1)
        self.assertEqual(measured['tool_seconds'], .75)
        self.assertIsNone(measured['context_usage'])

    def test_single_render_trace_omits_payload_without_mutating_result(self):
        client = Mock()
        client.call.return_value = {'success': True, 'result': {'png_base64': 'png'}}
        e = Exercise(client)
        self.assertEqual(e.call('observe.render')['png_base64'], 'png')
        self.assertNotIn('png_base64', e.trace[0]['response']['result'])
        self.assertGreaterEqual(e.trace[0]['seconds'], 0)

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'report.json').write_text('original')
            with self.assertRaises(ValueError):
                run_manual(CATALOG['planter'], path, executable='missing')
            self.assertEqual((path / 'report.json').read_text(), 'original')
