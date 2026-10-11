import copy
import io
import unittest
from unittest.mock import patch

from runtime.api import RuntimeAPI
from runtime.errors import ToolError
from runtime.logging import EventLogger
from runtime.recovery import RecoveryService, scene_diff
from runtime.schemas import validate_response


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.api = RuntimeAPI(blender_version='test', logger=EventLogger(io.StringIO()))
        self.rows = {'one': {'vertices': 8, 'faces': 6, 'transform': [0, 0, 0]}}
        self.saved = None
        self.fail_save = self.fail_load = False
        self.service = RecoveryService(observer=None, identities=None, state=self.api.state,
            capture=lambda: copy.deepcopy(self.rows), save=self.save, load=self.load)
        self.service.register(self.api.registry)
        self.addCleanup(self.service.close)

    def save(self, path):
        if self.fail_save:
            raise ToolError('SNAPSHOT_FAILED', 'fixture')
        self.saved = copy.deepcopy(self.rows)
        path.write_bytes(b'checkpoint fixture')
        return '/original.blend'

    def load(self, checkpoint):
        if self.fail_load:
            raise ToolError('ROLLBACK_FAILED', 'fixture')
        self.rows = copy.deepcopy(self.saved)

    def call(self, tool, arguments=None, **state):
        response = self.api.execute({'api_version': '1.0', 'session_id': self.api.state.session_id,
            'expected_revision': self.api.state.revision, 'tool': tool, 'arguments': arguments or {}, **state})
        validate_response(response)
        return response

    def begin(self):
        response = self.call('transaction.begin')
        self.assertTrue(response['success'], response)
        return {'transaction_id': response['result']['transaction_id']}

    def test_numeric_diff_is_sorted_and_detects_same_count_changes(self):
        diff = scene_diff({'a': {'faces': 6}, 'b': {'vertices': 8}},
                          {'b': {'vertices': 8, 'shape': 'changed'}, 'c': {'faces': 1}})
        self.assertEqual(diff['created_ids'], ['c'])
        self.assertEqual(diff['deleted_ids'], ['a'])
        self.assertEqual(diff['modified_ids'], ['b'])
        self.assertEqual(diff['changes'][1]['fields'], ['shape'])
        self.assertEqual(scene_diff({}, {})['changes'], [])

    def test_diff_commit_and_cleanup(self):
        args = self.begin()
        path = self.service.active.path
        self.rows['two'] = {'vertices': 1}
        diff = self.call('scene.diff', args)
        self.assertEqual(diff['result']['diff']['created_ids'], ['two'])
        self.assertEqual((diff['revision_before'], diff['revision_after']), (1, 1))
        committed = self.call('transaction.commit', args)
        self.assertEqual(committed['created_ids'], ['two'])
        self.assertEqual(committed['revision_after'], 2)
        self.assertFalse(path.parent.exists())
        self.assertIn('two', self.rows)
        self.assertEqual(self.call('scene.diff', args)['error']['code'], 'NO_ACTIVE_TRANSACTION')

    def test_rollback_restores_contents_and_never_revision(self):
        args = self.begin()
        self.rows = {'two': {'faces': 1}}
        self.api.state.advance()
        restored = self.call('transaction.rollback', args)
        self.assertEqual(restored['created_ids'], ['one'])
        self.assertEqual(restored['deleted_ids'], ['two'])
        self.assertEqual(restored['revision_after'], 3)
        self.assertEqual(self.rows, self.saved)
        self.assertIsNone(self.service.active)

    def test_nested_wrong_expired_and_stale_requests(self):
        args = self.begin()
        self.assertEqual(self.call('transaction.begin')['error']['code'], 'TRANSACTION_ACTIVE')
        self.assertEqual(self.api.state.revision, 2)
        self.assertEqual(self.call('transaction.rollback', {'transaction_id': 'other'})['error']['code'], 'INVALID_TRANSACTION')
        self.assertEqual(self.api.state.revision, 3)
        self.assertEqual(self.call('transaction.rollback', args, expected_revision=0)['error']['code'], 'STALE_SCENE_STATE')
        self.assertEqual(self.api.state.revision, 3)
        self.assertEqual(self.call('transaction.rollback', {})['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.api.state.revision, 3)
        self.assertTrue(self.call('transaction.rollback', args)['success'])
        self.assertEqual(self.call('transaction.commit', args)['error']['code'], 'NO_ACTIVE_TRANSACTION')

    def test_save_and_load_failure_keep_lifecycle_recoverable(self):
        self.fail_save = True
        self.assertEqual(self.call('transaction.begin')['error']['code'], 'SNAPSHOT_FAILED')
        self.assertIsNone(self.service.active)
        self.fail_save = False
        args = self.begin()
        self.fail_load = True
        self.assertEqual(self.call('transaction.rollback', args)['error']['code'], 'ROLLBACK_FAILED')
        self.assertTrue(self.service.active.path.exists())
        self.fail_load = False
        self.assertTrue(self.call('transaction.rollback', args)['success'])

    def test_corruption_rejects_before_load_and_retains_checkpoint(self):
        args = self.begin()
        path = self.service.active.path
        original = path.read_bytes()
        self.rows.clear()
        path.write_bytes(b'corrupt')
        self.assertEqual(self.call('transaction.rollback', args)['error']['code'], 'SNAPSHOT_UNAVAILABLE')
        self.assertEqual(self.rows, {})
        path.write_bytes(original)
        self.assertTrue(self.call('transaction.rollback', args)['success'])

    def test_bad_current_identity_can_still_rollback(self):
        args = self.begin()
        def fail():
            raise ToolError('UUID_COLLISION', 'fixture')
        self.service.capture = fail
        self.assertEqual(self.call('transaction.commit', args)['error']['code'], 'UUID_COLLISION')
        self.assertIsNotNone(self.service.active)
        result = self.call('transaction.rollback', args)
        self.assertTrue(result['success'])
        self.assertIsNone(result['result']['diff'])
        self.assertEqual(result['result']['diff_error'], 'UUID_COLLISION')

    def test_close_cleans_abandoned_checkpoint_and_backend_is_optional(self):
        self.begin()
        path = self.service.active.path
        self.service.close()
        self.service.close()
        self.assertFalse(path.parent.exists())
        self.assertFalse(self.api.features['transactions'])
        self.assertNotIn('transaction.begin', RuntimeAPI(blender_version='test').registry.names())


    def test_oversized_commit_preserves_checkpoint_and_rollback_still_runs(self):
        args = self.begin()
        self.rows['one']['large'] = 'x' * 2000
        with patch('controller.ipc.MAX_FRAME_BYTES', 5000):
            self.assertEqual(self.call('transaction.commit', args)['error']['code'], 'RESPONSE_TOO_LARGE')
            self.assertIsNotNone(self.service.active)
            restored = self.call('transaction.rollback', args)
            self.assertTrue(restored['success'])
            self.assertEqual(restored['result']['diff_error'], 'RESPONSE_TOO_LARGE')
        self.assertEqual(self.rows, self.saved)
