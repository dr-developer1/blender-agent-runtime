import json
import os
import shutil
import unittest

from controller.client import BlenderClient

BLENDER = os.environ.get('BLENDER_EXECUTABLE', 'blender')


@unittest.skipUnless(shutil.which(BLENDER), 'Blender executable unavailable')
class ApiIntegrationTests(unittest.TestCase):
    def test_public_discovery_contract_and_recovery(self):
        with BlenderClient(executable=BLENDER) as client:
            version = client.call('runtime.get_version')
            self.assertTrue(version['success'])
            self.assertEqual(version['api_version'], '1.0')
            self.assertTrue(version['result']['blender_version'])
            names = client.call('runtime.list_tools')['result']['tools']
            for name in names:
                self.assertTrue(client.call('runtime.describe_tool', {'name': name})['success'])
            self.assertEqual(client.call('runtime.list_tools', api_version='9.0')['error']['code'],
                             'UNSUPPORTED_API_VERSION')
            self.assertEqual(client.call('mesh.bevel')['error']['code'], 'UNKNOWN_TOOL')
            self.assertEqual(client.call('runtime.describe_tool', {'name': False})['error']['code'],
                             'INVALID_ARGUMENT')
            self.assertTrue(client.call('runtime.get_limits')['success'])
            self.assertTrue(client.request('process.ping')['success'])
        events = [json.loads(line) for line in client.log_output.splitlines() if line.startswith('{')]
        self.assertTrue(events)
        self.assertEqual(sum(not event['success'] for event in events), 3)
        self.assertTrue(all(event['event'] == 'tool_call' for event in events))
