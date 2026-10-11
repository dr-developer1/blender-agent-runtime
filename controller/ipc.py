"""Private bounded JSON-lines transport for the process foundation."""
import json

MAX_FRAME_BYTES = 1024 * 1024


class ProtocolError(ValueError):
    pass


def _reject_constant(value):
    raise ProtocolError(f'Non-finite JSON value: {value}')


class JsonChannel:
    def __init__(self, sock, max_bytes=MAX_FRAME_BYTES):
        self.sock = sock
        self.max_bytes = max_bytes
        self.buffer = bytearray()

    def send(self, message):
        if not isinstance(message, dict):
            raise ProtocolError('Frame must be a JSON object')
        try:
            payload = json.dumps(message, allow_nan=False, separators=(',', ':')).encode('utf-8')
        except (TypeError, ValueError) as exc:
            raise ProtocolError(str(exc)) from exc
        if len(payload) > self.max_bytes:
            raise ProtocolError('Frame exceeds byte limit')
        self.sock.sendall(payload + b'\n')

    def receive(self):
        while True:
            end = self.buffer.find(b'\n')
            if end >= 0:
                if end > self.max_bytes:
                    raise ProtocolError('Frame exceeds byte limit')
                payload = bytes(self.buffer[:end])
                del self.buffer[:end + 1]
                try:
                    message = json.loads(payload, parse_constant=_reject_constant)
                except (ValueError, UnicodeError) as exc:
                    raise ProtocolError(f'Invalid JSON frame: {exc}') from exc
                if not isinstance(message, dict):
                    raise ProtocolError('Frame must be a JSON object')
                return message
            if len(self.buffer) > self.max_bytes:
                raise ProtocolError('Frame exceeds byte limit')
            chunk = self.sock.recv(min(65536, self.max_bytes + 1 - len(self.buffer)))
            if not chunk:
                raise EOFError('IPC peer disconnected')
            self.buffer.extend(chunk)
