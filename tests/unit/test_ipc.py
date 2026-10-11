import socket
import unittest

from controller.ipc import JsonChannel, ProtocolError


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = socket.socketpair()
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)
        self.channel = JsonChannel(self.a, max_bytes=128)

    def test_roundtrip(self):
        JsonChannel(self.b).send({'id': 'one', 'text': 'café'})
        self.assertEqual(self.channel.receive(), {'id': 'one', 'text': 'café'})

    def test_coalesced_frames(self):
        self.b.sendall(b'{"id":1}\n{"id":2}\n')
        self.assertEqual(self.channel.receive()['id'], 1)
        self.assertEqual(self.channel.receive()['id'], 2)

    def test_invalid_frames(self):
        for payload in (b'[]\n', b'NaN\n', b'{broken}\n', b'{"x":NaN}\n'):
            with self.subTest(payload=payload):
                self.b.sendall(payload)
                with self.assertRaises(ProtocolError):
                    self.channel.receive()

    def test_oversized_frame(self):
        self.b.sendall(b'x' * 129)
        with self.assertRaises(ProtocolError):
            self.channel.receive()

    def test_disconnect(self):
        self.b.close()
        with self.assertRaises(EOFError):
            self.channel.receive()
