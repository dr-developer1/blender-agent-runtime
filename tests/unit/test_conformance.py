import io
import unittest

from conformance.__main__ import EvidenceResult


class EvidenceTests(unittest.TestCase):
    def run_case(self, case):
        return unittest.TextTestRunner(stream=io.StringIO(), resultclass=EvidenceResult).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(case))

    def test_failed_subtest_is_not_recorded_as_passed(self):
        class Case(unittest.TestCase):
            def test_failure(self):
                with self.subTest(tool='fixture'):
                    self.assertEqual(1, 2)
        result = self.run_case(Case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.records[0]['status'], 'failed')

    def test_skip_reason_and_metrics_are_preserved(self):
        class Case(unittest.TestCase):
            def test_skip(self):
                self.skipTest('Blender unavailable')

            def test_metrics(self):
                self.metrics = {'object_count': 2001}
        result = self.run_case(Case)
        by_name = {row['test'].split('.')[-1]: row for row in result.records}
        self.assertEqual(by_name['test_skip']['status'], 'skipped')
        self.assertEqual(by_name['test_skip']['reason'], 'Blender unavailable')
        self.assertEqual(by_name['test_metrics']['metrics'], {'object_count': 2001})

    def test_error_is_recorded(self):
        class Case(unittest.TestCase):
            def test_error(self):
                raise RuntimeError('fixture')
        result = self.run_case(Case)
        self.assertEqual(result.records[0]['status'], 'error')
        self.assertGreaterEqual(result.records[0]['seconds'], 0)
