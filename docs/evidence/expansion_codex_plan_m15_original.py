"""Codex-authored scripted agent plans, distinct from the manual recipe replay.

The active Codex session chooses construction/duplication, palette and semantic
edge selections. Model reasoning is at script-authoring time, not per API call.
This is a supported scripted-agent exercise, not an autonomous model comparison.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from benchmarks.catalog import CATALOG
from benchmarks.expansion import write_json
from benchmarks.replay import BridgeClient
from benchmarks.stool import Exercise

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path('artifacts/expansion-m15-codex'))
parser.add_argument('--blender', default='blender')
parser.add_argument('--engine', choices=('WORKBENCH', 'EEVEE'), default='WORKBENCH')
cli_args = parser.parse_args()
root = cli_args.output
root.mkdir(parents=True, exist_ok=True)
if any(root.iterdir()):
    raise SystemExit('Output must be empty')
entries = []
for brief in CATALOG.values():
    output = root / brief.name
    with tempfile.TemporaryFile(mode='w+t') as errors:
        process = subprocess.Popen([sys.executable, '-m', 'benchmarks.agent',
            '--benchmark', brief.name, '--agent', 'Codex (scripted public-API plans)',
            '--max-calls', '500', '--blender', cli_args.blender, '--engine', cli_args.engine,
            '--output', str(output)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            bridge = BridgeClient(process)
            e = Exercise(bridge)
            tools = e.call('runtime.list_tools')['tools']
            for name in ('object.duplicate', 'object.transform', 'mesh.bevel', 'mesh.boolean'):
                assert name in tools
                e.call('runtime.describe_tool', {'name': name})
            # Discover and remove the startup scene in a page before editing.
            page = e.call('scene.list_objects', {'limit': 100})
            assert page['next_cursor'] is None
            for obj in page['objects']:
                e.call('object.delete', {'object_id': obj['object_id']})
            roles, cache, materials = {}, {}, {}
            for part in brief.parts:
                if part.material not in materials:
                    palette = {
                        'wood': ([.30, .14, .055, 1], .7, 0),
                        'metal': ([.32, .34, .38, 1], .4, .9),
                        'plastic': ([.025, .085, .12, 1], .55, 0),
                        'ceramic': ([.48, .30, .16, 1], .75, 0),
                        'accent': ([.7, .12, .02, 1], .5, 0)}
                    rgba, roughness, metallic = palette[part.material]
                    materials[part.material] = e.call('material.create', {
                        'name': 'Codex '+part.material, 'base_color': rgba,
                        'roughness': roughness, 'metallic': metallic})['material_id']
                key = (part.dimensions, part.primitive, part.material,
                       part.cavity, part.cavity_offset)
                if key in cache:
                    oid = e.call('object.duplicate', {'object_id': cache[key],
                                                    'name': part.role})['object_id']
                    e.call('object.transform', {'object_id': oid, 'unit': 'mm',
                                                 'location': list(part.location)})
                else:
                    size = max(part.dimensions)
                    args = {'primitive': part.primitive, 'size': size, 'unit': 'mm',
                            'scale': [v/size for v in part.dimensions],
                            'location': list(part.location), 'name': part.role}
                    if part.primitive == 'CYLINDER':
                        args['segments'] = 96
                    oid = e.call('object.create_primitive', args)['object_id']
                    query = e.call('mesh.query', {'object_id': oid, 'element_type': 'EDGE',
                              'selectors': [{'kind': 'dihedral_angle', 'minimum': 45, 'maximum': 135}]})
                    if query['matched_count']:
                        e.call('mesh.bevel', {'selection_handle': query['selection_handle'],
                                             'width': .8, 'unit': 'mm', 'segments': 3})
                    if part.cavity:
                        size = max(part.cavity)
                        cutter_args = {'primitive': 'CYLINDER' if part.cavity[0] == part.cavity[1] else 'CUBE',
                            'size': size, 'unit': 'mm', 'scale': [v/size for v in part.cavity],
                            'location': [a+b for a,b in zip(part.location, part.cavity_offset)]}
                        if cutter_args['primitive'] == 'CYLINDER':
                            cutter_args['segments'] = 96
                        cutter = e.call('object.create_primitive', cutter_args)['object_id']
                        e.call('mesh.boolean', {'object_id': oid, 'operand_id': cutter,
                                              'operation': 'DIFFERENCE'})
                        e.call('object.delete', {'object_id': cutter})
                        e.call('mesh.cleanup', {'object_id': oid, 'unit': 'mm', 'merge_distance': .001})
                    e.call('material.assign', {'object_id': oid, 'material_id': materials[part.material]})
                    cache[key] = oid
                roles[part.role] = oid
            # Inspection is independent of construction and precedes acceptance.
            inspected = e.call('scene.inspect_objects', {'object_ids': list(roles.values())})
            assert len(inspected['objects']) == len(roles)
            report = bridge.submit({'finish': roles})
            if 'bridge_error' in report:
                raise RuntimeError(report['bridge_error'])
            process.stdin.close()
            assert process.wait(timeout=30) == 0
            write_json(output/'agent_provenance.json', {
                'agent': 'Codex', 'execution_style': 'scripted_agent',
                'reasoning_scope': 'This active Codex session authored and executed plans; no per-call model invocation.',
                'uses_manual_build_recipe': False, 'uses_shared_briefs': True,
                'independent_blind_model_comparison': False})
            entries.append({'benchmark': brief.name, 'status': 'passed' if
                report['reports']['supported_technical_passed'] else 'failed', 'metrics': report['metrics']})
        except Exception as exc:
            entries.append({'benchmark': brief.name, 'status': 'error',
                            'error_type': type(exc).__name__, 'message': str(exc)})
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=10)
            if not process.stdin.closed:
                process.stdin.close()
            process.stdout.close()
    write_json(root/'summary.json', {'mode': 'scripted_agent', 'agent': 'Codex',
               'benchmarks': entries, 'expected_benchmarks': len(CATALOG),
               'complete': len(entries) == len(CATALOG),
               'passed': len(entries) == len(CATALOG) and all(r['status'] == 'passed' for r in entries)})
    print(brief.name, entries[-1]['status'], flush=True)

raise SystemExit(0 if len(entries) == len(CATALOG) and
                 all(r['status'] == 'passed' for r in entries) else 1)
