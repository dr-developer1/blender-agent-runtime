import unittest

from runtime.errors import ToolError
from runtime.schemas import validate_arguments
from runtime.validation import (GEOMETRY_SCHEMA, ASSEMBLY_SCHEMA, DIMENSIONS_SCHEMA,
                                geometry_checks, assembly_checks, dimension_checks, report)


def sample(points, edges=(), faces=(), normals=()):
    return {'object_id': 'part', 'points': points, 'edges': edges, 'faces': faces,
            'normals': normals, 'negative_scale': False}


class ValidationTests(unittest.TestCase):
    def test_loose_and_degenerate_geometry(self):
        data = sample([(0,0,0), (1,0,0), (2,0,0), (9,0,0)],
                      [(0,1), (1,2), (2,0)], [(0,1,2)], [(0,0,0)])
        checks = {c['code']: c for c in geometry_checks(data, True, 1e-12)}
        self.assertEqual(checks['LOOSE_VERTICES']['details']['count'], 1)
        self.assertEqual(checks['DEGENERATE_FACES']['details']['count'], 1)
        self.assertFalse(checks['INVALID_NORMALS']['passed'])
        self.assertFalse(report(list(checks.values()))['passed'])

    def test_open_surface_policy_and_duplicate_positions(self):
        data = sample([(0,0,0),(1,0,0),(0,1,0)], [(0,1),(1,2),(2,0)],
                      [(0,1,2)], [(0,0,1)])
        self.assertTrue(report(geometry_checks(data, False, 1e-12))['passed'])
        self.assertFalse(report(geometry_checks(data, True, 1e-12))['passed'])
        data['points'].append((0,0,0))
        checks = {c['code']: c for c in geometry_checks(data, False, 1e-12)}
        self.assertEqual(checks['COINCIDENT_VERTICES']['details']['count'], 1)

    def test_nonfinite_geometry_is_a_finding(self):
        checks = geometry_checks(sample([(float('nan'),0,0)]), True, 1e-12)
        self.assertEqual(checks[0]['code'], 'NONFINITE_GEOMETRY')
        self.assertFalse(report(checks)['passed'])

    def test_world_dimensions_and_units(self):
        bounds = {'part': {'min': [0,0,0], 'max': [.4,.4,.45]}}
        checks = dimension_checks(bounds, {'expected': [400,400,450], 'unit': 'mm', 'tolerance': 2})
        self.assertTrue(report(checks)['passed'])
        checks = dimension_checks(bounds, {'expected': [400,400,460], 'unit': 'mm', 'tolerance': 2})
        self.assertFalse(report(checks)['passed'])

    def test_assembly_contact_support_ground_overlap_clearance_symmetry(self):
        bounds = {'leg': {'min': [-1,-1,0], 'max': [0,0,1]},
                  'seat': {'min': [-1,-1,1], 'max': [1,1,2]}}
        checks = [{'kind': 'contact', 'object_id': 'leg', 'other_id': 'seat'},
                  {'kind': 'support', 'object_id': 'leg', 'other_id': 'seat'},
                  {'kind': 'ground', 'object_id': 'leg'},
                  {'kind': 'no_overlap', 'object_id': 'leg', 'other_id': 'seat'},
                  {'kind': 'component_count', 'expected': 2},
                  {'kind': 'connected'}]
        self.assertTrue(report(assembly_checks(bounds, {'checks': checks}))['passed'])
        self.assertFalse(report(assembly_checks(bounds, {'checks': [
            {'kind': 'clearance', 'object_id': 'leg', 'other_id': 'seat', 'minimum': .1}]}))['passed'])
        self.assertTrue(report(assembly_checks(bounds, {'checks': [
            {'kind': 'symmetry', 'object_id': 'seat', 'other_id': 'seat', 'axis': 'X'}]}))['passed'])

    def test_invalid_assembly_contracts(self):
        bounds = {'part': {'min': [0,0,0], 'max': [1,1,1]}}
        for check in [{'kind': 'contact', 'object_id': 'part'},
                      {'kind': 'ground', 'object_id': 'missing'},
                      {'kind': 'ground', 'object_id': 'part', 'minimum': 1}]:
            with self.subTest(check=check), self.assertRaises(ToolError):
                assembly_checks(bounds, {'checks': [check]})

    def test_strict_bounded_schemas(self):
        for schema, args in [(GEOMETRY_SCHEMA, {'object_ids': []}),
            (GEOMETRY_SCHEMA, {'object_ids': ['a'], 'require_closed': 1}),
            (DIMENSIONS_SCHEMA, {'object_ids': ['a'], 'expected': [1,2,float('nan')]}),
            (ASSEMBLY_SCHEMA, {'object_ids': ['a'], 'checks': [{'kind': 'magic'}]})]:
            with self.subTest(args=args), self.assertRaises(ToolError):
                validate_arguments(args, schema)
