"""Background Blender entrypoint: all bpy access stays on the main thread."""
import os
from pathlib import Path
import socket
import sys
import threading

# Blender executes this file as a script, outside an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.ipc import JsonChannel


def serve():
    import bpy

    assert threading.current_thread() is threading.main_thread()
    with socket.create_connection(('127.0.0.1', int(os.environ['BAR_IPC_PORT'])), timeout=10) as sock:
        channel = JsonChannel(sock)
        channel.send({'type': 'ready', 'token': os.environ.pop('BAR_IPC_TOKEN'), 'pid': os.getpid()})
        sock.settimeout(None)
        sequence = 0
        while True:
            try:
                request = channel.receive()
            except EOFError:
                return
            request_id = request.get('id')
            command = request.get('command')
            arguments = request.get('arguments')
            error = None
            if (not isinstance(request_id, str) or not request_id or
                    not isinstance(command, str) or not isinstance(arguments, dict) or
                    set(request) != {'id', 'command', 'arguments'}):
                error = ('INVALID_REQUEST', 'Expected id, command and arguments.')
            elif command not in ('process.ping', 'process.shutdown'):
                error = ('UNKNOWN_COMMAND', f'Unknown command: {command}')
            elif arguments:
                error = ('INVALID_ARGUMENT', 'This command accepts no arguments.')
            if error:
                channel.send({'id': request_id, 'success': False,
                              'error': {'code': error[0], 'message': error[1], 'details': {}}})
                continue
            sequence += 1
            result = {'pid': os.getpid(), 'sequence': sequence,
                      'main_thread': threading.current_thread() is threading.main_thread(),
                      'blender_version': bpy.app.version_string}
            channel.send({'id': request_id, 'success': True, 'result': result})
            if command == 'process.shutdown':
                return


if __name__ == '__main__':
    serve()
