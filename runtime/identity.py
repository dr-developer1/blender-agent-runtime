"""Persistent object identity; callers must run on Blender's main thread.

No object-reference cache survives deletion or file loading. After bootstrap,
identity writes belong inside a revision-advancing runtime mutation handler.
"""
import uuid

from .errors import ToolError

UUID_PROPERTY = 'bar_uuid'


def validate_uuid(value):
    if not isinstance(value, str):
        raise ToolError('INVALID_OBJECT_UUID', 'Object UUID must be a canonical UUID string.')
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise ToolError('INVALID_OBJECT_UUID', 'Object UUID must be a canonical UUID string.') from None
    if str(parsed) != value or parsed.int == 0:
        raise ToolError('INVALID_OBJECT_UUID', 'Object UUID must be a canonical nonzero UUID string.')
    return value


def object_key(obj):
    # Pointers are only compared within one scan, never used as persistent identity.
    pointer = getattr(obj, 'as_pointer', None)
    return pointer() if pointer is not None else id(obj)


class ObjectIdentity:
    def __init__(self, objects):
        """objects is a callable returning the current live object collection."""
        self._objects = objects

    def _snapshot(self):
        return list(self._objects())

    def _index(self, objects):
        index = {}
        for obj in objects:
            if UUID_PROPERTY not in obj:
                continue
            object_id = validate_uuid(obj[UUID_PROPERTY])
            if object_id in index:
                raise ToolError('UUID_COLLISION', 'Multiple objects have the same UUID.',
                                {'object_id': object_id})
            index[object_id] = obj
        return index

    def _require_live(self, obj, objects):
        try:
            key = object_key(obj)
        except ReferenceError:
            raise ToolError('OBJECT_NOT_FOUND', 'Object is no longer present.') from None
        if not any(object_key(candidate) == key for candidate in objects):
            raise ToolError('OBJECT_NOT_FOUND', 'Object is no longer present.')

    def _require_writable(self, obj):
        if not getattr(obj, 'is_editable', True):
            raise ToolError('OBJECT_IDENTITY_READ_ONLY', 'Cannot assign identity to a read-only object.')

    def _fresh_uuid(self, index):
        while True:
            value = str(uuid.uuid4())
            if value not in index:
                return value

    def _write(self, obj, object_id):
        try:
            obj[UUID_PROPERTY] = object_id
        except (TypeError, RuntimeError, AttributeError) as exc:
            raise ToolError('OBJECT_IDENTITY_WRITE_FAILED', 'Could not store object identity.') from exc

    def ensure_all(self):
        """Manage missing IDs, preserving valid IDs; preflight collisions first."""
        objects = self._snapshot()
        index = self._index(objects)
        missing = [obj for obj in objects if UUID_PROPERTY not in obj]
        for obj in missing:
            self._require_writable(obj)
        assigned = []
        for obj in missing:
            object_id = self._fresh_uuid(index)
            self._write(obj, object_id)
            index[object_id] = obj
            assigned.append(object_id)
        return assigned

    def ensure(self, obj):
        """Assign one live object a UUID, or return its existing unique UUID."""
        objects = self._snapshot()
        self._require_live(obj, objects)
        index = self._index(objects)
        if UUID_PROPERTY in obj:
            return obj[UUID_PROPERTY]
        self._require_writable(obj)
        object_id = self._fresh_uuid(index)
        self._write(obj, object_id)
        return object_id

    def index(self):
        """Return a validated current UUID index; callers must not retain it."""
        return self._index(self._snapshot())

    def resolve(self, object_id):
        """Resolve exactly one current object; never use its display name."""
        validate_uuid(object_id)
        index = self.index()
        if object_id not in index:
            raise ToolError('OBJECT_NOT_FOUND', 'No current object has this UUID.',
                            {'object_id': object_id})
        return index[object_id]

    def assign_duplicate(self, source, duplicate):
        """Repair a known copy, preserving source identity and unique managed copies.

        Unknown collisions cannot be repaired by guessing which object is original.
        """
        objects = self._snapshot()
        self._require_live(source, objects)
        self._require_live(duplicate, objects)
        if object_key(source) == object_key(duplicate):
            raise ToolError('INVALID_ARGUMENT', 'Source and duplicate must be different objects.')
        index = self._index([obj for obj in objects if object_key(obj) != object_key(duplicate)])
        if UUID_PROPERTY not in source:
            raise ToolError('OBJECT_NOT_MANAGED', 'Source object does not have an identity.')
        source_id = source[UUID_PROPERTY]
        if UUID_PROPERTY in duplicate:
            duplicate_id = validate_uuid(duplicate[UUID_PROPERTY])
            if duplicate_id != source_id:
                if duplicate_id in index:
                    raise ToolError('UUID_COLLISION', 'Duplicate UUID belongs to another object.',
                                    {'object_id': duplicate_id})
                return duplicate_id
        self._require_writable(duplicate)
        object_id = self._fresh_uuid(index)
        self._write(duplicate, object_id)
        return object_id
