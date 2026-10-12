import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from benchmarks.catalog import CATALOG
from benchmarks.expansion import build_recipe, evaluate, scene_ids
from benchmarks.replay import BridgeClient, run_replay
from benchmarks.stool import Exercise
from controller.client import BlenderClient

BLENDER = os.environ.get('BLENDER_EXECUTABLE', 'blender')


@unittest.skipUnless(shutil.which(BLENDER), 'Blender executable unavailable')
class ExpansionIntegrationTests(unittest.TestCase):
    def test_all_twenty_public_api_assets_and_rollback(self):
        self.metrics = {}
        # Every recipe rolls back to the same isolated startup scene, preventing
        # orphan materials or discarded cutter data accumulating across fixtures.
        with BlenderClient(executable=BLENDER, request_timeout=90) as client:
            e = Exercise(client)
            original = e.call('scene.inspect_objects', {'object_ids': scene_ids(e)})
            for brief in CATALOG.values():
                with self.subTest(benchmark=brief.name):
                    control = e.call('transaction.begin')
                    control = {'transaction_id': control['transaction_id']}
                    start = len(e.trace)
                    try:
                        roles = build_recipe(e, brief)
                        report = evaluate(e, brief, roles)
                        self.assertTrue(report['supported_technical_passed'], report['failures'])
                        self.assertFalse(report['full_benchmark_passed'])
                        self.assertTrue(all(c['response']['success'] for c in e.trace[start:]))
                        if brief.name == 'bottle':
                            # The old stepped cylinder has the same outer bounds,
                            # but must fail the independently checked shoulder slope.
                            material = e.call('material.create', {})['material_id']
                            old_shoulder = e.call('object.create_primitive', {
                                'primitive': 'CYLINDER', 'size': 90, 'unit': 'mm',
                                'scale': [1, 1, 20/90], 'location': [0, 0, 200],
                                'segments': 128})['object_id']
                            e.call('material.assign', {'object_id': old_shoulder,
                                                      'material_id': material})
                            e.call('object.delete', {'object_id': roles['shoulder']})
                            roles['shoulder'] = old_shoulder
                            stepped = evaluate(e, brief, roles)
                            self.assertTrue(stepped['dimensions']['passed'])
                            self.assertFalse(stepped['declared_taper_surfaces']['passed'])
                        if brief.name == 'desk_lamp':
                            # The old floating stem still passes AABB connectivity.
                            # Actual opposing roof/stem faces must reject it.
                            e.call('object.transform', {'object_id': roles['stem'], 'unit': 'mm',
                                'location': [0, 0, 175], 'scale': [20/422, 20/422, 310/422]})
                            floating = evaluate(e, brief, roles)
                            self.assertTrue(floating['assembly']['passed'])
                            self.assertFalse(floating['declared_surface_joints']['passed'])
                        if brief.name == 'sci_fi_crate':
                            # Fill both recesses, restoring the old overlapped front.
                            front = next(p for p in brief.parts if p.role == 'front')
                            solid = e.call('object.create_primitive', {
                                'primitive': 'CUBE', 'size': 570, 'unit': 'mm',
                                'scale': [d/570 for d in front.dimensions],
                                'location': list(front.location)})['object_id']
                            e.call('mesh.boolean', {'object_id': roles['front'],
                                                   'operand_id': solid, 'operation': 'UNION'})
                            e.call('object.delete', {'object_id': solid})
                            overlapped = evaluate(e, brief, roles)
                            self.assertTrue(overlapped['dimensions']['passed'])
                            self.assertFalse(overlapped['recess_surfaces']['passed'])
                        if brief.name == 'pipe_connector':
                            # Fill the bore without changing outer bounds: a box-only
                            # evaluator would accept this broken connector.
                            solid = e.call('object.create_primitive', {
                                'primitive': 'CYLINDER', 'size': 60, 'unit': 'mm',
                                'scale': [1, 1, 130/60], 'location': [0, 0, 65],
                                'segments': 64})['object_id']
                            e.call('mesh.boolean', {'object_id': roles['tube'],
                                                   'operand_id': solid, 'operation': 'UNION'})
                            e.call('object.delete', {'object_id': solid})
                            filled = evaluate(e, brief, roles)
                            self.assertTrue(filled['dimensions']['passed'])
                            self.assertFalse(filled['cavity_surfaces']['passed'])
                        if brief.name == 'planter':
                            # Filling only the drainage bore leaves the large cavity
                            # and all outer dimensions unchanged.
                            plug=e.call('object.create_primitive', {'primitive':'CYLINDER',
                                'size':14,'unit':'mm','scale':[1,1,15/14],
                                'location':[0,0,7.5],'segments':128})['object_id']
                            e.call('mesh.boolean', {'object_id':roles['pot'],
                                'operand_id':plug,'operation':'UNION'})
                            e.call('object.delete', {'object_id':plug})
                            blocked=evaluate(e,brief,roles)
                            self.assertTrue(blocked['dimensions']['passed'])
                            self.assertTrue(blocked['cavity_surfaces']['passed'])
                            self.assertFalse(blocked['additional_bore_surfaces']['passed'])
                        if brief.name == 'appliance_housing':
                            plug=e.call('object.create_primitive', {'primitive':'CUBE',
                                'size':80,'unit':'mm','scale':[12/80,20/80,1],
                                'location':[-120,140,120]})['object_id']
                            e.call('mesh.boolean', {'object_id':roles['housing'],
                                'operand_id':plug,'operation':'UNION'})
                            e.call('object.delete', {'object_id':plug})
                            blocked=evaluate(e,brief,roles)
                            self.assertTrue(blocked['dimensions']['passed'])
                            self.assertFalse(blocked['aperture_surfaces']['passed'])
                        # Move a role: independently ensure acceptance notices a real defect.
                        target = brief.parts[0]
                        e.call('object.transform', {'object_id': roles[target.role], 'unit': 'mm',
                                                   'location': [10000, 10000, 10000]})
                        broken = evaluate(e, brief, roles)
                        self.assertFalse(broken['supported_technical_passed'])
                        self.metrics[brief.name] = {'calls': len(e.trace)-start,
                                                   'objects': len(roles)}
                    finally:
                        revision = client.revision
                        e.call('transaction.rollback', control)
                        self.assertGreater(client.revision, revision)
                    restored = e.call('scene.inspect_objects', {'object_ids': scene_ids(e)})
                    self.assertEqual(restored, original)

    def test_expansion_bridge_success_and_distinct_replay_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            report = run_replay(CATALOG['product_casing'], path, executable=BLENDER)
            self.assertEqual(report['outcome'], 'transaction.commit')
            self.assertTrue(report['reports']['supported_technical_passed'])
            self.assertEqual(len(list(path.glob('*.png'))), 6)
            self.assertFalse(json.loads((path / 'replay.json').read_text())['autonomous_agent_run'])
            commands = json.loads((path / 'agent_commands.json').read_text())
            self.assertIn('finish', commands[-1])
            self.assertTrue(all(not c.get('tool', '').startswith('transaction.') for c in commands))

    def test_expansion_bridge_invalid_finish_repair_then_failed_acceptance_rollback(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile(mode='w+t') as errors:
            process = subprocess.Popen([sys.executable, '-m', 'benchmarks.agent',
                       '--benchmark', 'planter', '--agent', 'integration fixture',
                       '--blender', BLENDER, '--output', directory],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
                       cwd=Path(__file__).resolve().parents[2])
            try:
                client = BridgeClient(process)
                self.assertEqual(client.ready['roles'], ['pot'])
                self.assertEqual(client.ready['brief']['dimensions'], [300, 300, 350])
                self.assertEqual(client.ready['brief']['parts'][0]['cavity'], [270, 270, 350])
                self.assertIn('bridge_error', client.submit({'finish': []}))
                roles = build_recipe(Exercise(client), CATALOG['planter'])
                client.call('object.transform', {'object_id': roles['pot'], 'unit': 'mm',
                                                 'location': [0, 0, 1000]})
                report = client.submit({'finish': roles})
                self.assertEqual(report['outcome'], 'transaction.rollback')
                self.assertFalse(report['reports']['supported_technical_passed'])
                self.assertEqual(report['metrics']['rollbacks'], 1)
                process.stdin.close()
                self.assertEqual(process.wait(timeout=30), 0)
                trace = json.loads((Path(directory) / 'trace.json').read_text())
                self.assertEqual(trace[-1]['tool'], 'transaction.rollback')
                self.assertIn(roles['pot'], trace[-1]['response']['deleted_ids'])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                if not process.stdin.closed:
                    process.stdin.close()
                process.stdout.close()
