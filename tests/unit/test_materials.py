import unittest
from unittest.mock import Mock

from runtime.api import RuntimeAPI
from runtime.capability_registry import CapabilityRegistry
from runtime.errors import ToolError
from runtime.materials import MaterialControl
from runtime.schemas import validate_arguments


class MaterialContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry()
        MaterialControl(objects=Mock()).register(self.registry)

    def test_backend_disabled_without_object_control(self):
        api = RuntimeAPI(blender_version='test')
        self.assertFalse(api.features['basic_materials'])
        self.assertNotIn('material.create', api.registry.names())

    def test_discovery_declares_mutations_and_typed_results(self):
        for name in self.registry.names():
            spec = self.registry.describe(name)
            self.assertTrue(spec['side_effects'])
            self.assertTrue(spec['output_schema']['required'])
            self.assertFalse(spec['transaction_safe'])
        self.registry.enable_transactions(self.registry.names())
        self.assertTrue(self.registry.describe('material.assign')['transaction_safe'])

    def test_invalid_parameters_reject_before_mutation(self):
        advance = Mock()
        for tool, args in [('material.create', {'roughness': 1.1}),
                           ('material.create', {'metallic': True}),
                           ('material.create', {'base_color': [0, 0, 0]}),
                           ('material.assign', {'object_id': 'x'}),
                           ('material.assign', {'object_id': 'x', 'material_id': 'y', 'slot': 0})]:
            with self.assertRaises(ToolError):
                self.registry.invoke(tool, args, before_mutation=advance)
        advance.assert_not_called()

    def test_valid_boundary_parameters(self):
        schema = self.registry.describe('material.create')['input_schema']
        for args in ({}, {'base_color': [0, 1, 0, 1], 'roughness': 0, 'metallic': 1}):
            validate_arguments(args, schema)
