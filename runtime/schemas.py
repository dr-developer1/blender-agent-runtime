"""Typed API 1.0 foundation contracts with strict boundary validation."""
from dataclasses import dataclass
import math
from typing import Any, TypedDict

from .errors import ToolError

API_VERSION = '1.0'
SUPPORTED_VERSIONS = (API_VERSION,)
RUNTIME_VERSION = '0.4.0'


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


def validate_arguments(arguments, schema):
    """Validate the deliberately small object/string schema subset used by discovery."""
    if not isinstance(arguments, dict):
        raise ToolError('INVALID_ARGUMENT', 'Arguments must be an object.')
    properties = schema['properties']
    unknown = set(arguments) - set(properties)
    missing = set(schema['required']) - set(arguments)
    if unknown or missing:
        raise ToolError('INVALID_ARGUMENT', 'Unexpected or missing arguments.',
                        {'unknown': sorted(unknown), 'missing': sorted(missing)})
    for name, value in arguments.items():
        rule = properties[name]
        if not isinstance(value, str) or len(value) < rule.get('minLength', 0):
            raise ToolError('INVALID_ARGUMENT', f'{name} must be a nonempty string.', {'field': name})


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
