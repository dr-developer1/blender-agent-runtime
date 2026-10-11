"""Typed API 1.0 foundation contracts with strict boundary validation."""
from dataclasses import dataclass
import math
from typing import Any, TypedDict

from .errors import ToolError

API_VERSION = '1.0'
SUPPORTED_VERSIONS = (API_VERSION,)
RUNTIME_VERSION = '0.13.0'


class MutationResult(dict):
    """Tool data plus explicit object changes for the public response envelope."""
    def __init__(self, result, *, created_ids=(), modified_ids=(), deleted_ids=()):
        super().__init__(result)
        self.created_ids = list(created_ids)
        self.modified_ids = list(modified_ids)
        self.deleted_ids = list(deleted_ids)


class ErrorBody(TypedDict):
    code: str
    message: str
    details: dict[str, Any]


class SuccessResponse(TypedDict):
    api_version: str
    success: bool
    session_id: str
    revision_before: int
    revision_after: int
    result: dict[str, Any]
    created_ids: list[str]
    modified_ids: list[str]
    deleted_ids: list[str]
    warnings: list[str]
    metrics: dict[str, Any]
    validation: None


class FailureResponse(TypedDict):
    api_version: str
    success: bool
    session_id: str
    revision: int
    error: ErrorBody


@dataclass(frozen=True)
class ToolRequest:
    api_version: str
    session_id: str
    expected_revision: int
    tool: str
    arguments: dict[str, Any]

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {'api_version', 'session_id', 'expected_revision', 'tool', 'arguments'}:
            raise ToolError('INVALID_REQUEST', 'Expected api_version, session_id, expected_revision, tool and arguments.')
        if (not isinstance(value['api_version'], str) or not value['api_version'] or
                not isinstance(value['tool'], str) or not value['tool'] or
                not isinstance(value['arguments'], dict) or
                not isinstance(value['session_id'], str) or not value['session_id'] or
                type(value['expected_revision']) is not int or value['expected_revision'] < 0):
            raise ToolError('INVALID_REQUEST', 'Invalid request field types or empty identifiers.')
        if value['api_version'] not in SUPPORTED_VERSIONS:
            raise ToolError('UNSUPPORTED_API_VERSION', 'Unsupported API version.',
                            {'supported_versions': list(SUPPORTED_VERSIONS)})
        return cls(**value)


def object_schema(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {},
            'required': list(required), 'additionalProperties': False}


def validate_schema(schema):
    """Validate only the JSON Schema subset that this runtime can enforce."""
    if not isinstance(schema, dict):
        raise ValueError('Unsupported argument schema')
    kind = schema.get('type')
    allowed = {'string': {'type', 'minLength', 'maxLength', 'enum'},
               'integer': {'type', 'minimum', 'maximum'},
               'number': {'type', 'minimum', 'maximum'},
               'boolean': {'type'},
               'array': {'type', 'items', 'minItems', 'maxItems'},
               'object': {'type', 'properties', 'required', 'additionalProperties'}}
    if not isinstance(kind, str) or kind not in allowed or set(schema) - allowed[kind]:
        raise ValueError('Unsupported argument schema')
    for key in ('minLength', 'maxLength', 'minItems', 'maxItems'):
        if key in schema and (type(schema[key]) is not int or schema[key] < 0):
            raise ValueError('Invalid schema bound')
    for key in ('minimum', 'maximum'):
        if key in schema and (type(schema[key]) not in (int, float) or (type(schema[key]) is float and not math.isfinite(schema[key]))):
            raise ValueError('Invalid schema bound')
    for low, high in (('minLength', 'maxLength'), ('minItems', 'maxItems'), ('minimum', 'maximum')):
        if low in schema and high in schema and schema[low] > schema[high]:
            raise ValueError('Invalid schema bounds')
    if 'enum' in schema and (not isinstance(schema['enum'], list) or not schema['enum'] or
                             any(not isinstance(item, str) for item in schema['enum'])):
        raise ValueError('Unsupported enum')
    if kind == 'array':
        validate_schema(schema.get('items'))
    if kind == 'object':
        if (set(schema) != allowed[kind] or not isinstance(schema['properties'], dict) or
                not isinstance(schema['required'], list) or
                any(not isinstance(key, str) for key in schema['required']) or
                not set(schema['required']) <= set(schema['properties']) or
                any(not isinstance(key, str) for key in schema['properties'])):
            raise ValueError('Unsupported object schema')
        for rule in schema['properties'].values():
            validate_schema(rule)
        additional = schema['additionalProperties']
        if type(additional) is not bool:
            validate_schema(additional)


def validate_arguments(arguments, schema, path='arguments'):
    """Enforce the registered schema before a handler may execute."""
    def invalid():
        raise ToolError('INVALID_ARGUMENT', 'Argument does not match its schema.', {'field': path})
    kind = schema['type']
    if kind == 'object':
        if not isinstance(arguments, dict) or any(not isinstance(key, str) for key in arguments):
            invalid()
        properties = schema['properties']
        unknown = set(arguments) - set(properties)
        missing = set(schema['required']) - set(arguments)
        additional = schema['additionalProperties']
        if missing or (unknown and additional is False):
            raise ToolError('INVALID_ARGUMENT', 'Unexpected or missing arguments.',
                            {'field': path, 'unknown': sorted(unknown), 'missing': sorted(missing)})
        for name, value in arguments.items():
            rule = properties.get(name, additional)
            if rule is not True:
                validate_arguments(value, rule, path + '.' + name)
    elif kind == 'string':
        if (not isinstance(arguments, str) or len(arguments) < schema.get('minLength', 0) or
                len(arguments) > schema.get('maxLength', float('inf')) or
                ('enum' in schema and arguments not in schema['enum'])):
            invalid()
    elif kind == 'boolean':
        if type(arguments) is not bool:
            invalid()
    elif kind in ('integer', 'number'):
        if (type(arguments) not in ((int,) if kind == 'integer' else (int, float)) or
                (type(arguments) is float and not math.isfinite(arguments)) or arguments < schema.get('minimum', -float('inf')) or
                arguments > schema.get('maximum', float('inf'))):
            invalid()
    elif kind == 'array':
        if (not isinstance(arguments, list) or len(arguments) < schema.get('minItems', 0) or
                len(arguments) > schema.get('maxItems', float('inf'))):
            invalid()
        for index, value in enumerate(arguments):
            validate_arguments(value, schema['items'], f'{path}[{index}]')


def success_response(result, duration_ms, session_id, revision_before, revision_after) -> SuccessResponse:
    return {'api_version': API_VERSION, 'success': True, 'result': result,
            'session_id': session_id, 'revision_before': revision_before, 'revision_after': revision_after,
            'created_ids': [], 'modified_ids': [], 'deleted_ids': [],
            'warnings': [], 'metrics': {'duration_ms': duration_ms}, 'validation': None}


def failure_response(error: ToolError, session_id, revision) -> FailureResponse:
    return {'api_version': API_VERSION, 'success': False, 'error': error.as_dict(),
            'session_id': session_id, 'revision': revision}


def validate_response(value):
    """Reject corrupt public response contracts before returning them to callers."""
    if not isinstance(value, dict) or value.get('api_version') != API_VERSION:
        raise ValueError('Invalid response API version')
    if type(value.get('success')) is not bool:
        raise ValueError('Invalid response success flag')
    if not isinstance(value.get('session_id'), str) or not value['session_id']:
        raise ValueError('Invalid response session')
    revision_keys = ('revision_before', 'revision_after') if value['success'] else ('revision',)
    if any(type(value.get(key)) is not int or value[key] < 0 for key in revision_keys):
        raise ValueError('Invalid response revision')
    if value['success']:
        if value['revision_after'] < value['revision_before']:
            raise ValueError('Response revision moved backward')
        expected = {'api_version', 'success', 'result', 'created_ids', 'modified_ids',
                    'deleted_ids', 'warnings', 'metrics', 'validation',
                    'session_id', 'revision_before', 'revision_after'}
        if (set(value) != expected or not isinstance(value['result'], dict) or
                not isinstance(value['metrics'], dict) or value['validation'] is not None):
            raise ValueError('Invalid success response')
        for key in ('created_ids', 'modified_ids', 'deleted_ids', 'warnings'):
            if not isinstance(value[key], list) or any(not isinstance(item, str) for item in value[key]):
                raise ValueError(f'Invalid response {key}')
        duration = value['metrics'].get('duration_ms')
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
            raise ValueError('Invalid response duration')
    else:
        error = value.get('error')
        if (set(value) != {'api_version', 'success', 'error', 'session_id', 'revision'} or not isinstance(error, dict) or
                set(error) != {'code', 'message', 'details'} or
                not isinstance(error['code'], str) or not error['code'] or
                not isinstance(error['message'], str) or not isinstance(error['details'], dict)):
            raise ValueError('Invalid error response')
