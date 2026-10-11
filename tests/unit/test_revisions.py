import io
import unittest
from concurrent.futures import ThreadPoolExecutor

from runtime.api import RuntimeAPI
from runtime.capability_registry import ToolSpec
from runtime.errors import ToolError
from runtime.logging import EventLogger
from runtime.schemas import validate_response


class StateTests(unittest.TestCase):
    def setUp(self):
        self.api = RuntimeAPI(blender_version='fixture', logger=EventLogger(io.StringIO()))
        self.contents = []
        self.api.registry.register(ToolSpec('test.edit', 'Mutation fixture',
                                           side_effects=('scene',)),
                                   lambda args: self.edit())

    def edit(self):
        self.contents.append('object')
        return {}

    def call(self, tool='test.edit', **fields):
        message = {'api_version': '1.0', 'session_id': self.api.state.session_id,
                   'expected_revision': self.api.state.revision, 'tool': tool, 'arguments': {}}
        message.update(fields)
        response = self.api.execute(message)
        validate_response(response)
        return response

    def test_new_instances_have_distinct_sessions(self):
        other = RuntimeAPI(blender_version='fixture', logger=EventLogger(io.StringIO()))
        self.assertNotEqual(self.api.state.session_id, other.state.session_id)
        self.assertEqual(other.state.revision, 0)
        result = self.call(session_id=other.state.session_id)
        self.assertEqual(result['error']['code'], 'SESSION_MISMATCH')
        self.assertEqual(result['session_id'], self.api.state.session_id)
        self.assertEqual(self.contents, [])

    def test_revisions_guard_mutations_and_reads(self):
        first = self.call()
        self.assertEqual((first['revision_before'], first['revision_after']), (0, 1))
        for revision in (0, 2):
            for tool in ('test.edit', 'runtime.get_version'):
                response = self.call(tool, expected_revision=revision)
                self.assertEqual(response['error']['code'], 'STALE_SCENE_STATE')
                self.assertEqual(response['revision'], 1)
        self.assertEqual(self.contents, ['object'])
        read = self.call('runtime.get_version')
        self.assertEqual((read['revision_before'], read['revision_after']), (1, 1))
        self.assertEqual(self.call()['revision_after'], 2)

    def test_invalid_state_fields_do_not_execute(self):
        for field, values in (('session_id', ('', None, 42)),
                              ('expected_revision', (-1, True, 0.0, '0', None))):
            for value in values:
                self.assertEqual(self.call(**{field: value})['error']['code'], 'INVALID_REQUEST')
        for field in ('session_id', 'expected_revision'):
            message = {'api_version': '1.0', 'session_id': self.api.state.session_id,
                       'expected_revision': 0, 'tool': 'test.edit', 'arguments': {}}
            del message[field]
            response = self.api.execute(message)
            validate_response(response)
            self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
        self.assertEqual(self.contents, [])
        self.assertEqual(self.api.state.revision, 0)

    def test_failed_mutations_advance_but_preflight_errors_do_not(self):
        def partial(args):
            self.contents.append('partial')
            raise ToolError('FIXTURE_FAILURE', 'Mutation failed.')
        self.api.registry.register(ToolSpec('test.partial', 'Failure fixture',
                                           side_effects=('scene',)), partial)
        self.assertEqual(self.call(arguments={'unexpected': 'x'})['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.call('unknown')['error']['code'], 'UNKNOWN_TOOL')
        self.assertEqual(self.api.state.revision, 0)
        failure = self.call('test.partial')
        self.assertEqual(failure['revision'], 1)
        self.assertEqual(self.contents, ['partial'])
        self.assertEqual(self.call(expected_revision=0)['error']['code'], 'STALE_SCENE_STATE')
        self.api.registry.register(ToolSpec('test.bad', 'Bad result fixture',
                                           side_effects=('scene',)), lambda args: {'value': object()})
        self.assertEqual(self.call('test.bad')['revision'], 2)

    def test_restoring_contents_never_restores_timeline(self):
        self.call()
        self.call()
        self.api.registry.register(ToolSpec('test.rollback', 'Restore fixture',
                                           side_effects=('scene',)),
                                   lambda args: (self.contents.clear() or {}))
        restored = self.call('test.rollback')
        self.assertEqual(self.contents, [])
        self.assertEqual((restored['revision_before'], restored['revision_after']), (2, 3))
        self.assertEqual(self.call(expected_revision=0)['error']['code'], 'STALE_SCENE_STATE')

    def test_concurrent_calls_with_same_revision_only_execute_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.call(expected_revision=0), range(12)))
        self.assertEqual(sum(result['success'] for result in results), 1)
        self.assertEqual(self.contents, ['object'])
        self.assertEqual(self.api.state.revision, 1)
