"""Milestone 14 acceptance gates beyond the inherited correctness fixtures."""
import json
import os
from pathlib import Path
import shutil
import time
import unittest

from controller.client import BlenderClient
from controller.lifecycle import run_headless

BLENDER = os.environ.get('BLENDER_EXECUTABLE', 'blender')
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which(BLENDER), 'Blender executable unavailable')
class RuntimeConformanceTests(unittest.TestCase):
    def test_warm_public_ipc_latency(self):
        with BlenderClient(executable=BLENDER) as client:
            client.call('scene.summary')
            samples = []
            for _ in range(25):
                started = time.perf_counter()
                response = client.call('scene.summary')
                samples.append(time.perf_counter() - started)
                self.assertTrue(response['success'], response)
                self.assertEqual(response['result']['object_count'], 3)
            self.assertEqual(client.revision, 0)
        self.metrics = {'samples': len(samples), 'median_seconds': sorted(samples)[12],
                        'max_seconds': max(samples), 'total_seconds': sum(samples),
                        'budget_seconds': 10}
        self.assertLess(sum(samples), 10, self.metrics)

    def test_api_1_0_compatibility(self):
        baseline = json.loads((ROOT / 'conformance' / 'api_1_0.json').read_text())
        with BlenderClient(executable=BLENDER) as client:
            names = client.call('runtime.list_tools')['result']['tools']
            self.assertEqual(names, sorted(baseline))
            for name in names:
                with self.subTest(tool=name):
                    descriptor = client.call('runtime.describe_tool', {'name': name})['result']
                    contract = {key: descriptor[key] for key in baseline[name]}
                    self.assertEqual(contract, baseline[name])
            for version in ('0.9', '1.1', '2.0'):
                response = client.call('runtime.get_version', api_version=version)
                self.assertEqual(response['error']['code'], 'UNSUPPORTED_API_VERSION')
            self.assertEqual(client.revision, 0)
            self.assertTrue(client.call('scene.summary')['success'])

    def test_large_scene_accuracy_performance_and_repeated_rollback(self):
        result = run_headless(ROOT / 'tests' / 'blender' / 'conformance_stress.py',
                              executable=BLENDER, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_CONFORMANCE_STRESS_OK', result.stdout)
        line = next(line for line in result.stdout.splitlines()
                    if line.startswith('BAR_CONFORMANCE_METRICS '))
        self.metrics = json.loads(line.split(' ', 1)[1])
        self.assertEqual(self.metrics['object_count'], 2001)
        self.assertEqual(self.metrics['rollback_cycles'], 5)
