"""Structured call metadata without payloads or credentials."""
import json
import sys


class EventLogger:
    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr

    def tool_call(self, *, request_id, tool, api_version, success, error_code, duration_ms):
        event = {'event': 'tool_call', 'request_id': request_id, 'tool': tool,
                 'api_version': api_version, 'success': success,
                 'error_code': error_code, 'duration_ms': duration_ms}
        print(json.dumps(event, allow_nan=False, separators=(',', ':')), file=self.stream, flush=True)
