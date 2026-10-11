import itertools
import math
import unittest
from unittest.mock import patch

from runtime.api import RuntimeAPI
from runtime.capability_registry import CapabilityRegistry
from runtime.errors import ToolError
from runtime.observation import (frame_camera, VIEWS, ObservationService, MAX_RENDER_BYTES,
                                 RENDER_OUTPUT, CAMERA_OUTPUT)
from runtime.schemas import validate_arguments


class CameraTests(unittest.TestCase):
    def test_all_aabb_corners_fit_rectangular_and_perspective_views(self):
        bounds = {'min': [-17, -2, 30], 'max': [9, 11, 31]}
        for width, height in ((384,384), (32,768), (768,32)):
            for view in VIEWS:
                c = frame_camera(bounds, view, width, height)
                validate_arguments(c, CAMERA_OUTPUT['properties']['camera'])
                matrix = c['world_matrix']
                right, up, out = ([matrix[i][j] for i in range(3)] for j in range(3))
                for point in itertools.product(*zip(bounds['min'], bounds['max'])):
                    p = [a-b for a,b in zip(point, c['location'])]
                    x,y,z = (sum(a*b for a,b in zip(p, axis)) for axis in (right,up,out))
                    depth = -z
                    self.assertGreater(depth, c['clip_start'])
                    self.assertLess(depth, c['clip_end'])
                    if c['projection'] == 'ORTHO':
                        self.assertLess(abs(x), c['ortho_scale']/2)
                        self.assertLess(abs(y), c['ortho_scale']/2*height/width)
                    else:
                        self.assertLess(abs(x)/depth, 36/100)
                        self.assertLess(abs(y)/depth, 36/100*height/width)
                self.assertEqual(c, frame_camera(bounds,view,width,height))

    def test_canonical_orientation_and_degenerate_bounds(self):
        bounds = {'min': [0,0,0], 'max': [0,0,0]}
        for view in VIEWS:
            camera = frame_camera(bounds,view)
            self.assertGreater(camera['clip_start'],0)
            self.assertGreater(camera['clip_end'],camera['clip_start'])
            self.assertGreater(camera['ortho_scale'],0)
        c = frame_camera(bounds,'front')['world_matrix']
        self.assertEqual([c[i][0] for i in range(3)], [1,0,0])
        self.assertEqual([c[i][1] for i in range(3)], [0,0,1])
        c = frame_camera(bounds,'top')['world_matrix']
        self.assertEqual([c[i][1] for i in range(3)], [0,1,0])

    def test_invalid_bounds_fail_with_json_safe_error(self):
        for bounds in ({'min':[math.nan,0,0],'max':[1,1,1]},
                       {'min':[2,0,0],'max':[1,1,1]},
                       {'min':[0,0,0],'max':[1e7,1,1]}):
            with self.assertRaises(ToolError) as error:
                frame_camera(bounds,'front')
            self.assertEqual(error.exception.code,'INVALID_GEOMETRY')


class ObservationContractTests(unittest.TestCase):
    def setUp(self):
        self.api = RuntimeAPI(blender_version='fake')
        self.service = ObservationService(identities=None, scene=None, view_layer=None, depsgraph=None)
        self.service.register(self.api.registry)

    def call(self, name, args):
        return self.api.execute({'api_version':'1.0', 'session_id':self.api.state.session_id,
            'expected_revision':self.api.state.revision, 'tool':name, 'arguments':args})

    def test_schema_and_semantic_failures_do_not_consume_revision(self):
        cases = [('observe.render', {'width':True}), ('observe.render',{'height':769}),
            ('observe.render',{'view':'unknown'}), ('observe.render',{'output_path':'/tmp/x'}),
            ('observe.render',{'engine':'CYCLES'}), ('observe.render',{'padding':1}),
            ('observe.render',{'engine':'EEVEE','mode':'wireframe'}),
            ('observe.render_multiview',{'views':['front','front']}),
            ('observe.render_multiview',{'views':[]})]
        for name,args in cases:
            with self.subTest(args=args):
                result = self.call(name,args)
                self.assertEqual(result['error']['code'],'INVALID_ARGUMENT')
                self.assertEqual(result['revision'],0)
        result = self.call('observe.render_multiview', {'width':768,'height':768})
        self.assertEqual(result['error']['code'],'OBSERVATION_LIMIT_EXCEEDED')
        self.assertEqual(result['revision'],0)

    def test_available_tools_are_read_only_and_transaction_safe(self):
        for name in self.api.registry.names():
            if name.startswith('observe.'):
                spec = self.api.registry.describe(name)
                self.assertEqual(spec['side_effects'],[])
                self.assertTrue(spec['transaction_safe'])
                self.assertTrue(spec['supports']['transactions'])
        with self.assertRaises(ValueError):
            RuntimeAPI(blender_version='fake',observation=True)
        self.assertFalse(self.call('runtime.get_supported_features',{})['result']['diagnostic_rendering'])

    def test_render_failure_is_structured_and_redacted(self):
        base = {'object_ids':[], 'bounds':{'min':[0,0,0],'max':[1,1,1]},
                'geometry_source':'evaluated_viewport_mesh'}
        with patch.object(self.service, '_targets', return_value=(None,[],base)), \
                patch.object(self.service, '_render_blender', side_effect=RuntimeError('private data')):
            result = self.call('observe.render',{})
        self.assertEqual(result['error']['code'],'RENDER_FAILED')
        self.assertNotIn('private data',str(result))
        self.assertEqual(result['revision'],0)

    def test_combined_png_budget_fits_transport_with_base64(self):
        from controller.ipc import MAX_FRAME_BYTES
        self.assertLess(4*((MAX_RENDER_BYTES+2)//3) + 32_000, MAX_FRAME_BYTES)
