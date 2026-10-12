"""Milestone 15 manual benchmarks: python -m benchmarks.expansion --output DIR."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from benchmarks.catalog import CATALOG, material_key, material_arguments
from benchmarks.stool import Exercise
from controller.client import BlenderClient


RUBRIC_VERSION = 'asset-quality-v1'
CATEGORIES = ('proportions', 'silhouette', 'structural_plausibility',
              'surface_cleanliness', 'material_plausibility')


def object_ids(brief, roles):
    if not isinstance(roles, dict) or set(roles) != {p.role for p in brief.parts}:
        raise ValueError('Finish requires exactly the advertised role names')
    ids = [roles[p.role] for p in brief.parts]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Each role requires a distinct nonempty object UUID')
    return ids


def scene_ids(exercise):
    ids, arguments = [], {'limit': 100}
    while True:
        page = exercise.call('scene.list_objects', arguments)
        ids.extend(o['object_id'] for o in page['objects'])
        if page['next_cursor'] is None:
            return ids
        arguments['cursor'] = page['next_cursor']


def build_recipe(exercise, brief):
    """Model only: checkpoint ownership and acceptance live in the harness."""
    e = exercise
    e.call('runtime.get_version')
    e.call('runtime.describe_tool', {'name': 'object.create_primitive'})
    e.call('runtime.describe_tool', {'name': 'mesh.boolean'})
    for oid in scene_ids(e):
        e.call('object.delete', {'object_id': oid})
    materials = {}
    roles = {}
    for part in brief.parts:
        key = material_key(part)
        if key not in materials:
            materials[key] = e.call('material.create', material_arguments(part))['material_id']
        size = max(part.dimensions)
        args = {'primitive': part.primitive, 'name': part.role,
                'size': size, 'unit': 'mm', 'scale': [d/size for d in part.dimensions],
                'location': list(part.location), 'rotation': list(part.rotation)}
        if part.primitive in ('CYLINDER', 'CONE'):
            args['segments'] = 128
        if part.top_diameter:
            diameter, _, height = part.dimensions
            full_height = height * diameter / (diameter-part.top_diameter)
            args['scale'][2] = full_height / size
            args['location'][2] += (full_height-height)/2
        oid = e.call('object.create_primitive', args)['object_id']
        if part.top_diameter:
            trim_size = 4 * max(part.dimensions)
            trim = e.call('object.create_primitive', {
                'primitive': 'CUBE', 'size': trim_size, 'unit': 'mm',
                'location': [part.location[0], part.location[1],
                             part.location[2]+part.dimensions[2]/2+trim_size/2]})['object_id']
            e.call('mesh.boolean', {'object_id': oid, 'operand_id': trim, 'operation': 'DIFFERENCE'})
            e.call('object.delete', {'object_id': trim})
        # Bake the primitive's scale through the public boolean API, so bevel
        # widths measure real millimetres on both long panels and narrow legs.
        unscaled = e.call('object.create_primitive', {'primitive': 'CUBE',
            'size': 3*size, 'unit': 'mm', 'location': list(part.location),
            'rotation': list(part.rotation), 'name': part.role})['object_id']
        e.call('mesh.boolean', {'object_id': unscaled, 'operand_id': oid, 'operation': 'INTERSECT'})
        e.call('object.delete', {'object_id': oid})
        oid = unscaled
        # Round the primitive before cutting. Beveling the EXACT solver's
        # coplanar annular faces can create zero-area miter faces.
        selected = e.call('mesh.query', {'object_id': oid, 'element_type': 'EDGE',
                          'selectors': [{'kind': 'dihedral_angle', 'minimum': 30, 'maximum': 150}]})
        if selected['matched_count']:
            e.call('mesh.bevel', {'selection_handle': selected['selection_handle'],
                                  'width': min(1.2, min(part.dimensions)/5), 'unit': 'mm', 'segments': 4})
        if part.cavity:
            # Equal XY dimensions denote a cylindrical cutter.
            cylindrical = part.cavity[0] == part.cavity[1]
            cutter_size = max(part.cavity)
            cutter_args = {'primitive': 'CYLINDER' if cylindrical else 'CUBE',
                           'name': 'temporary_cavity_cutter', 'size': cutter_size, 'unit': 'mm',
                           'scale': [d/cutter_size for d in part.cavity],
                           'location': [a+b for a, b in zip(part.location, part.cavity_offset)]}
            if cylindrical:
                cutter_args['segments'] = 128
            if part.cavity_top_diameter:
                diameter, _, height = part.cavity
                slope = (diameter-part.cavity_top_diameter)/height
                # Extend below the shoulder to avoid a coplanar lower cut.
                extended_diameter = diameter+slope
                full_height = extended_diameter/slope
                cutter_args.update(primitive='CONE', size=extended_diameter,
                    scale=[1, 1, full_height/extended_diameter],
                    location=[part.location[0], part.location[1],
                              part.location[2]-height/2-1+full_height/2])
            cutter = e.call('object.create_primitive', cutter_args)['object_id']
            e.call('mesh.boolean', {'object_id': oid, 'operand_id': cutter,
                                   'operation': 'DIFFERENCE'})
            e.call('object.delete', {'object_id': cutter})
            e.call('mesh.cleanup', {'object_id': oid, 'merge_distance': .001, 'unit': 'mm'})
        for dimensions, offset in (*part.recesses, *part.openings):
            size = max(dimensions)
            cutter = e.call('object.create_primitive', {
                'primitive': 'CUBE', 'size': size, 'unit': 'mm',
                'scale': [d/size for d in dimensions],
                'location': [a+b for a, b in zip(part.location, offset)]})['object_id']
            e.call('mesh.boolean', {'object_id': oid, 'operand_id': cutter,
                                   'operation': 'DIFFERENCE'})
            e.call('object.delete', {'object_id': cutter})
            e.call('mesh.cleanup', {'object_id': oid, 'merge_distance': .001, 'unit': 'mm'})
        for diameter, height, offset in part.holes:
            cutter = e.call('object.create_primitive', {'primitive': 'CYLINDER',
                'size': diameter, 'unit': 'mm', 'scale': [1, 1, height/diameter],
                'segments': 128, 'location': [a+b for a,b in zip(part.location,offset)]})['object_id']
            e.call('mesh.boolean', {'object_id': oid, 'operand_id': cutter, 'operation': 'DIFFERENCE'})
            e.call('object.delete', {'object_id': cutter})
            e.call('mesh.cleanup', {'object_id': oid, 'merge_distance': .001, 'unit': 'mm'})
        e.call('material.assign', {'object_id': oid, 'material_id': materials[key]})
        roles[part.role] = oid
    return roles


def evaluate(exercise, brief, roles):
    ids = object_ids(brief, roles)
    e = exercise
    geometry = e.call('validate.geometry', {'object_ids': ids})
    dimensions = e.call('validate.dimensions', {'object_ids': ids,
                       'expected': list(brief.dimensions), 'unit': 'mm', 'tolerance': 2})
    checks = [{'kind': 'connected'}, {'kind': 'component_count', 'expected': len(ids)}]
    checks += [{'kind': 'ground', 'object_id': roles[r]} for r in brief.grounds]
    checks += [{'kind': 'contact', 'object_id': roles[a], 'other_id': roles[b]}
               for a, b in brief.contacts]
    assembly = e.call('validate.assembly', {'object_ids': ids, 'checks': checks,
                                          'unit': 'mm', 'tolerance': 2})
    embedded = {f'{a}/{b}': e.call('validate.assembly', {
        'object_ids':[roles[a],roles[b]], 'checks':[{'kind':'connected'}],
        'unit':'mm','tolerance':2}) for a,b in brief.embedded}
    materials = e.call('validate.asset', {'object_ids': ids, 'require_materials': True})
    # Independently inspect individual roles, not merely the union silhouette.
    part_dimensions = {part.role: e.call('validate.dimensions', {
        'object_ids': [roles[part.role]], 'expected': list(part.world_dimensions),
        'unit': 'mm', 'tolerance': 2}) for part in brief.parts}
    cavities = {}
    recesses = {}
    tapers = {}
    openings = {}
    holes = {}
    for part in brief.parts:
        for index, (dims, offset) in enumerate(part.openings):
            center = [a+b for a,b in zip(part.location,offset)]
            selected = e.call('mesh.query', {'object_id':roles[part.role],
                'element_type':'FACE', 'space':'WORLD', 'selectors':[
                    {'kind':'within_bbox','min':[(c-d/2)/1000 for c,d in zip(center,dims)],
                     'max':[(c+d/2)/1000 for c,d in zip(center,dims)],'tolerance':.00001},
                    {'kind':'normal_direction','direction':[1,0,0],'angle_degrees':1}]})
            openings[f'{part.role}_{index}'] = {'passed':selected['matched_count']>0,
                                               'interior_faces':selected['matched_count']}
        for index, (diameter,height,offset) in enumerate(part.holes):
            center = [a+b for a,b in zip(part.location,offset)]
            dims = (diameter,diameter,height)
            selected = e.call('mesh.query', {'object_id':roles[part.role],
                'element_type':'FACE','space':'WORLD','selectors':[
                    {'kind':'within_bbox','min':[(c-d/2)/1000 for c,d in zip(center,dims)],
                     'max':[(c+d/2)/1000 for c,d in zip(center,dims)],'tolerance':.00001},
                    {'kind':'side_faces','angle_degrees':5},
                    {'kind':'area_range','minimum':1e-8,'maximum':1}]})
            holes[f'{part.role}_{index}'] = {'passed':selected['matched_count']>0,
                                            'interior_faces':selected['matched_count']}
        if part.top_diameter:
            selected = e.call('mesh.query', {
                'object_id': roles[part.role], 'element_type': 'FACE', 'space': 'WORLD',
                'selectors': [{'kind': 'side_faces', 'angle_degrees': 80},
                    {'kind': 'area_range', 'minimum': .00001, 'maximum': 1},
                    {'kind': 'normal_direction', 'direction': [0, 0, 1], 'angle_degrees': 45}]})
            tapers[part.role] = {'passed': selected['matched_count'] > 0,
                                 'sloped_faces': selected['matched_count']}
        for index, (recess_dimensions, offset) in enumerate(part.recesses):
            center = [a+b for a, b in zip(part.location, offset)]
            low = [(c-d/2)/1000 for c, d in zip(center, recess_dimensions)]
            high = [(c+d/2)/1000 for c, d in zip(center, recess_dimensions)]
            # Recesses in these briefs open toward -Y. Require the pocket's
            # back wall, excluding triangulated exterior faces on a filled box.
            low[1] = high[1] - .00001
            selected = e.call('mesh.query', {
                'object_id': roles[part.role], 'element_type': 'FACE', 'space': 'WORLD',
                'selectors': [{'kind': 'within_bbox',
                               'min': low, 'max': high, 'tolerance': .00001},
                              {'kind': 'normal_direction', 'direction': [0, -1, 0],
                               'angle_degrees': 1}]})
            recesses[f'{part.role}_{index+1}'] = {
                'passed': selected['matched_count'] > 0,
                'interior_faces': selected['matched_count']}
        if not part.cavity:
            continue
        center = [a+b for a, b in zip(part.location, part.cavity_offset)]
        selectors = [{'kind': 'within_bbox',
                      'min': [(c-d/2)/1000 for c, d in zip(center, part.cavity)],
                      'max': [(c+d/2)/1000 for c, d in zip(center, part.cavity)],
                      'tolerance': .00001}]
        if part.cavity_top_diameter:
            selectors.extend([{'kind': 'side_faces', 'angle_degrees': 80},
                {'kind': 'area_range', 'minimum': .00001, 'maximum': 1},
                {'kind': 'normal_direction', 'direction': [0, 0, -1], 'angle_degrees': 45}])
        elif part.cavity[0] == part.cavity[1]:
            # A solid cap triangulated by a boolean may have triangles inside
            # the bore's box. Only interior side walls establish a round cavity.
            selectors.append({'kind': 'side_faces', 'angle_degrees': 5})
        selected = e.call('mesh.query', {
            'object_id': roles[part.role], 'element_type': 'FACE', 'space': 'WORLD',
            'selectors': selectors})
        cavities[part.role] = {'passed': selected['matched_count'] > 0,
                              'interior_faces': selected['matched_count']}
    coverage = {'passed': set(scene_ids(e)) == set(ids),
                'expected_object_count': len(ids)}
    # This brief has an explicit planar joint. Check actual opposing surfaces,
    # since overlapping shade/stem AABBs also accept a stem inside empty space.
    joints = {}
    if brief.name == 'desk_lamp':
        for role, direction in (('stem', [0, 0, 1]), ('shade', [0, 0, -1])):
            selected = e.call('mesh.query', {
                'object_id': roles[role], 'element_type': 'FACE', 'space': 'WORLD',
                'selectors': [{'kind': 'within_bbox',
                               'min': [-.073, -.073, .4419],
                               'max': [.073, .073, .4421], 'tolerance': .00001},
                              {'kind': 'normal_direction', 'direction': direction,
                               'angle_degrees': 1}]})
            joints[role] = {'passed': selected['matched_count'] > 0,
                            'joint_faces': selected['matched_count']}
    reports = {'geometry': geometry, 'dimensions': dimensions, 'assembly': assembly,
               'materials': materials, 'scene_coverage': coverage,
               'embedded_joinery': {'passed':all(r['passed'] for r in embedded.values()), 'roles':embedded},
               'cavity_surfaces': {'passed': all(r['passed'] for r in cavities.values()),
                                   'roles': cavities},
               'recess_surfaces': {'passed': all(r['passed'] for r in recesses.values()),
                                   'roles': recesses},
               'aperture_surfaces': {'passed': all(r['passed'] for r in openings.values()), 'roles': openings},
               'additional_bore_surfaces': {'passed': all(r['passed'] for r in holes.values()), 'roles': holes},
               'role_dimensions': {'passed': all(r['passed'] for r in part_dimensions.values()),
                                   'roles': part_dimensions},
               'declared_surface_joints': {'passed': all(r['passed'] for r in joints.values()),
                                           'roles': joints},
               'declared_taper_surfaces': {'passed': all(r['passed'] for r in tapers.values()),
                                           'roles': tapers}}
    failures = [{'criterion': name, 'classification': 'model_or_recipe',
                 'evidence': report} for name, report in reports.items() if not report['passed']]
    return {'supported_technical_passed': not failures, 'full_benchmark_passed': False,
            **reports, 'failures': failures, 'visual_evaluation': None,
            'unverified': ['visual_rubric', 'exact_surface_contact', 'physical_stability',
                           'interior_cavity_and_hole_accuracy', 'production_readiness',
                           *brief.limitations]}


def metrics(trace):
    rejected = [entry for entry in trace if not entry['response']['success']]
    return {'tool_calls': len(trace), 'tool_seconds': sum(e.get('seconds', 0) for e in trace),
            'structured_rejections': len(rejected),
            'selection_rejections': sum(e['tool'] in ('mesh.query', 'mesh.inspect_selection') or
                e['response']['error']['code'] in ('INVALID_SELECTION_HANDLE', 'STALE_SELECTION',
                                                  'EMPTY_SELECTION') for e in rejected),
            'rollbacks': sum(e['tool'] == 'transaction.rollback' and e['response']['success']
                             for e in trace),
            'rejections': [{'tool': e['tool'], 'error': e['response']['error']} for e in rejected],
            'context_usage': None,
            'context_usage_note': 'The local bridge cannot measure model token usage.'}


def save_images(output, images):
    for image in images['images']:
        (output / (image['camera']['view'] + '.png')).write_bytes(
            base64.b64decode(image['png_base64'], validate=True))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def run_manual(brief, output, *, executable='blender', engine='WORKBENCH', render=True):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Benchmark output must be empty')
    with BlenderClient(executable=executable, request_timeout=180) as client:
        e = Exercise(client)
        active = False
        try:
            control = e.call('transaction.begin')
            control = {'transaction_id': control['transaction_id']}
            active = True
            roles = build_recipe(e, brief)
            reports = evaluate(e, brief, roles)
            if render:
                save_images(output, e.call('observe.render_multiview', {
                    'object_ids': object_ids(brief, roles), 'engine': engine}))
            e.call('scene.diff', control)
            action = 'transaction.commit' if reports['supported_technical_passed'] else 'transaction.rollback'
            e.call(action, control)
            active = False
            report = {'benchmark': f'{brief.name}-v{brief.version}', 'mode': 'manual', 'prompt': brief.prompt,
                      'roles': roles, 'reports': reports, 'outcome': action,
                      'runtime': e.call('runtime.get_version'), 'engine': engine,
                      'session_id': client.session_id, 'final_revision': client.revision,
                      'metrics': metrics(e.trace)}
            write_json(output / 'report.json', report)
            return report
        finally:
            try:
                if active:
                    e.call('transaction.rollback', control)
            finally:
                write_json(output / 'trace.json', e.trace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--benchmark', choices=tuple(CATALOG))
    parser.add_argument('--engine', choices=('WORKBENCH', 'EEVEE'), default='WORKBENCH')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('--output must be empty')
    entries = []
    started = time.perf_counter()
    briefs = [CATALOG[args.benchmark]] if args.benchmark else list(CATALOG.values())
    for brief in briefs:
        try:
            report = run_manual(brief, args.output / brief.name,
                                executable=args.blender, engine=args.engine)
            entries.append({'benchmark': brief.name, 'status': 'passed' if
                            report['reports']['supported_technical_passed'] else 'failed',
                            'metrics': report['metrics'], 'report': brief.name+'/report.json'})
        except Exception as exc:
            entries.append({'benchmark': brief.name, 'status': 'error',
                            'error_type': type(exc).__name__, 'message': str(exc)})
        write_json(args.output / 'summary.json', {
            'format_version': 1, 'timestamp': datetime.now(timezone.utc).isoformat(),
            'seconds': time.perf_counter()-started, 'mode': 'manual', 'benchmarks': entries,
            'expected_benchmarks': len(briefs), 'complete': len(entries) == len(briefs),
            'passed': len(entries) == len(briefs) and all(e['status'] == 'passed' for e in entries)})
        print(f"{brief.name}: {entries[-1]['status']}", flush=True)
    return 0 if all(e['status'] == 'passed' for e in entries) else 1


if __name__ == '__main__':
    raise SystemExit(main())
