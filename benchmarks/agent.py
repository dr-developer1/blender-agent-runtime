"""JSON-line bridge for one external AI agent driving the stool exercise.

Run locally and send {"tool": ..., "arguments": {...}} lines, then
{"finish": {"seat": "UUID", "legs": ["UUID", ...]}}. No model credentials
or provider SDK are required by the bridge.
"""
import argparse
import base64
import json
from dataclasses import asdict
from pathlib import Path
import sys

from benchmarks.stool import Exercise, PROMPT, ToolRejected, evaluate
from controller.client import BlenderClient
from benchmarks.catalog import CATALOG
from benchmarks.expansion import evaluate as evaluate_expansion, object_ids, metrics


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--agent', required=True, help='Evaluator-visible agent identity')
    parser.add_argument('--benchmark', choices=('stool', *CATALOG), default='stool')
    parser.add_argument('--engine', choices=('WORKBENCH', 'EEVEE'), default='WORKBENCH')
    parser.add_argument('--max-calls', type=int, default=100)
    args = parser.parse_args()
    brief = CATALOG.get(args.benchmark)
    if not 1 <= args.max_calls <= 500:
        parser.error('--max-calls must be between 1 and 500')
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('--output must be an empty directory')
    with BlenderClient(executable=args.blender, request_timeout=180) as client:
        e = Exercise(client)
        transaction = e.call('transaction.begin')
        control = {'transaction_id': transaction['transaction_id']}
        active = True
        submitted = []
        try:
            names = e.call('runtime.list_tools')['tools']
            # The harness owns checkpoint lifetime; the agent owns scene edits.
            allowed = [name for name in names if not name.startswith('transaction.') and name != 'scene.diff']
            emit({'ready': True, 'prompt': brief.prompt if brief else PROMPT, 'tools': allowed,
                  'benchmark': args.benchmark,
                  'brief': asdict(brief) if brief else None,
                  'tolerance_mm': 2,
                  'roles': [p.role for p in brief.parts] if brief else ['seat', 'legs'],
                  'agent': args.agent, 'session_id': client.session_id,
                  'instructions': 'Discover schemas with runtime.describe_tool. Finish with the advertised role UUIDs (stool legs is a list of four). Delete the initial scene objects. Harness evaluates, renders and commits supported technical criteria; otherwise rolls back.'})
            for _ in range(args.max_calls):
                line = sys.stdin.readline(1024 * 1024 + 1)
                if not line:
                    break
                if len(line.encode('utf-8')) > 1024 * 1024:
                    raise ValueError('Input line exceeds bridge budget')
                command = json.loads(line)
                submitted.append(command)
                if not isinstance(command, dict):
                    raise ValueError('Command must be an object')
                if set(command) == {'finish'}:
                    roles = command['finish']
                    try:
                        if brief:
                            ids = object_ids(brief, roles)
                            reports = evaluate_expansion(e, brief, roles)
                        else:
                            reports = evaluate(e, roles)
                            ids = [roles['seat'], *roles['legs']]
                    except (ValueError, KeyError, TypeError, ToolRejected) as exc:
                        emit({'bridge_error': str(exc)})
                        continue
                    images = e.call('observe.render_multiview', {
                        'object_ids': ids, 'engine': args.engine})
                    for image in images['images']:
                        (args.output / (image['camera']['view'] + '.png')).write_bytes(
                            base64.b64decode(image['png_base64'], validate=True))
                    action = 'transaction.commit' if reports['supported_technical_passed'] else 'transaction.rollback'
                    e.call(action, control)
                    active = False
                    report = {'benchmark': f'{args.benchmark}-v{brief.version if brief else 1}', 'mode': 'agent', 'agent': args.agent,
                              'prompt': brief.prompt if brief else PROMPT, 'roles': roles, 'reports': reports,
                              'engine': args.engine, 'metrics': metrics(e.trace),
                              'outcome': action, 'session_id': client.session_id,
                              'final_revision': client.revision}
                    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
                    emit(report)
                    return
                if (set(command) != {'tool', 'arguments'} or
                        not isinstance(command['tool'], str) or command['tool'] not in allowed):
                    emit({'bridge_error': 'Use an advertised tool and arguments, or finish with role UUIDs.'})
                    continue
                try:
                    e.call(command['tool'], command['arguments'])
                except ToolRejected:
                    # Structured API failures remain observations the agent can repair.
                    pass
                emit(e.trace[-1]['response'])
            emit({'bridge_error': 'Agent disconnected or exhausted its call budget; rolling back.'})
        finally:
            try:
                if active:
                    e.call('transaction.rollback', control)
            finally:
                (args.output / 'trace.json').write_text(json.dumps(e.trace, indent=2) + '\n')
                (args.output / 'agent_commands.json').write_text(json.dumps(submitted, indent=2) + '\n')


if __name__ == '__main__':
    main()
