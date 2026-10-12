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

from benchmarks.catalog import CATALOG, material_key, material_arguments
from benchmarks.expansion import write_json
from benchmarks.replay import BridgeClient
from benchmarks.stool import Exercise

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path('artifacts/expansion-m15-codex'))
parser.add_argument('--blender', default='blender')
parser.add_argument('--engine', choices=('WORKBENCH', 'EEVEE'), default='WORKBENCH')
parser.add_argument('--benchmark', choices=tuple(CATALOG))
cli_args = parser.parse_args()
root = cli_args.output
root.mkdir(parents=True, exist_ok=True)
if any(root.iterdir()):
    raise SystemExit('Output must be empty')
entries = []
briefs = [CATALOG[cli_args.benchmark]] if cli_args.benchmark else list(CATALOG.values())
for brief in briefs:
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
            # Small casing fittings do not need 192 sides; lower sampling keeps
            # intermediate boolean meshes within the unchanged recovery scan cap.
            round_segments = 96 if brief.name == 'product_casing' else 192
            roles, cache, materials = {}, {}, {}
            for part in brief.parts:
                material = material_key(part)
                if material not in materials:
                    materials[material] = e.call('material.create',
                        material_arguments(part, agent=True))['material_id']
                key = (part.dimensions, part.primitive, part.material,
                       part.cavity, part.cavity_offset, part.recesses,
                       part.top_diameter, part.cavity_top_diameter, part.rotation, part.holes, part.openings)
                if key in cache:
                    oid = e.call('object.duplicate', {'object_id': cache[key],
                                                    'name': part.role})['object_id']
                    e.call('object.transform', {'object_id': oid, 'unit': 'mm',
                                                 'location': list(part.location)})
                else:
                    size = max(part.dimensions)
                    args = {'primitive': part.primitive, 'size': size, 'unit': 'mm',
                            'scale': [v/size for v in part.dimensions],
                            'location': list(part.location), 'rotation': list(part.rotation), 'name': part.role}
                    if part.primitive in ('CYLINDER', 'CONE'):
                        args['segments'] = round_segments
                    if part.top_diameter:
                        base_diameter, _, rise = part.dimensions
                        cone_rise = rise/(1-part.top_diameter/base_diameter)
                        args['scale'][2] = cone_rise/size
                        args['location'][2] = part.location[2]-rise/2+cone_rise/2
                    oid = e.call('object.create_primitive', args)['object_id']
                    if part.top_diameter:
                        span = max(part.dimensions)*3
                        trim = e.call('object.create_primitive', {
                            'primitive': 'CUBE', 'size': span, 'unit': 'mm',
                            'location': [part.location[0], part.location[1],
                                         part.location[2]+rise/2+span/2]})['object_id']
                        e.call('mesh.boolean', {'object_id': oid, 'operand_id': trim,
                                              'operation': 'DIFFERENCE'})
                        e.call('object.delete', {'object_id': trim})
                    unscaled = e.call('object.create_primitive', {'primitive': 'CUBE',
                        'size': 3*size, 'unit': 'mm', 'location': list(part.location),
                        'rotation': list(part.rotation), 'name': part.role})['object_id']
                    e.call('mesh.boolean', {'object_id':unscaled, 'operand_id':oid, 'operation':'INTERSECT'})
                    e.call('object.delete', {'object_id':oid})
                    oid = unscaled
                    query = e.call('mesh.query', {'object_id': oid, 'element_type': 'EDGE',
                              'selectors': [{'kind': 'dihedral_angle', 'minimum': 45, 'maximum': 135}]})
                    if query['matched_count']:
                        e.call('mesh.bevel', {'selection_handle': query['selection_handle'],
                                             'width': min(1.0, min(part.dimensions)/5), 'unit': 'mm', 'segments': 4})
                    if part.cavity:
                        size = max(part.cavity)
                        cutter_args = {'primitive': 'CYLINDER' if part.cavity[0] == part.cavity[1] else 'CUBE',
                            'size': size, 'unit': 'mm', 'scale': [v/size for v in part.cavity],
                            'location': [a+b for a,b in zip(part.location, part.cavity_offset)]}
                        if cutter_args['primitive'] == 'CYLINDER':
                            cutter_args['segments'] = round_segments
                        if part.cavity_top_diameter:
                            bore_diameter, _, bore_rise = part.cavity
                            reduction = (bore_diameter-part.cavity_top_diameter)/bore_rise
                            extended_bore = bore_diameter+reduction
                            cone_rise = extended_bore/reduction
                            cutter_args.update(primitive='CONE', size=extended_bore,
                                scale=[1, 1, cone_rise/extended_bore],
                                location=[part.location[0], part.location[1],
                                          part.location[2]-bore_rise/2-1+cone_rise/2])
                        cutter = e.call('object.create_primitive', cutter_args)['object_id']
                        e.call('mesh.boolean', {'object_id': oid, 'operand_id': cutter,
                                              'operation': 'DIFFERENCE'})
                        e.call('object.delete', {'object_id': cutter})
                        e.call('mesh.cleanup', {'object_id': oid, 'unit': 'mm', 'merge_distance': .001})
                    for dimensions, offset in (*part.recesses, *part.openings):
                        size = max(dimensions)
                        cutter = e.call('object.create_primitive', {
                            'primitive': 'CUBE', 'size': size, 'unit': 'mm',
                            'scale': [v/size for v in dimensions],
                            'location': [a+b for a, b in zip(part.location, offset)]})['object_id']
                        e.call('mesh.boolean', {'object_id': oid, 'operand_id': cutter,
                                              'operation': 'DIFFERENCE'})
                        e.call('object.delete', {'object_id': cutter})
                        e.call('mesh.cleanup', {'object_id': oid, 'unit': 'mm', 'merge_distance': .001})
                    for diameter, height, offset in part.holes:
                        cutter = e.call('object.create_primitive', {'primitive':'CYLINDER',
                            'size':diameter, 'unit':'mm', 'scale':[1,1,height/diameter],
                            'segments':round_segments, 'location':[a+b for a,b in zip(part.location,offset)]})['object_id']
                        e.call('mesh.boolean', {'object_id':oid,'operand_id':cutter,'operation':'DIFFERENCE'})
                        e.call('object.delete', {'object_id':cutter})
                        e.call('mesh.cleanup', {'object_id':oid,'unit':'mm','merge_distance':.001})
                    e.call('material.assign', {'object_id': oid, 'material_id': materials[material]})
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
               'benchmarks': entries, 'expected_benchmarks': len(briefs),
               'complete': len(entries) == len(briefs),
               'passed': len(entries) == len(briefs) and all(r['status'] == 'passed' for r in entries)})
    print(brief.name, entries[-1]['status'], flush=True)

raise SystemExit(0 if len(entries) == len(briefs) and
                 all(r['status'] == 'passed' for r in entries) else 1)
