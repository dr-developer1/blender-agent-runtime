"""A serialized synchronous client owning one headless Blender process."""
import hmac
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import uuid

from .ipc import JsonChannel, ProtocolError
from .lifecycle import BlenderProcessError, blender_command, isolated_environment


class BlenderClient:
    def __init__(self, *, executable='blender', startup_timeout=30, request_timeout=10,
                 shutdown_timeout=10):
        if min(startup_timeout, request_timeout, shutdown_timeout) <= 0:
            raise ValueError('Timeouts must be positive')
        self.executable = executable
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self.shutdown_timeout = shutdown_timeout
        self.process = None
        self._sock = None
        self._channel = None
        self._directory = None
        self._log = None
        self._lock = threading.RLock()
        self._closed = False
        self.log_output = ''

    @property
    def pid(self):
        return self.process.pid if self.process else None

    @property
    def returncode(self):
        return self.process.poll() if self.process else None

    def start(self):
        with self._lock:
            if self._closed or self.process is not None:
                raise BlenderProcessError('Client is single-use; create a new client to restart')
            self._directory = tempfile.TemporaryDirectory(prefix='bar-runtime-')
            self._log = tempfile.TemporaryFile(mode='w+b')
            token = secrets.token_hex(32)
            deadline = time.monotonic() + self.startup_timeout
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                    listener.bind(('127.0.0.1', 0))
                    listener.listen(1)
                    env = isolated_environment(self._directory.name)
                    env.update(BAR_IPC_PORT=str(listener.getsockname()[1]), BAR_IPC_TOKEN=token)
                    server = Path(__file__).resolve().parents[1] / 'runtime' / 'server.py'
                    self.process = subprocess.Popen(
                        blender_command(self.executable, server), env=env,
                        cwd=self._directory.name, stdin=subprocess.DEVNULL,
                        stdout=self._log, stderr=subprocess.STDOUT)
                    while True:
                        if self.process.poll() is not None:
                            raise BlenderProcessError('Blender exited before IPC startup')
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise BlenderProcessError('Blender IPC startup timed out')
                        listener.settimeout(min(remaining, 0.1))
                        try:
                            self._sock, _ = listener.accept()
                            break
                        except socket.timeout:
                            continue
                    self._sock.settimeout(max(0.001, deadline - time.monotonic()))
                    self._channel = JsonChannel(self._sock)
                    ready = self._channel.receive()
                    if (ready.get('type') != 'ready' or ready.get('pid') != self.pid or
                            not isinstance(ready.get('token'), str) or
                            not hmac.compare_digest(ready['token'], token)):
                        raise ProtocolError('Invalid Blender startup handshake')
                    self._sock.settimeout(self.request_timeout)
            except (OSError, EOFError, ProtocolError, BlenderProcessError) as exc:
                self._dispose()
                raise BlenderProcessError(f'{exc}\n{self.log_output[-4000:]}') from exc
            return self

    def request(self, command, arguments=None):
        with self._lock:
            if (self._closed or self.process is None or self._channel is None or
                    self.process.poll() is not None):
                raise BlenderProcessError(f'Blender is not running (exit code {self.returncode})')
            if command == 'process.shutdown':
                raise ValueError('Use close() for shutdown')
            return self._exchange(command, {} if arguments is None else arguments)

    def _exchange(self, command, arguments):
        request_id = str(uuid.uuid4())
        message = {'id': request_id, 'command': command, 'arguments': arguments}
        try:
            self._channel.send(message)
            response = self._channel.receive()
            if (response.get('id') != request_id or type(response.get('success')) is not bool or
                    not isinstance(response.get('result' if response['success'] else 'error'), dict)):
                raise ProtocolError('Invalid or uncorrelated response')
            return response
        except (OSError, EOFError, ProtocolError) as exc:
            self._dispose()
            raise BlenderProcessError(f'Blender IPC failed: {exc}\n{self.log_output[-4000:]}') from exc

    def close(self):
        with self._lock:
            if self._closed:
                return
            failure = None
            if self.process is not None and self.process.poll() is None and self._channel:
                try:
                    self._sock.settimeout(self.shutdown_timeout)
                    response = self._exchange('process.shutdown', {})
                    if not response['success']:
                        raise BlenderProcessError('Blender rejected shutdown')
                    self.process.wait(timeout=self.shutdown_timeout)
                    if self.process.returncode != 0:
                        raise BlenderProcessError(f'Blender exited with {self.process.returncode}')
                except (BlenderProcessError, subprocess.TimeoutExpired, OSError) as exc:
                    failure = exc
            self._dispose()
            if failure:
                raise BlenderProcessError(f'Clean shutdown failed: {failure}') from failure

    def _dispose(self):
        self._closed = True
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self._channel = None
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self._log is not None:
            self._log.seek(0)
            self.log_output = self._log.read().decode('utf-8', errors='replace')
            self._log.close()
            self._log = None
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.close()
        else:
            with self._lock:
                self._dispose()
