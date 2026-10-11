import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from benchmarks.stool import Exercise, build_manual
from controller.client import BlenderClient

BLENDER = os.environ.get('BLENDER_EXECUTABLE', 'blender')


@unittest.skipUnless(shutil.which(BLENDER), 'Blender executable unavailable')
class StoolIntegrationTests(unittest.TestCase):
    def test_agent_bridge_rejections_and_disconnect_restore_checkpoint(self):
        commands = [
            {'tool': 'transaction.commit', 'arguments': {}},
            {'tool': 'object.create_primitive', 'arguments': {'primitive': 'INVALID'}},
            {'tool': 'object.create_primitive', 'arguments': {'primitive': 'CUBE'}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, '-m', 'benchmarks.agent', '--blender', BLENDER,
                 '--agent', 'test fixture', '--output', directory],
                input=''.join(json.dumps(c) + '\n' for c in commands),
                capture_output=True, text=True, timeout=90,
                cwd=Path(__file__).resolve().parents[2])
            self.assertEqual(result.returncode, 0, result.stderr)
            output = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertTrue(output[0]['ready'])
            self.assertIn('bridge_error', output[1])
            self.assertEqual(output[2]['error']['code'], 'INVALID_ARGUMENT')
            self.assertTrue(output[3]['success'])
            created_id = output[3]['result']['object_id']
            trace = json.loads((Path(directory) / 'trace.json').read_text())
            self.assertEqual(trace[-1]['tool'], 'transaction.rollback')
            self.assertIn(created_id, trace[-1]['response']['deleted_ids'])
            self.assertFalse((Path(directory) / 'report.json').exists())

    def test_manual_public_api_baseline_and_recovery(self):
        with BlenderClient(executable=BLENDER, request_timeout=90) as client:
            e = Exercise(client)
            roles, reports, images = build_manual(e)
            self.assertTrue(reports['supported_technical_passed'], reports)
            self.assertFalse(reports['full_benchmark_passed'])
            self.assertFalse(reports['materials']['passed'])
            self.assertEqual(len(images['images']), 6)
            self.assertEqual(e.call('scene.summary')['object_count'], 5)
            # Each frustum has a broad upper cap and a smaller foot cap. Check
            # actual local face areas, independently of creation names/trace.
            for leg in roles['legs']:
                for direction, minimum, maximum in (
                        ([0, 0, -1], .0014, .0017),
                        ([0, 0, 1], .0006, .0008)):
                    cap = e.call('mesh.query', {
                        'object_id': leg, 'element_type': 'FACE', 'space': 'LOCAL',
                        'selectors': [
                            {'kind': 'normal_direction', 'direction': direction, 'angle_degrees': 1},
                            {'kind': 'area_range', 'minimum': minimum, 'maximum': maximum}],
                    })
                    self.assertEqual(cap['matched_count'], 1, cap)
            checkpoint = e.call('transaction.begin')
            before = client.revision
            e.call('object.delete', {'object_id': roles['legs'][0]})
            e.call('transaction.rollback', {'transaction_id': checkpoint['transaction_id']})
            self.assertGreater(client.revision, before)
            self.assertEqual(len(e.call('scene.inspect_objects', {
                'object_ids': [roles['seat'], *roles['legs']]})['objects']), 5)
            self.assertTrue(all('png_base64' not in image for entry in e.trace
                                for image in entry['response'].get('result', {}).get('images', [])))
