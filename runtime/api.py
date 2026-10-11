"""Versioned API dispatcher, injectable without importing bpy."""
from copy import deepcopy
import json
import time
import threading

from controller.ipc import MAX_FRAME_BYTES
from .capability_registry import CapabilityRegistry, ToolSpec
from .errors import ToolError
from .identity import ObjectIdentity
from .objects import ObjectControl
from .mesh import MeshControl
from .validation import ValidationService, MAX_VALIDATION_ELEMENTS, MAX_ASSEMBLY_CHECKS
from .logging import EventLogger
from .revisions import RuntimeState
from .selection import (SelectionService, QUERY_SCHEMA, HANDLE_SCHEMA, QUERY_OUTPUT,
                        INSPECT_OUTPUT, MAX_HANDLES, MAX_MESH_ELEMENTS, MAX_SELECTION_INDICES)
from .scene import (SceneObserver, LIST_INPUT_SCHEMA, LIST_OUTPUT_SCHEMA, SUMMARY_OUTPUT_SCHEMA,
                    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PAGE_INPUT_SCHEMA, HIERARCHY_OUTPUT_SCHEMA,
                    INSPECT_INPUT_SCHEMA, INSPECT_OUTPUT_SCHEMA)
from .schemas import (API_VERSION, RUNTIME_VERSION, SUPPORTED_VERSIONS, ToolRequest,
                      failure_response, object_schema, success_response, MutationResult)

CONVENTIONS = {'up': '+Z', 'forward': '-Y', 'ground_plane': 'XY',
               'length_units': ['mm', 'cm', 'm'], 'internal_length_unit': 'm',
               'angle_unit': 'degrees', 'rotation_order': 'XYZ',
               'dimensions': 'evaluated_world_space'}
FEATURES = {'capability_discovery': True, 'typed_contracts': True,
            'structured_errors': True, 'synchronous_execution': True,
            'scene_mutation': False, 'sessions': True, 'revisions': True,
            'transactions': False, 'semantic_selection': False, 'selection_handles': False,
            'validation': False, 'object_identity': False, 'scene_observation': False, 'evaluated_geometry': False}
LIMITS = {'max_frame_bytes': MAX_FRAME_BYTES, 'max_in_flight_requests': 1,
          'execution_mode': 'headless', 'transport': 'loopback_tcp',
          'default_page_size': DEFAULT_PAGE_SIZE, 'max_page_size': MAX_PAGE_SIZE,
          'max_selection_handles': MAX_HANDLES, 'max_mesh_query_elements': MAX_MESH_ELEMENTS,
          'max_selection_indices': MAX_SELECTION_INDICES,
          'max_validation_elements': MAX_VALIDATION_ELEMENTS, 'max_assembly_checks': MAX_ASSEMBLY_CHECKS}

STRING = {'type': 'string'}
STRING_ARRAY = {'type': 'array', 'items': STRING}
DESCRIPTOR_SCHEMA = object_schema({
    'name': STRING, 'version': STRING, 'description': STRING,
    'input_schema': {'type': 'object'}, 'output_schema': {'type': 'object'},
    'supports': {'type': 'object', 'additionalProperties': {'type': 'boolean'}},
    'side_effects': STRING_ARRAY, 'transaction_safe': {'type': 'boolean'}},
    ('name', 'version', 'description', 'input_schema', 'output_schema',
     'supports', 'side_effects', 'transaction_safe'))


def record_schema(values):
    properties = {name: {'type': ('boolean' if type(value) is bool else
                                  'integer' if type(value) is int else
                                  'array' if isinstance(value, list) else 'string')}
                  for name, value in values.items()}
    for rule in properties.values():
        if rule['type'] == 'array':
            rule['items'] = STRING
    return object_schema(properties, tuple(properties))


OUTPUT_SCHEMAS = {
    'runtime.get_version': object_schema(
        {name: STRING for name in ('runtime_version', 'api_version', 'blender_version')},
        ('runtime_version', 'api_version', 'blender_version')),
    'runtime.get_supported_versions': object_schema({'versions': STRING_ARRAY}, ('versions',)),
    'runtime.list_tools': object_schema({'tools': STRING_ARRAY}, ('tools',)),
    'runtime.describe_tool': DESCRIPTOR_SCHEMA,
    'runtime.get_supported_features': record_schema(FEATURES),
    'runtime.get_limits': record_schema(LIMITS),
    'runtime.describe_capabilities': object_schema({
        'api_version': STRING, 'tools': {'type': 'array', 'items': DESCRIPTOR_SCHEMA},
        'features': record_schema(FEATURES), 'limits': record_schema(LIMITS),
        'conventions': record_schema(CONVENTIONS)},
        ('api_version', 'tools', 'features', 'limits', 'conventions')),
}


class RuntimeAPI:
    def __init__(self, *, blender_version, logger=None, objects=None, scene=None, view_layer=None, depsgraph=None,
                 object_control=False):
        self.blender_version = blender_version
        self.logger = logger if logger is not None else EventLogger()
        self.state = RuntimeState()
        self._lock = threading.RLock()
        self.identities = ObjectIdentity(objects) if objects is not None else None
        # Bootstrap is part of the initial scene baseline, before state is published.
        if self.identities is not None:
            self.identities.ensure_all()
        if scene is not None and self.identities is None:
            raise ValueError('Scene observation requires an object provider')
        self.observer = (SceneObserver(scene=scene, view_layer=view_layer, identities=self.identities,
                                       state=self.state, depsgraph=depsgraph) if scene is not None else None)
        self.selections = (SelectionService(identities=self.identities, state=self.state,
                                           scene=scene, view_layer=view_layer) if scene is not None else None)
        self.features = {**FEATURES, 'object_identity': self.identities is not None,
                         'scene_observation': self.observer is not None,
                         'evaluated_geometry': self.observer is not None and depsgraph is not None,
                         'semantic_selection': self.selections is not None,
                         'selection_handles': self.selections is not None}
        self.registry = CapabilityRegistry()
        self._register_tools()
        if self.observer is not None and depsgraph is not None:
            self.validation = ValidationService(identities=self.identities, scene=scene,
                depsgraph=depsgraph)
            self.validation.register(self.registry)
            self.features['validation'] = True
        if object_control:
            if self.identities is None or scene is None or view_layer is None:
                raise ValueError('Object control requires live Blender providers')
            self.objects = ObjectControl(identities=self.identities, scene=scene, view_layer=view_layer)
            self.objects.register(self.registry)
            self.mesh = MeshControl(objects=self.objects, selections=self.selections, depsgraph=depsgraph)
            self.mesh.register(self.registry)
            self.features['scene_mutation'] = True

    def _register_tools(self):
        tools = [
            ('runtime.get_version', 'Get runtime, API and Blender versions.',
             lambda args: {'runtime_version': RUNTIME_VERSION, 'api_version': API_VERSION,
                           'blender_version': self.blender_version}),
            ('runtime.get_supported_versions', 'List supported API versions.',
             lambda args: {'versions': list(SUPPORTED_VERSIONS)}),
            ('runtime.list_tools', 'List available public tool names.',
             lambda args: {'tools': self.registry.names()}),
            ('runtime.describe_tool', 'Describe one tool and its typed arguments.',
             lambda args: self.registry.describe(args['name'])),
            ('runtime.get_supported_features', 'Report implemented and unavailable features.',
             lambda args: dict(self.features)),
            ('runtime.get_limits', 'Report transport and execution limits.',
             lambda args: dict(LIMITS)),
            ('runtime.describe_capabilities', 'Describe available tools, conventions and limits.',
             lambda args: {'api_version': API_VERSION,
                           'tools': [self.registry.describe(name) for name in self.registry.names()],
                           'features': dict(self.features), 'limits': dict(LIMITS),
                           'conventions': deepcopy(CONVENTIONS)}),
        ]
        for name, description, handler in tools:
            schema = (object_schema({'name': {'type': 'string', 'minLength': 1}}, ('name',))
                      if name == 'runtime.describe_tool' else object_schema())
            self.registry.register(ToolSpec(name, description, input_schema=schema,
                                            output_schema=OUTPUT_SCHEMAS[name]), handler)

        if self.observer is not None:
            self.registry.register(ToolSpec('scene.summary', 'Summarize the active scene.',
                                            output_schema=SUMMARY_OUTPUT_SCHEMA), self.observer.summary)
            self.registry.register(ToolSpec('scene.list_objects', 'List filtered objects in bounded pages.',
                                            input_schema=LIST_INPUT_SCHEMA, output_schema=LIST_OUTPUT_SCHEMA),
                                   self.observer.list_objects)
            self.registry.register(ToolSpec('scene.get_hierarchy', 'List parent relationships in bounded pages.',
                                            input_schema=PAGE_INPUT_SCHEMA, output_schema=HIERARCHY_OUTPUT_SCHEMA),
                                   self.observer.hierarchy)
            if self.features['evaluated_geometry']:
                self.registry.register(ToolSpec('scene.inspect_objects', 'Inspect selected UUIDs and evaluated geometry.',
                                                input_schema=INSPECT_INPUT_SCHEMA, output_schema=INSPECT_OUTPUT_SCHEMA),
                                       self.observer.inspect_objects)

        if self.selections is not None:
            self.registry.register(ToolSpec('mesh.query', 'Query base mesh elements and create a revision-bound selection handle.',
                                            input_schema=QUERY_SCHEMA, output_schema=QUERY_OUTPUT,
                                            supports={'semantic_selection': True, 'transactions': False}),
                                   self.selections.query)
            self.registry.register(ToolSpec('mesh.inspect_selection', 'Resolve a current selection handle to bounded base-mesh indices.',
                                            input_schema=HANDLE_SCHEMA, output_schema=INSPECT_OUTPUT),
                                   self.selections.inspect)

    def execute(self, message, *, request_id=None):
        with self._lock:
            return self._execute(message, request_id=request_id)

    def _execute(self, message, *, request_id):
        started = time.monotonic()
        revision_before = self.state.revision
        request = None
        error = None
        try:
            request = ToolRequest.parse(message)
            self.state.check(request.session_id, request.expected_revision)
            result = self.registry.invoke(request.tool, request.arguments,
                                          before_mutation=self.state.advance)
            encoded = json.dumps(result, allow_nan=False, separators=(',', ':')).encode('utf-8')
            if len(encoded) > MAX_FRAME_BYTES - 4096:
                raise ToolError('RESPONSE_TOO_LARGE', 'Result exceeds the transport budget; request a smaller page.')
        except ToolError as exc:
            error = exc
        except Exception:
            error = ToolError('INTERNAL_ERROR', 'Tool execution failed.')
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        response = (failure_response(error, self.state.session_id, self.state.revision) if error else
                    success_response(result, duration_ms, self.state.session_id,
                                     revision_before, self.state.revision))
        if error is None and isinstance(result, MutationResult):
            for field in ('created_ids', 'modified_ids', 'deleted_ids'):
                response[field] = getattr(result, field)
        # Only validated identifiers enter logs; malformed payloads are never recorded.
        self.logger.tool_call(request_id=request_id, tool=request.tool if request else None,
                              api_version=request.api_version if request else None,
                              success=response['success'], error_code=error.code if error else None,
                              duration_ms=duration_ms)
        return response
