import io
import json
import unittest

from runtime.api import RuntimeAPI
from runtime.capability_registry import CapabilityRegistry, ToolSpec
from runtime.schemas import validate_response
from runtime.logging import EventLogger


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.logs = io.StringIO()
        self.api = RuntimeAPI(blender_version='test-blender', logger=EventLogger(self.logs))

    def call(self, tool, arguments=None, **extra):
        message = {'api_version': '1.0', 'tool': tool, 'arguments': arguments or {}}
        message.update(extra)
        return self.api.execute(message, request_id='test-id')

    def test_discovery_describes_every_registered_tool(self):
        tools = self.call('runtime.list_tools')['result']['tools']
        self.assertEqual(len(tools), 7)
        for name in tools:
            result = self.call('runtime.describe_tool', {'name': name})
            self.assertTrue(result['success'])
            self.assertEqual(result['result']['name'], name)
            self.assertEqual(result['result']['input_schema']['type'], 'object')
            self.assertEqual(result['result']['side_effects'], [])
        capabilities = self.call('runtime.describe_capabilities')['result']
        self.assertEqual([tool['name'] for tool in capabilities['tools']], tools)
        self.assertEqual(capabilities['conventions']['up'], '+Z')
        self.assertFalse(capabilities['features']['scene_mutation'])

    def test_version_and_limits(self):
        result = self.call('runtime.get_version')['result']
        self.assertEqual(result['api_version'], '1.0')
        self.assertEqual(result['blender_version'], 'test-blender')
        self.assertEqual(self.call('runtime.get_supported_versions')['result']['versions'], ['1.0'])
        limits = self.call('runtime.get_limits')['result']
        self.assertEqual(limits['max_in_flight_requests'], 1)
        self.assertEqual(limits['max_frame_bytes'], 1024 * 1024)

    def test_rejects_invalid_envelopes_and_versions(self):
        for request in ({}, {'api_version': 1, 'tool': 'x', 'arguments': {}},
                        {'api_version': '1.0', 'tool': '', 'arguments': {}},
                        {'api_version': '1.0', 'tool': 'x', 'arguments': []},
                        {'api_version': '1.0', 'tool': 'x', 'arguments': {}, 'extra': 1}):
            with self.subTest(request=request):
                self.assertEqual(self.api.execute(request)['error']['code'], 'INVALID_REQUEST')
        result = self.call('runtime.list_tools', api_version='2.0')
        self.assertEqual(result['error']['code'], 'UNSUPPORTED_API_VERSION')
        self.assertEqual(result['error']['details']['supported_versions'], ['1.0'])

    def test_unknown_tool_and_argument_validation(self):
        self.assertEqual(self.call('mesh.bevel')['error']['code'], 'UNKNOWN_TOOL')
        self.assertEqual(self.call('runtime.describe_tool', {'name': 'mesh.bevel'})['error']['code'], 'UNKNOWN_TOOL')
        for args in ({}, {'name': 42}, {'name': ''}, {'name': 'x', 'extra': 1}):
            self.assertEqual(self.call('runtime.describe_tool', args)['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.call('runtime.list_tools', {'extra': True})['error']['code'], 'INVALID_ARGUMENT')

    def test_read_only_success_envelope(self):
        result = self.call('runtime.list_tools')
        self.assertEqual(result['api_version'], '1.0')
        for field in ('created_ids', 'modified_ids', 'deleted_ids', 'warnings'):
            self.assertEqual(result[field], [])
        self.assertIsNone(result['validation'])
        self.assertGreaterEqual(result['metrics']['duration_ms'], 0)
        self.assertNotIn('session_id', result)

    def test_logs_omit_payloads_and_secrets(self):
        self.call('runtime.describe_tool', {'name': 'secret-value'})
        event = json.loads(self.logs.getvalue())
        self.assertEqual(event['request_id'], 'test-id')
        self.assertEqual(event['error_code'], 'UNKNOWN_TOOL')
        self.assertNotIn('secret-value', self.logs.getvalue())
        self.assertNotIn('arguments', event)

    def test_internal_error_is_redacted_and_next_call_works(self):
        def fail(arguments):
            raise RuntimeError('secret traceback text')
        self.api.registry.register(ToolSpec('test.fail', 'Failure fixture'), fail)
        result = self.call('test.fail')
        self.assertEqual(result['error']['code'], 'INTERNAL_ERROR')
        self.assertNotIn('secret', json.dumps(result) + self.logs.getvalue())
        self.assertTrue(self.call('runtime.list_tools')['success'])

    def test_registry_rejects_duplicate_and_isolates_descriptors(self):
        registry = CapabilityRegistry()
        registry.register(ToolSpec('test.tool', 'fixture'), lambda args: {})
        with self.assertRaises(ValueError):
            registry.register(ToolSpec('test.tool', 'duplicate'), lambda args: {})
        described = registry.describe('test.tool')
        described['input_schema']['properties']['fake'] = {'type': 'string'}
        self.assertNotIn('fake', registry.describe('test.tool')['input_schema']['properties'])

    def test_response_validation(self):
        good = self.call('runtime.list_tools')
        validate_response(good)
        validate_response(self.call('unknown'))
        for field, bad_value in (('api_version', '9.0'), ('warnings', 'wrong'),
                                 ('created_ids', [3]), ('success', 1),
                                 ('metrics', {'duration_ms': float('nan')})):
            with self.subTest(field=field):
                bad = dict(good)
                bad[field] = bad_value
                with self.assertRaises(ValueError):
                    validate_response(bad)

    def test_non_json_tool_output_is_internal_error(self):
        for value in (float('nan'), object()):
            name = 'test.bad_output.' + type(value).__name__
            self.api.registry.register(ToolSpec(name, 'Bad output fixture'),
                                       lambda args, value=value: {'bad': value})
            self.assertEqual(self.call(name)['error']['code'], 'INTERNAL_ERROR')

    def test_unsupported_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            self.api.registry.register(ToolSpec('test.unsupported', 'Unsupported schema',
                input_schema={'type': 'array'}), lambda args: {})

    def test_convention_results_cannot_mutate_registry(self):
        first = self.call('runtime.describe_capabilities')['result']
        first['conventions']['length_units'].append('feet')
        self.assertEqual(self.call('runtime.describe_capabilities')['result']['conventions']['length_units'],
                         ['mm', 'cm', 'm'])
