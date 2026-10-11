"""The same registry drives dispatch and introspection."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import ToolError
from .schemas import object_schema, validate_arguments


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    version: str = '1.0'
    input_schema: dict[str, Any] = field(default_factory=object_schema)
    output_schema: dict[str, Any] = field(default_factory=lambda: {'type': 'object'})
    supports: dict[str, bool] = field(default_factory=lambda: {'transactions': False})
    side_effects: tuple[str, ...] = ()
    transaction_safe: bool = False

    def describe(self):
        return deepcopy({'name': self.name, 'version': self.version,
                         'description': self.description, 'input_schema': self.input_schema,
                         'output_schema': self.output_schema, 'supports': self.supports,
                         'side_effects': list(self.side_effects),
                         'transaction_safe': self.transaction_safe})


class CapabilityRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[ToolSpec, Callable]] = {}

    def register(self, spec: ToolSpec, handler: Callable):
        if spec.name in self._tools:
            raise ValueError(f'Duplicate tool: {spec.name}')
        # Refuse schemas the boundary validator cannot enforce.
        schema = spec.input_schema
        if (schema.get('type') != 'object' or schema.get('additionalProperties') is not False or
                not isinstance(schema.get('properties'), dict) or
                not isinstance(schema.get('required'), list) or
                not set(schema['required']) <= set(schema['properties']) or
                any(rule.get('type') != 'string' or set(rule) - {'type', 'minLength'}
                    for rule in schema['properties'].values()) or
                set(schema) != {'type', 'properties', 'required', 'additionalProperties'}):
            raise ValueError('Unsupported argument schema')
        self._tools[spec.name] = (deepcopy(spec), handler)

    def names(self):
        return sorted(self._tools)

    def _resolve(self, name):
        try:
            return self._tools[name]
        except KeyError:
            raise ToolError('UNKNOWN_TOOL', 'Tool is not available.', {'name': name}) from None

    def describe(self, name):
        return self._resolve(name)[0].describe()

    def invoke(self, name, arguments, *, before_mutation=None):
        spec, handler = self._resolve(name)
        validate_arguments(arguments, spec.input_schema)
        if spec.side_effects and before_mutation is not None:
            before_mutation()
        result = handler(arguments)
        if not isinstance(result, dict):
            raise TypeError('Tool result must be an object')
        return result
