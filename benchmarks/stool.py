"""Repeatable manual stool baseline using only the discoverable public API."""
import argparse
import base64
import json
from pathlib import Path

from controller.client import BlenderClient


PROMPT = ('Create a modern wooden stool, 450 mm high and 400 mm wide, with four '
          'slightly angled and slightly tapered legs, rounded edges, clean '
          'geometry, and a wood-like material.')


class ToolRejected(RuntimeError):
    """A structured API rejection the agent may inspect and repair."""


class Exercise:
    def __init__(self, client):
        self.client = client
        self.trace = []

    def call(self, tool, arguments=None):
        arguments = {} if arguments is None else arguments
        response = self.client.call(tool, arguments)
        # Keep response state and failures; PNG payloads are separate artifacts.
        recorded = json.loads(json.dumps(response))
        for image in recorded.get('result', {}).get('images', []):
            image.pop('png_base64', None)
        self.trace.append({'tool': tool, 'arguments': json.loads(json.dumps(arguments)),
                           'response': recorded})
        if not response['success']:
            raise ToolRejected(f"{tool}: {response['error']['code']}")
        return response['result']

    def bevel(self, object_id, width):
        handle = self.call('mesh.query', {
            'object_id': object_id, 'element_type': 'EDGE',
            'selectors': [{'kind': 'manifold'}],
        })['selection_handle']
        self.call('mesh.bevel', {'selection_handle': handle,
                                'width': width, 'unit': 'mm', 'segments': 3})


def build_manual(exercise, *, engine="WORKBENCH"):
    """Run in a fresh isolated client; commit only the supported technical checks."""
    e = exercise
    e.call('runtime.get_version')
    e.call('runtime.list_tools')
    transaction = e.call('transaction.begin')['transaction_id']
    control = {'transaction_id': transaction}
    try:
        # Page before mutating: every mutation invalidates listing cursors.
        objects = []
        arguments = {'limit': 100}
        while True:
            page = e.call('scene.list_objects', arguments)
            objects.extend(page['objects'])
            if page['next_cursor'] is None:
                break
            arguments['cursor'] = page['next_cursor']
        for obj in objects:
            e.call('object.delete', {'object_id': obj['object_id']})
        seat = e.call('object.create_primitive', {
            'primitive': 'CUBE', 'name': 'Seat', 'size': 400, 'unit': 'mm',
            'scale': [1, 1, .1], 'location': [0, 0, 430],
        })['object_id']
        e.bevel(seat, 5)
        # A 1230 mm cone cut 820 mm from its tip yields a 410 mm frustum,
        # with a 45 mm top and 30 mm foot. All edits use public core tools.
        cutter = e.call('object.create_primitive', {
            'primitive': 'CUBE', 'name': 'Leg_tip_cutter', 'size': 2000,
            'unit': 'mm', 'location': [0, 0, -1000],
        })['object_id']
        legs = []
        for x, y in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            leg = e.call('object.create_primitive', {
                'primitive': 'CONE', 'name': f'Leg_{x}_{y}',
                'size': 45, 'unit': 'mm', 'scale': [1, 1, 1230 / 45],
                'rotation': [180, 0, 0], 'location': [0, 0, -205],
                'segments': 32,
            })['object_id']
            e.call('mesh.boolean', {'object_id': leg, 'operand_id': cutter,
                                   'operation': 'DIFFERENCE'})
            handle = e.call('mesh.query', {
                'object_id': leg, 'element_type': 'EDGE',
                'selectors': [{'kind': 'dihedral_angle', 'minimum': 30, 'maximum': 150}],
            })['selection_handle']
            e.call('mesh.bevel', {'selection_handle': handle, 'width': .1,
                                  'unit': 'mm', 'segments': 3})
            e.call('object.transform', {
                'object_id': leg, 'rotation': [180 + y * 4, -x * 4, 0],
                'location': [x * 145, y * 145, -205], 'unit': 'mm',
            })
            bounds = e.call('scene.inspect_objects', {
                'object_ids': [leg]})['objects'][0]['evaluated_bounds']
            e.call('object.transform', {
                'object_id': leg, 'unit': 'mm',
                'location': [x * 145, y * 145, -205 - bounds['min'][2] * 1000],
            })
            legs.append(leg)
        e.call('object.delete', {'object_id': cutter})
        material = e.call('material.create', {
            'name': 'Warm wood', 'base_color': [.22, .08, .025, 1],
            'roughness': .65, 'metallic': 0})['material_id']
        for object_id in [seat, *legs]:
            e.call('material.assign', {'object_id': object_id, 'material_id': material})
        roles = {'seat': seat, 'legs': legs}
        reports = evaluate(e, roles)
        if not reports['supported_technical_passed']:
            raise RuntimeError('Manual baseline failed supported technical criteria')
        images = e.call('observe.render_multiview', {'object_ids': [seat, *legs], 'engine': engine})
        e.call('scene.diff', control)
        e.call('transaction.commit', control)
        return roles, reports, images
    except Exception:
        e.call('transaction.rollback', control)
        raise


def evaluate(exercise, roles):
    """Use explicit role UUIDs; never infer four legs from object names."""
    seat, legs = roles['seat'], roles['legs']
    if len(legs) != 4 or len(set([seat, *legs])) != 5:
        raise ValueError('Expected one seat and four distinct leg UUIDs')
    ids = [seat, *legs]
    e = exercise
    geometry = e.call('validate.geometry', {'object_ids': ids})
    dimensions = e.call('validate.dimensions', {
        'object_ids': ids, 'expected': [400, 400, 450], 'unit': 'mm', 'tolerance': 2})
    assembly = e.call('validate.assembly', {
        'object_ids': ids, 'unit': 'mm', 'tolerance': 2,
        'checks': [{'kind': 'connected'}] +
                  [{'kind': 'ground', 'object_id': leg} for leg in legs] +
                  [{'kind': 'support', 'object_id': leg, 'other_id': seat} for leg in legs]})
    count = e.call('validate.assembly', {
        'object_ids': legs, 'checks': [{'kind': 'component_count', 'expected': 4}]})
    materials = e.call('validate.asset', {'object_ids': ids, 'require_materials': True})
    passed = all(report['passed'] for report in (geometry, dimensions, assembly, count, materials))
    failures = []
    for name, report in (('geometry', geometry), ('dimensions', dimensions),
                         ('assembly', assembly), ('leg_count', count)):
        if not report['passed']:
            failures.append({'criterion': name, 'classification': 'model_or_recipe',
                             'evidence': [c for c in report['checks'] if not c['passed']]})
    if any(c['code'] == 'MATERIAL_ASSIGNMENT' and not c['passed']
           for c in materials['checks']):
        failures.append({'criterion': 'wood_material', 'classification': 'model_or_recipe',
                         'evidence': 'Material assignment check fails; public material creation and assignment are available.'})
    return {'supported_technical_passed': passed, 'full_benchmark_passed': False,
            'geometry': geometry, 'dimensions': dimensions, 'assembly': assembly,
            'leg_count': count, 'materials': materials,
            'failures': failures, 'visual_evaluation': None,
            'unverified': ['leg_angle_and_taper', 'rounded_edges', 'visual_rubric',
                           'exact_surface_contact_and_physical_stability']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine', choices=['WORKBENCH', 'EEVEE'], default='WORKBENCH')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite a previous benchmark's evidence.
    if any(args.output.iterdir()):
        parser.error('--output must be an empty directory')
    with BlenderClient(executable=args.blender, request_timeout=90) as client:
        exercise = Exercise(client)
        try:
            roles, reports, rendered = build_manual(exercise, engine=args.engine)
            for image in rendered['images']:
                (args.output / (image['camera']['view'] + '.png')).write_bytes(
                    base64.b64decode(image['png_base64'], validate=True))
            report = {'benchmark': 'stool-v1', 'mode': 'manual', 'prompt': PROMPT,
                      'roles': roles, 'reports': reports, 'session_id': client.session_id,
                      'final_revision': client.revision}
            (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        finally:
            (args.output / 'trace.json').write_text(json.dumps(exercise.trace, indent=2) + '\n')
    print(f'Manual stool evidence: {args.output}')


if __name__ == '__main__':
    main()
