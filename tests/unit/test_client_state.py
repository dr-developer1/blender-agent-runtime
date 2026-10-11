import unittest
from unittest.mock import Mock

from controller.client import BlenderClient
from controller.lifecycle import BlenderProcessError
from runtime.schemas import success_response, failure_response
from runtime.errors import ToolError


class ClientStateTests(unittest.TestCase):
    def client(self, response):
        client = BlenderClient()
        client.process = Mock()
        client.process.poll.return_value = None
        client._session_id = 'session'
        client._revision = 0
        client._channel = Mock()
        client._channel.receive.side_effect = lambda: {
            'id': client._channel.send.call_args.args[0]['id'], **response}
        client._dispose = Mock()
        return client

    def test_tracks_success_and_rejection_without_retry(self):
        response = success_response({}, 0, 'session', 0, 1)
        client = self.client(response)
        self.assertTrue(client.call('fixture')['success'])
        self.assertEqual(client.revision, 1)
        self.assertEqual(client._channel.send.call_args.args[0]['expected_revision'], 0)
        response.clear()
        response.update(failure_response(ToolError('STALE_SCENE_STATE', 'Stale.'), 'session', 3))
        self.assertFalse(client.call('fixture', expected_revision=0)['success'])
        self.assertEqual(client.revision, 3)
        self.assertEqual(client._channel.send.call_count, 2)
        client._dispose.assert_not_called()

    def test_corrupt_state_responses_poison_connection(self):
        for response, observed in ((success_response({}, 0, 'other', 0, 1), 0),
                                   (success_response({}, 0, 'session', 0, 0), 1),
                                   (success_response({}, 0, 'session', 1, 2), 0),
                                   (failure_response(ToolError('X', 'x'), 'session', 0), 1)):
            with self.subTest(response=response):
                client = self.client(response)
                client._revision = observed
                with self.assertRaises(BlenderProcessError):
                    client.call('fixture')
                client._dispose.assert_called_once()
