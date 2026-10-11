import os
from pathlib import Path
import shutil
import signal
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

from controller.client import BlenderClient
from controller.lifecycle import BlenderProcessError, run_headless

BLENDER = os.environ.get('BLENDER_EXECUTABLE', 'blender')


@unittest.skipUnless(shutil.which(BLENDER), 'Blender executable unavailable')
class ProcessTests(unittest.TestCase):
    def start_client(self):
        client = BlenderClient(executable=BLENDER)
        client.start()
        self.addCleanup(client.close)
        return client

    def test_persistent_serial_main_thread_execution(self):
        client = self.start_client()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: client.request('process.ping'), range(12)))
        self.assertTrue(all(r['success'] for r in results))
        self.assertEqual({r['result']['pid'] for r in results}, {client.pid})
        self.assertTrue(all(r['result']['main_thread'] for r in results))
        self.assertEqual(sorted(r['result']['sequence'] for r in results), list(range(1, 13)))

    def test_structured_errors_and_recovery(self):
        client = self.start_client()
        bad = client.request('unknown')
        self.assertFalse(bad['success'])
        self.assertEqual(bad['error']['code'], 'UNKNOWN_COMMAND')
        bad = client.request('process.ping', {'unexpected': True})
        self.assertEqual(bad['error']['code'], 'INVALID_ARGUMENT')
        self.assertTrue(client.request('process.ping')['success'])

    def test_clean_shutdown(self):
        client = self.start_client()
        pid = client.pid
        client.close()
        self.assertIsNotNone(pid)
        self.assertEqual(client.returncode, 0)
        client.close()
        with self.assertRaises(BlenderProcessError):
            client.request('process.ping')

    def test_invalid_request_and_recovery(self):
        client = self.start_client()
        client._channel.send({'id': 'malformed', 'command': 'process.ping'})
        response = client._channel.receive()
        self.assertEqual(response['id'], 'malformed')
        self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
        self.assertTrue(client.request('process.ping')['success'])

    def test_crash_detection(self):
        client = self.start_client()
        client.process.kill()
        client.process.wait(timeout=10)
        with self.assertRaises(BlenderProcessError):
            client.request('process.ping')

    def test_headless_runner_success_and_failure(self):
        fixtures = Path(__file__).parents[1] / 'blender'
        result = run_headless(fixtures / 'smoke.py', executable=BLENDER)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('BAR_HEADLESS_OK', result.stdout)
        failed = run_headless(fixtures / 'failure.py', executable=BLENDER)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('intentional runner failure', failed.stdout)

    def test_missing_executable(self):
        client = BlenderClient(executable='/nonexistent/bar-blender')
        with self.assertRaises(BlenderProcessError):
            client.start()
        client.close()

    @unittest.skipUnless(hasattr(signal, 'SIGSTOP'), 'Requires POSIX process suspension')
    def test_request_timeout_terminates_child(self):
        client = self.start_client()
        client.request_timeout = 0.1
        client._sock.settimeout(client.request_timeout)
        os.kill(client.pid, signal.SIGSTOP)
        with self.assertRaises(BlenderProcessError):
            client.request('process.ping')
        self.assertIsNotNone(client.returncode)
        with self.assertRaises(BlenderProcessError):
            client.request('process.ping')

    def test_early_process_exit(self):
        client = BlenderClient(executable=sys.executable)
        with self.assertRaises(BlenderProcessError):
            client.start()
        self.assertIsNotNone(client.returncode)
        self.assertIn('background', client.log_output)

    def test_headless_runner_timeout(self):
        fixture = Path(__file__).parents[1] / 'blender' / 'hang.py'
        with self.assertRaises(BlenderProcessError):
            run_headless(fixture, executable=BLENDER, timeout=0.2)
