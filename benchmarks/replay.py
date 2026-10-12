"""Deterministic agent-protocol replay, explicitly not an autonomous model run.

Exercise every expansion recipe through the JSON-line bridge in a fresh process.
The bridge owns checkpoint/evaluation/rendering; this client only submits public
calls and role UUIDs. Useful for transport regression and as an agent example.
"""
import argparse
import json
from pathlib import Path
import subprocess
import queue
import threading
import sys
import tempfile

from benchmarks.catalog import CATALOG
from benchmarks.expansion import build_recipe, write_json
from benchmarks.stool import Exercise


class BridgeClient:
    def __init__(self, process):
        self.process = process
        self.messages = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.ready = self.receive()
        if not self.ready.get('ready'):
            raise RuntimeError('Bridge did not become ready')

    def _read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(line)
        finally:
            self.messages.put(None)

    def receive(self):
        try:
            line = self.messages.get(timeout=180)
        except queue.Empty:
            raise TimeoutError('Bridge response deadline exceeded') from None
        if not line:
            raise RuntimeError('Bridge exited without a response')
        return json.loads(line)

    def submit(self, value):
        self.process.stdin.write(json.dumps(value)+'\n')
        self.process.stdin.flush()
        return self.receive()

    def call(self, tool, arguments):
        response = self.submit({'tool': tool, 'arguments': arguments})
        if 'bridge_error' in response:
            raise RuntimeError(response['bridge_error'])
        return response


def run_replay(brief, output, *, executable='blender', engine='WORKBENCH'):
    # Logs cannot fill a pipe while the caller waits on stdout.
    with tempfile.TemporaryFile(mode='w+t') as errors:
        process = subprocess.Popen(
            [sys.executable, '-m', 'benchmarks.agent', '--benchmark', brief.name,
             '--agent', 'deterministic recipe replay (no model)', '--max-calls', '500',
             '--blender', executable, '--engine', engine, '--output', str(output)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
            text=True, cwd=Path(__file__).resolve().parents[1])
        try:
            client = BridgeClient(process)
            roles = build_recipe(Exercise(client), brief)
            report = client.submit({'finish': roles})
            if 'bridge_error' in report:
                raise RuntimeError(report['bridge_error'])
            process.stdin.close()
            if process.wait(timeout=30) != 0:
                errors.seek(0)
                raise RuntimeError(errors.read())
            # Preserve the harness report and record provenance in a separate file.
            write_json(output / 'replay.json', {'mode': 'protocol_replay',
                       'autonomous_agent_run': False, 'benchmark': brief.name,
                       'uses_manual_recipe': True})
            return report
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if not process.stdin.closed:
                process.stdin.close()
            process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--benchmark', choices=tuple(CATALOG))
    parser.add_argument('--engine', choices=('WORKBENCH', 'EEVEE'), default='WORKBENCH')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('--output must be empty')
    entries = []
    briefs = [CATALOG[args.benchmark]] if args.benchmark else list(CATALOG.values())
    for brief in briefs:
        try:
            report = run_replay(brief, args.output / brief.name,
                                executable=args.blender, engine=args.engine)
            entries.append({'benchmark': brief.name, 'status': 'passed' if
                            report['reports']['supported_technical_passed'] else 'failed',
                            'metrics': report['metrics']})
        except Exception as exc:
            entries.append({'benchmark': brief.name, 'status': 'error',
                            'error_type': type(exc).__name__, 'message': str(exc)})
        write_json(args.output / 'summary.json', {'mode': 'protocol_replay',
                   'autonomous_agent_run': False, 'benchmarks': entries,
                   'expected_benchmarks': len(briefs), 'complete': len(entries) == len(briefs),
                   'passed': len(entries) == len(briefs) and all(e['status'] == 'passed' for e in entries)})
        print(f"{brief.name}: {entries[-1]['status']}", flush=True)
    return 0 if all(e['status'] == 'passed' for e in entries) else 1


if __name__ == '__main__':
    raise SystemExit(main())
