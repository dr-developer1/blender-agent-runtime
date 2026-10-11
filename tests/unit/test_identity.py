import io
import unittest
import uuid
from unittest.mock import patch

from runtime.api import RuntimeAPI
from runtime.errors import ToolError
from runtime.identity import ObjectIdentity, UUID_PROPERTY, validate_uuid
from runtime.logging import EventLogger


class Object(dict):
    is_editable = True


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.objects = [Object(), Object()]
        self.identity = ObjectIdentity(lambda: self.objects)

    def assert_code(self, code, action):
        with self.assertRaises(ToolError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def test_assigns_unique_ids_once_and_resolves_without_names(self):
        assigned = self.identity.ensure_all()
        self.assertEqual(len(assigned), 2)
        self.assertEqual(len(set(assigned)), 2)
        for obj, object_id in zip(self.objects, assigned):
            self.assertEqual(validate_uuid(object_id), object_id)
            obj['name'] = 'Renamed label'
            self.assertIs(self.identity.resolve(object_id), obj)
            self.assertEqual(self.identity.ensure(obj), object_id)
        self.assertEqual(self.identity.ensure_all(), [])

    def test_unmanaged_and_removed_objects(self):
        missing = str(uuid.uuid4())
        self.assert_code('OBJECT_NOT_FOUND', lambda: self.identity.resolve(missing))
        self.assert_code('OBJECT_NOT_FOUND', lambda: self.identity.ensure(Object()))
        obj = self.objects[0]
        object_id = self.identity.ensure(obj)
        self.objects.pop(0)
        self.assert_code('OBJECT_NOT_FOUND', lambda: self.identity.resolve(object_id))
        self.assert_code('OBJECT_NOT_FOUND', lambda: self.identity.ensure(obj))
        self.objects.insert(0, Object({UUID_PROPERTY: object_id}))
        self.assertIs(self.identity.resolve(object_id), self.objects[0])

    def test_collision_rejects_resolution_and_bootstrap_without_assigning(self):
        object_id = str(uuid.uuid4())
        for obj in self.objects:
            obj[UUID_PROPERTY] = object_id
        missing = Object()
        self.objects.append(missing)
        self.assert_code('UUID_COLLISION', lambda: self.identity.resolve(object_id))
        self.assert_code('UUID_COLLISION', self.identity.ensure_all)
        self.assertNotIn(UUID_PROPERTY, missing)

    def test_known_duplicate_gets_fresh_id_preserving_source(self):
        source = self.objects[0]
        source_id = self.identity.ensure(source)
        duplicate = Object(source)
        self.objects.append(duplicate)
        self.assert_code('UUID_COLLISION', lambda: self.identity.resolve(source_id))
        duplicate_id = self.identity.assign_duplicate(source, duplicate)
        self.assertNotEqual(duplicate_id, source_id)
        self.assertIs(self.identity.resolve(source_id), source)
        self.assertIs(self.identity.resolve(duplicate_id), duplicate)
        self.assertEqual(self.identity.assign_duplicate(source, duplicate), duplicate_id)
        self.assert_code('INVALID_ARGUMENT', lambda: self.identity.assign_duplicate(source, source))

    def test_missing_duplicate_id_and_unmanaged_source(self):
        self.assert_code('OBJECT_NOT_MANAGED',
                         lambda: self.identity.assign_duplicate(*self.objects))
        source_id = self.identity.ensure(self.objects[0])
        other_id = self.identity.assign_duplicate(*self.objects)
        self.assertNotEqual(source_id, other_id)

    def test_duplicate_does_not_repair_unrelated_collisions(self):
        self.identity.ensure_all()
        source, other = self.objects
        duplicate = Object(other)
        self.objects.append(duplicate)
        self.assert_code('UUID_COLLISION', lambda: self.identity.assign_duplicate(source, duplicate))
        self.assertEqual(duplicate[UUID_PROPERTY], other[UUID_PROPERTY])
        self.objects.append(Object(source))
        self.assert_code('UUID_COLLISION', lambda: self.identity.assign_duplicate(source, duplicate))

    def test_rejects_malformed_stored_and_input_uuids(self):
        for value in (None, 3, '', 'Cube', '0' * 32, str(uuid.uuid4()).upper(), uuid.uuid4().hex):
            with self.subTest(value=value):
                self.assert_code('INVALID_OBJECT_UUID', lambda: self.identity.resolve(value))
                self.objects[0][UUID_PROPERTY] = value
                self.assert_code('INVALID_OBJECT_UUID', self.identity.ensure_all)
        self.assertNotIn(UUID_PROPERTY, self.objects[1])

    def test_read_only_preflight_and_write_failure(self):
        self.objects[1].is_editable = False
        self.assert_code('OBJECT_IDENTITY_READ_ONLY', self.identity.ensure_all)
        self.assertTrue(all(UUID_PROPERTY not in obj for obj in self.objects))
        class BrokenObject(Object):
            def __setitem__(self, key, value):
                raise TypeError('Private details')
        self.objects = [BrokenObject()]
        self.assert_code('OBJECT_IDENTITY_WRITE_FAILED', self.identity.ensure_all)

    def test_generation_avoids_existing_uuid(self):
        existing = uuid.uuid4()
        fresh = uuid.uuid4()
        self.objects[0][UUID_PROPERTY] = str(existing)
        with patch('runtime.identity.uuid.uuid4', side_effect=[existing, fresh]):
            self.assertEqual(self.identity.ensure(self.objects[1]), str(fresh))

    def test_runtime_bootstrap_and_discovery_report_adapter(self):
        api = RuntimeAPI(blender_version='fixture', objects=lambda: self.objects,
                         logger=EventLogger(io.StringIO()))
        self.assertTrue(all(UUID_PROPERTY in obj for obj in self.objects))
        self.assertEqual(api.state.revision, 0)
        result = api.execute({'api_version': '1.0', 'session_id': api.state.session_id,
                              'expected_revision': 0, 'tool': 'runtime.get_supported_features',
                              'arguments': {}})
        self.assertTrue(result['result']['object_identity'])
        self.assertFalse(result['result']['scene_mutation'])
        self.assertEqual(result['revision_after'], 0)
        self.assertFalse(RuntimeAPI(blender_version='fixture').features['object_identity'])
