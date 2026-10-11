import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from controller.client import BlenderClient
from controller.lifecycle import BlenderProcessError, run_headless

BLENDER = os.environ.get('BLENDER_EXECUTABLE', 'blender')


@unittest.skipUnless(shutil.which(BLENDER), 'Blender executable unavailable')
class ApiIntegrationTests(unittest.TestCase):
    def test_public_discovery_contract_and_recovery(self):
        with BlenderClient(executable=BLENDER) as client:
            version = client.call('runtime.get_version')
            self.assertTrue(version['success'])
            self.assertEqual(version['api_version'], '1.0')
            self.assertTrue(version['result']['blender_version'])
            features = client.call('runtime.get_supported_features')['result']
            self.assertTrue(features['object_identity'])
            names = client.call('runtime.list_tools')['result']['tools']
            for name in names:
                self.assertTrue(client.call('runtime.describe_tool', {'name': name})['success'])
            self.assertEqual(client.call('runtime.list_tools', api_version='9.0')['error']['code'],
                             'UNSUPPORTED_API_VERSION')
            self.assertEqual(client.call('mesh.unsupported')['error']['code'], 'UNKNOWN_TOOL')
            self.assertEqual(client.call('runtime.describe_tool', {'name': False})['error']['code'],
                             'INVALID_ARGUMENT')
            self.assertTrue(client.call('runtime.get_limits')['success'])
            self.assertTrue(client.request('process.ping')['success'])
        events = [json.loads(line) for line in client.log_output.splitlines() if line.startswith('{')]
        self.assertTrue(events)
        self.assertEqual(sum(not event['success'] for event in events), 3)
        self.assertTrue(all(event['event'] == 'tool_call' for event in events))

    def test_restart_and_state_preconditions_over_ipc(self):
        with BlenderClient(executable=BLENDER) as first:
            old_session = first.session_id
            self.assertEqual(first.revision, 0)
            read = first.call('runtime.get_version')
            self.assertEqual(read['session_id'], old_session)
            self.assertEqual((read['revision_before'], read['revision_after']), (0, 0))
            stale = first.call('runtime.get_version', expected_revision=1)
            self.assertEqual(stale['error']['code'], 'STALE_SCENE_STATE')
            self.assertEqual(first.revision, 0)
            invalid = first.call('runtime.get_version', expected_revision=True)
            self.assertEqual(invalid['error']['code'], 'INVALID_REQUEST')
            self.assertTrue(first.call('runtime.get_version')['success'])
        with BlenderClient(executable=BLENDER) as second:
            self.assertNotEqual(second.session_id, old_session)
            rejected = second.call('runtime.get_version', session_id=old_session)
            self.assertEqual(rejected['error']['code'], 'SESSION_MISMATCH')
            self.assertEqual(rejected['session_id'], second.session_id)
            self.assertTrue(second.call('runtime.get_version')['success'])

    def test_real_scene_mutation_and_restore_advance_timeline(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'state_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_STATE_HEADLESS_OK', result.stdout)

    def test_real_object_identity_lifecycle(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'identity_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_IDENTITY_HEADLESS_OK', result.stdout)

    def test_uuid_persists_across_blender_processes(self):
        fixture = Path(__file__).resolve().parents[1] / 'blender' / 'identity_persistence.py'
        with tempfile.TemporaryDirectory(prefix='bar-identity-integration-') as directory:
            for mode in ('write', 'read'):
                script = Path(directory) / (mode + '.py')
                script.write_text('import runpy\nrunpy.run_path(' + repr(str(fixture)) +
                                  ', init_globals=' + repr({'mode': mode, 'path': directory}) + ')\n')
                result = run_headless(script, executable=BLENDER)
                self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('BAR_IDENTITY_PERSISTENCE_OK', result.stdout)

    def test_scene_observation_over_ipc(self):
        with BlenderClient(executable=BLENDER) as client:
            self.assertTrue(client.call('runtime.get_supported_features')['result']['scene_observation'])
            self.assertEqual(len(client.call('runtime.list_tools')['result']['tools']), 31)
            summary = client.call('scene.summary')['result']
            self.assertEqual(summary['object_count'], 3)
            self.assertEqual(summary['object_types'], {'CAMERA': 1, 'LIGHT': 1, 'MESH': 1})
            objects = []
            arguments = {'limit': 1}
            while True:
                response = client.call('scene.list_objects', arguments)
                self.assertTrue(response['success'], response)
                objects.extend(response['result']['objects'])
                cursor = response['result']['next_cursor']
                if cursor is None:
                    break
                arguments['cursor'] = cursor
            self.assertEqual({row['name'] for row in objects}, {'Cube', 'Camera', 'Light'})
            self.assertEqual(len({row['object_id'] for row in objects}), 3)
            filtered = client.call('scene.list_objects', {'object_type': 'MESH'})['result']
            self.assertEqual([row['name'] for row in filtered['objects']], ['Cube'])
            self.assertEqual(client.call('scene.list_objects', {'limit': True})['error']['code'], 'INVALID_ARGUMENT')
            self.assertEqual(client.call('scene.list_objects', {'cursor': 'bad'})['error']['code'], 'INVALID_CURSOR')
            self.assertTrue(client.call('scene.summary')['success'])
            cube_id = filtered['objects'][0]['object_id']
            inspected = client.call('scene.inspect_objects', {'object_ids': [cube_id]})['result']['objects'][0]
            self.assertEqual(inspected['evaluated_dimensions'], [2.0, 2.0, 2.0])
            self.assertEqual(inspected['evaluated_geometry']['vertices'], 8)
            hierarchy = client.call('scene.get_hierarchy')['result']
            self.assertEqual(len(hierarchy['nodes']), 3)
            self.assertEqual(client.revision, 0)

    def test_real_filtered_scene_and_bounded_pagination(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'scene_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_SCENE_HEADLESS_OK', result.stdout)

    def test_real_evaluated_geometry_and_hierarchy(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'geometry_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_GEOMETRY_HEADLESS_OK', result.stdout)

    def test_semantic_selection_over_ipc(self):
        with BlenderClient(executable=BLENDER) as client:
            self.assertTrue(client.call('runtime.get_supported_features')['result']['semantic_selection'])
            cube_id = client.call('scene.list_objects', {'object_type': 'MESH'})['result']['objects'][0]['object_id']
            response = client.call('mesh.query', {'object_id': cube_id, 'element_type': 'EDGE',
                                                 'selectors': [{'kind': 'top'}]})
            self.assertTrue(response['success'], response)
            result = response['result']
            self.assertEqual(result['matched_count'], 4)
            self.assertEqual(result['valid_at_revision'], 0)
            inspected = client.call('mesh.inspect_selection', {'selection_handle': result['selection_handle']})
            self.assertEqual(len(inspected['result']['indices']), 4)
            invalid = client.call('mesh.query', {'object_id': cube_id, 'element_type': 'FACE',
                                                 'selectors': [{'kind': 'normal_direction', 'direction': [0, 0, 0]}]})
            self.assertEqual(invalid['error']['code'], 'INVALID_ARGUMENT')
            self.assertTrue(client.call('scene.summary')['success'])
            token = result['selection_handle']
        with BlenderClient(executable=BLENDER) as client:
            self.assertEqual(client.call('mesh.inspect_selection', {'selection_handle': token})['error']['code'],
                             'INVALID_SELECTION_HANDLE')

    def test_real_semantic_geometry_selection(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'selection_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_SELECTION_HEADLESS_OK', result.stdout)

    def test_object_control_over_ipc(self):
        with BlenderClient(executable=BLENDER) as client:
            self.assertTrue(client.call('runtime.get_supported_features')['result']['scene_mutation'])
            created = client.call('object.create_primitive', {'primitive': 'CUBE', 'size': 450, 'unit': 'mm'})
            self.assertTrue(created['success'], created)
            oid = created['result']['object_id']
            self.assertEqual(created['created_ids'], [oid])
            self.assertEqual(client.revision, 1)
            moved = client.call('object.transform', {'object_id': oid, 'location': [0, 0, 225], 'unit': 'mm'})
            self.assertTrue(moved['success'], moved)
            self.assertEqual(moved['modified_ids'], [oid])
            inspected = client.call('scene.inspect_objects', {'object_ids': [oid]})['result']['objects'][0]
            for dimension in inspected['evaluated_dimensions']:
                self.assertAlmostEqual(dimension, 0.45, places=6)
            duplicate = client.call('object.duplicate', {'object_id': oid})
            self.assertTrue(duplicate['success'], duplicate)
            copied_id = duplicate['result']['object_id']
            parented = client.call('object.set_parent', {'object_id': copied_id, 'parent_id': oid})
            self.assertTrue(parented['success'], parented)
            deleted = client.call('object.delete', {'object_id': oid})
            self.assertEqual(deleted['deleted_ids'], [oid])
            self.assertEqual(deleted['modified_ids'], [copied_id])
            self.assertEqual(client.revision, 5)
            self.assertTrue(client.call('scene.inspect_objects', {'object_ids': [copied_id]})['success'])

    def test_real_object_control(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'object_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_OBJECT_HEADLESS_OK', result.stdout)

    def test_mesh_control_over_ipc(self):
        with BlenderClient(executable=BLENDER) as client:
            oid = client.call('object.create_primitive', {'primitive': 'CUBE'})['result']['object_id']
            def query(kind, selector):
                result = client.call('mesh.query', {'object_id': oid, 'element_type': kind,
                    'selectors': [selector]})
                self.assertTrue(result['success'], result)
                return result['result']['selection_handle']
            for tool, kind, selector, values in [
                ('mesh.extrude', 'FACE', {'kind': 'top'}, {'offset': [0, 0, 250], 'unit': 'mm'}),
                ('mesh.inset', 'FACE', {'kind': 'top'}, {'thickness': .1}),
                ('mesh.bevel', 'EDGE', {'kind': 'manifold'}, {'width': .02, 'segments': 2})]:
                handle = query(kind, selector)
                before = client.revision
                result = client.call(tool, {'selection_handle': handle, **values})
                self.assertTrue(result['success'], result)
                self.assertEqual(result['modified_ids'], [oid])
                self.assertEqual(client.revision, before + 1)
                self.assertEqual(client.call('mesh.inspect_selection', {'selection_handle': handle})
                    ['error']['code'], 'INVALID_SELECTION_HANDLE')
            result = client.call('mesh.cleanup', {'object_id': oid, 'merge_distance': .00001})
            self.assertTrue(result['success'], result)
            operand = client.call('object.create_primitive', {'primitive': 'CUBE',
                'location': [1, 0, 0]})['result']['object_id']
            result = client.call('mesh.boolean', {'object_id': oid, 'operand_id': operand,
                'operation': 'DIFFERENCE'})
            self.assertTrue(result['success'], result)
            self.assertEqual(result['modified_ids'], [oid])
            inspected = client.call('scene.inspect_objects', {'object_ids': [oid, operand]})
            self.assertTrue(inspected['success'], inspected)

    def test_real_mesh_control(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'mesh_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_MESH_HEADLESS_OK', result.stdout)

    def test_validation_over_ipc(self):
        with BlenderClient(executable=BLENDER) as client:
            self.assertTrue(client.call('runtime.get_supported_features')['result']['validation'])
            oid = client.call('scene.list_objects', {'object_type': 'MESH'})['result']['objects'][0]['object_id']
            before = client.revision
            handle = client.call('mesh.query', {'object_id': oid, 'element_type': 'FACE',
                'selectors': [{'kind': 'top'}]})['result']['selection_handle']
            for tool, args in [
                ('validate.geometry', {'object_ids': [oid]}),
                ('validate.dimensions', {'object_ids': [oid], 'expected': [2000,2000,2000], 'unit': 'mm'}),
                ('validate.assembly', {'object_ids': [oid], 'checks': [
                    {'kind': 'ground', 'object_id': oid, 'plane': -1}]}),
                ('validate.asset', {'object_ids': [oid], 'dimensions': {'expected': [2,2,2]}})]:
                response = client.call(tool, args)
                self.assertTrue(response['success'], response)
                self.assertTrue(response['result']['passed'], response)
                self.assertEqual(response['modified_ids'], [])
                self.assertEqual(response['revision_after'], before)
            failed = client.call('validate.dimensions', {'object_ids': [oid], 'expected': [1,1,1]})
            self.assertTrue(failed['success'])
            self.assertFalse(failed['result']['passed'])
            self.assertTrue(client.call('mesh.inspect_selection', {'selection_handle': handle})['success'])
            self.assertEqual(client.call('validate.geometry', {'object_ids': [oid, oid]})
                ['error']['code'], 'INVALID_ARGUMENT')
            self.assertEqual(client.call('validate.geometry', {'object_ids': [oid]}, expected_revision=before+1)
                ['error']['code'], 'STALE_SCENE_STATE')
            self.assertEqual(client.revision, before)

    def test_real_validation(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'validation_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_VALIDATION_HEADLESS_OK', result.stdout)


    def test_transactions_and_scene_diff_over_ipc(self):
        with BlenderClient(executable=BLENDER) as client:
            features = client.call('runtime.get_supported_features')['result']
            self.assertTrue(features['transactions'] and features['scene_diff'])
            oid = client.call('scene.list_objects', {'object_type': 'MESH'})['result']['objects'][0]['object_id']
            session = client.session_id
            baseline = client.call('scene.inspect_objects', {'object_ids': [oid]})['result']
            started = client.call('transaction.begin')
            self.assertTrue(started['success'], started)
            args = {'transaction_id': started['result']['transaction_id']}
            self.assertEqual(client.call('scene.diff', args)['result']['diff']['changes'], [])
            self.assertTrue(client.call('object.transform', {'object_id': oid, 'location': [4, 0, 0]})['success'])
            created = client.call('object.create_primitive', {'primitive': 'CUBE'})['result']['object_id']
            diff = client.call('scene.diff', args)['result']['diff']
            self.assertEqual(diff['created_ids'], [created])
            self.assertEqual(diff['modified_ids'], [oid])
            handle = client.call('mesh.query', {'object_id': oid, 'element_type': 'FACE',
                'selectors': [{'kind': 'top'}]})['result']['selection_handle']
            before = client.revision
            restored = client.call('transaction.rollback', args)
            self.assertTrue(restored['success'], restored)
            self.assertEqual(client.revision, before + 1)
            self.assertEqual(client.session_id, session)
            self.assertEqual(restored['deleted_ids'], [created])
            self.assertEqual(client.call('scene.inspect_objects', {'object_ids': [oid]})['result'], baseline)
            self.assertEqual(client.call('mesh.inspect_selection', {'selection_handle': handle})
                             ['error']['code'], 'INVALID_SELECTION_HANDLE')
            self.assertEqual(client.call('object.transform', {'object_id': oid, 'location': [0, 0, 0]},
                expected_revision=before)['error']['code'], 'STALE_SCENE_STATE')
            started = client.call('transaction.begin')
            args = {'transaction_id': started['result']['transaction_id']}
            self.assertTrue(client.call('object.transform', {'object_id': oid, 'location': [2, 0, 0]})['success'])
            committed = client.call('transaction.commit', args)
            self.assertTrue(committed['success'], committed)
            self.assertEqual(committed['modified_ids'], [oid])
            self.assertEqual(client.call('transaction.rollback', args)['error']['code'], 'NO_ACTIVE_TRANSACTION')
            current = client.call('scene.inspect_objects', {'object_ids': [oid]})['result']['objects'][0]
            self.assertEqual(current['world_origin'], [2.0, 0.0, 0.0])
            # Shutdown with an active transaction releases its private snapshot.
            self.assertTrue(client.call('transaction.begin')['success'])

    def test_real_recovery(self):
        script = Path(__file__).resolve().parents[1] / 'blender' / 'recovery_smoke.py'
        result = run_headless(script, executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_RECOVERY_HEADLESS_OK', result.stdout)


    def test_forced_death_cleans_active_snapshot(self):
        with BlenderClient(executable=BLENDER) as client:
            self.assertTrue(client.call('transaction.begin')['success'])
            directory = Path(client._directory.name)
            self.assertEqual(len(list(directory.glob('bar-recovery-*/checkpoint.blend'))), 1)
            client.process.kill()
            client.process.wait(timeout=10)
            with self.assertRaises(BlenderProcessError):
                client.call('runtime.get_version')
            client.close()
            self.assertFalse(directory.exists())
