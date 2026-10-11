"""Read-only API foundation, injectable without importing bpy."""
from copy import deepcopy
import json
import time

from controller.ipc import MAX_FRAME_BYTES
from .capability_registry import CapabilityRegistry, ToolSpec
from .errors import ToolError
from .logging import EventLogger
from .schemas import (API_VERSION, RUNTIME_VERSION, SUPPORTED_VERSIONS, ToolRequest,
                      failure_response, object_schema, success_response)

CONVENTIONS = {'up': '+Z', 'forward': '-Y', 'ground_plane': 'XY',
               'length_units': ['mm', 'cm', 'm'], 'internal_length_unit': 'm',
               'angle_unit': 'degrees', 'rotation_order': 'XYZ',
               'dimensions': 'evaluated_world_space'}
FEATURES = {'capability_discovery': True, 'typed_contracts': True,
            'structured_errors': True, 'synchronous_execution': True,
            'scene_mutation': False, 'sessions': False, 'revisions': False,
            'transactions': False, 'semantic_selection': False}
LIMITS = {'max_frame_bytes': MAX_FRAME_BYTES, 'max_in_flight_requests': 1,
          'execution_mode': 'headless', 'transport': 'loopback_tcp'}

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
    def __init__(self, *, blender_version, logger=None):
        self.blender_version = blender_version
        self.logger = logger if logger is not None else EventLogger()
        self.registry = CapabilityRegistry()
        self._register_tools()

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
             lambda args: dict(FEATURES)),
            ('runtime.get_limits', 'Report transport and execution limits.',
             lambda args: dict(LIMITS)),
            ('runtime.describe_capabilities', 'Describe available tools, conventions and limits.',
             lambda args: {'api_version': API_VERSION,
                           'tools': [self.registry.describe(name) for name in self.registry.names()],
                           'features': dict(FEATURES), 'limits': dict(LIMITS),
                           'conventions': deepcopy(CONVENTIONS)}),
        ]
        for name, description, handler in tools:
            schema = (object_schema({'name': {'type': 'string', 'minLength': 1}}, ('name',))
                      if name == 'runtime.describe_tool' else object_schema())
            self.registry.register(ToolSpec(name, description, input_schema=schema,
                                            output_schema=OUTPUT_SCHEMAS[name]), handler)

    def execute(self, message, *, request_id=None):
        started = time.monotonic()
        request = None
        error = None
        try:
            request = ToolRequest.parse(message)
            result = self.registry.invoke(request.tool, request.arguments)
            json.dumps(result, allow_nan=False)
        except ToolError as exc:
            error = exc
        except Exception:
            error = ToolError('INTERNAL_ERROR', 'Tool execution failed.')
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        response = failure_response(error) if error else success_response(result, duration_ms)
        # Only validated identifiers enter logs; malformed payloads are never recorded.
        self.logger.tool_call(request_id=request_id, tool=request.tool if request else None,
                              api_version=request.api_version if request else None,
                              success=response['success'], error_code=error.code if error else None,
                              duration_ms=duration_ms)
        return response
