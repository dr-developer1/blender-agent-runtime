import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.errors import ToolError
from runtime.revisions import RuntimeState
from runtime.selection import MeshSnapshot, SelectionService, MAX_HANDLES, QUERY_SCHEMA
from runtime.schemas import validate_arguments, validate_schema


def cube():
    return MeshSnapshot(
        [(-1,-1,-1), (1,-1,-1), (1,1,-1), (-1,1,-1),
         (-1,-1,1), (1,-1,1), (1,1,1), (-1,1,1)],
        [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]],
        [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]])


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.mesh = cube()

    def match(self, element, kind, **parameters):
        return self.mesh.match(element, {'kind': kind, **parameters})

    def test_spatial_extremes(self):
        self.assertEqual(self.match('EDGE', 'top'), {4,5,6,7})
        self.assertEqual(self.match('FACE', 'top'), {1})
        self.assertEqual(self.match('VERTEX', 'front'), {0,1,4,5})
        self.assertEqual(self.match('VERTEX', 'right'), {1,2,5,6})
        self.assertEqual(self.match('FACE', 'bottom'), {0})
        self.assertEqual(self.match('FACE', 'left'), {5})
        self.assertEqual(self.match('FACE', 'back'), {4})

    def test_spatial_ranges_and_nearest_ties(self):
        self.assertEqual(self.match('EDGE', 'height_range', minimum=.5, maximum=1), {4,5,6,7})
        self.assertEqual(self.match('FACE', 'within_bbox', min=[-1,-1,1], max=[1,1,1]), {1})
        self.assertEqual(self.match('FACE', 'nearest_point', point=[0,0,5]), {1})
        self.assertEqual(self.match('VERTEX', 'nearest_point', point=[0,0,0]), set(range(8)))

    def test_geometric_and_semantic(self):
        self.assertEqual(self.match('FACE', 'normal_direction', direction=[0,0,10], angle_degrees=0), {1})
        self.assertEqual(self.match('FACE', 'cap_faces'), {0,1})
        self.assertEqual(self.match('FACE', 'side_faces'), {2,3,4,5})
        self.assertEqual(self.match('EDGE', 'length_range', minimum=2, maximum=2), set(range(12)))
        self.assertEqual(self.match('FACE', 'area_range', minimum=4, maximum=4), set(range(6)))
        self.assertEqual(self.match('EDGE', 'dihedral_angle', minimum=40, maximum=180), set(range(12)))

    def test_topology_closed_open_loose_and_disconnected(self):
        self.assertEqual(self.match('EDGE', 'manifold'), set(range(12)))
        self.assertEqual(self.match('EDGE', 'boundary'), set())
        self.assertEqual(self.match('FACE', 'connected_to', seed_index=0), set(range(6)))
        self.mesh = MeshSnapshot([(0,0,0),(1,0,0),(0,1,0),(4,0,0),(5,0,0)],
                                 [[0,1],[1,2],[2,0],[3,4]], [[0,1,2]])
        self.assertEqual(self.match('EDGE', 'boundary'), {0,1,2})
        self.assertEqual(self.match('EDGE', 'outer_boundary'), {0,1,2})
        self.assertEqual(self.match('EDGE', 'non_manifold'), {0,1,2,3})
        self.assertEqual(self.match('VERTEX', 'connected_to', seed_index=0), {0,1,2})
        self.assertEqual(self.match('EDGE', 'connected_to', seed_index=3), {3})

    def test_invalid_selector_combinations(self):
        cases = [('EDGE', 'area_range', {'minimum':0, 'maximum':1}),
                 ('FACE', 'top', {'point':[0,0,0]}),
                 ('VERTEX', 'within_bbox', {'min':[2,0,0], 'max':[1,0,0]}),
                 ('FACE', 'normal_direction', {'direction':[0,0,0]}),
                 ('EDGE', 'length_range', {'minimum':2, 'maximum':1}),
                 ('FACE', 'connected_to', {'seed_index':6}),
                 ('FACE', 'height_range', {'minimum':0})]
        for element, kind, parameters in cases:
            with self.subTest(kind=kind), self.assertRaises(ToolError) as ctx:
                self.match(element, kind, **parameters)
            self.assertEqual(ctx.exception.code, 'INVALID_ARGUMENT')

    def test_empty_and_degenerate_geometry(self):
        self.mesh = MeshSnapshot([], [], [])
        self.assertEqual(self.match('FACE', 'top'), set())
        self.assertEqual(self.match('VERTEX', 'nearest_point', point=[0,0,0]), set())
        self.mesh = MeshSnapshot([(0,0,0)]*3, [[0,1],[1,2],[2,0]], [[0,1,2]])
        self.assertEqual(self.match('FACE', 'normal_direction', direction=[0,0,1]), set())

    def service(self):
        obj = SimpleNamespace(type='MESH')
        return SelectionService(identities=SimpleNamespace(resolve=lambda key: obj), state=RuntimeState(),
                                scene=lambda: SimpleNamespace(objects=[obj]), snapshot=lambda obj, space: self.mesh)

    def test_handle_resolution_intersection_and_revision_expiry(self):
        service = self.service()
        result = service.query({'object_id':'uuid', 'element_type':'EDGE',
                                'selectors':[{'kind':'top'}, {'kind':'length_range','minimum':2,'maximum':2}]})
        self.assertEqual(result['matched_count'], 4)
        token = result['selection_handle']
        self.assertEqual(service.resolve(token)['indices'], [4,5,6,7])
        service.resolve(token)['indices'].clear()
        self.assertEqual(len(service.resolve(token)['indices']), 4)
        service.state.advance()
        with self.assertRaises(ToolError) as ctx:
            service.resolve(token)
        self.assertEqual(ctx.exception.code, 'INVALID_SELECTION_HANDLE')
        self.assertEqual(len(service._handles), 0)

    def test_untracked_geometry_changes_and_other_runtime(self):
        service = self.service()
        token = service.query({'object_id':'uuid','element_type':'FACE','selectors':[{'kind':'top'}]})['selection_handle']
        with self.assertRaises(ToolError):
            self.service().resolve(token)
        self.mesh = MeshSnapshot([(0,0,0)], [], [])
        with self.assertRaises(ToolError) as ctx:
            service.resolve(token)
        self.assertEqual(ctx.exception.code, 'STALE_SELECTION')

    def test_handle_budget_evicts_oldest(self):
        service = self.service()
        tokens = [service.query({'object_id':'uuid','element_type':'FACE','selectors':[{'kind':'top'}]})['selection_handle']
                  for _ in range(MAX_HANDLES+1)]
        self.assertEqual(len(service._handles), MAX_HANDLES)
        with self.assertRaises(ToolError):
            service.resolve(tokens[0])
        self.assertEqual(service.resolve(tokens[-1])['matched_count'], 1)

    def test_schema_rejects_nonfinite_wrong_fields_and_unbounded_selectors(self):
        validate_schema(QUERY_SCHEMA)
        args = {'object_id':'uuid','element_type':'FACE','selectors':[{'kind':'top'}]}
        for invalid in ({**args, 'element_type':'POLYGON'}, {**args, 'selectors':[]},
                        {**args, 'selectors':[{'kind':'top', 'tolerance':float('nan')}]},
                        {**args, 'selectors':[{'kind':'connected_to','seed_index':True}]},
                        {**args, 'geometry':'EVALUATED'}):
            with self.assertRaises(ToolError):
                validate_arguments(invalid, QUERY_SCHEMA)

    def test_selection_and_mesh_budgets_reject_without_partial_handles(self):
        service = self.service()
        with patch('runtime.selection.MAX_SELECTION_INDICES', 3), self.assertRaises(ToolError) as ctx:
            service.query({'object_id':'uuid', 'element_type':'EDGE', 'selectors':[{'kind':'top'}]})
        self.assertEqual(ctx.exception.code, 'SELECTION_LIMIT_EXCEEDED')
        self.assertEqual(len(service._handles), 0)
        mesh = SimpleNamespace(is_editmode=False, vertices=range(10), edges=[], polygons=[], loops=[])
        with patch('runtime.selection.MAX_MESH_ELEMENTS', 9), self.assertRaises(ToolError) as ctx:
            service._blender_snapshot(SimpleNamespace(data=mesh), 'WORLD')
        self.assertEqual(ctx.exception.code, 'SELECTION_LIMIT_EXCEEDED')
