"""Deterministic object mutations on Blender's main thread, using the data API."""
import math

from .capability_registry import ToolSpec
from .errors import ToolError
from .identity import object_key
from .schemas import MutationResult, object_schema

ID = {'type': 'string', 'minLength': 1, 'maxLength': 64}
NAME = {'type': 'string', 'minLength': 1, 'maxLength': 63}
UNIT = {'type': 'string', 'enum': ['m', 'cm', 'mm']}

def vector(bound):
    return {'type': 'array', 'items': {'type': 'number', 'minimum': -bound, 'maximum': bound},
            'minItems': 3, 'maxItems': 3}

TRANSFORM = {'location': vector(1e9), 'rotation': vector(360000), 'scale': vector(1e6), 'unit': UNIT}
CREATE_SCHEMA = object_schema({**TRANSFORM, 'primitive': {'type': 'string', 'enum': ['CUBE', 'PLANE', 'CYLINDER', 'CONE']},
                               'size': {'type': 'number', 'minimum': 1e-9, 'maximum': 1e6},
                               'segments': {'type': 'integer', 'minimum': 3, 'maximum': 256}, 'name': NAME}, ('primitive',))
TRANSFORM_SCHEMA = object_schema({**TRANSFORM, 'object_id': ID}, ('object_id',))
DUPLICATE_SCHEMA = object_schema({'object_id': ID, 'name': NAME, 'linked_data': {'type': 'boolean'}}, ('object_id',))
DELETE_SCHEMA = object_schema({'object_id': ID}, ('object_id',))
PARENT_SCHEMA = object_schema({'object_id': ID, 'parent_id': ID, 'keep_world_transform': {'type': 'boolean'}}, ('object_id',))
OUTPUT_SCHEMA = object_schema({'object_id': ID}, ('object_id',))


def primitive_geometry(kind, size, segments):
    """Closed outward-wound solids; size is diameter/height or cube/plane side."""
    r = size / 2
    if kind in ('CUBE', 'PLANE'):
        vertices = [(-r, -r, -r), (r, -r, -r), (r, r, -r), (-r, r, -r)]
        if kind == 'PLANE':
            return [(x, y, 0) for x, y, z in vertices], [(0, 1, 2, 3)]
        vertices += [(x, y, r) for x, y, z in vertices]
        return vertices, [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
                          (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ring = [(r * math.cos(2 * math.pi * i / segments),
             r * math.sin(2 * math.pi * i / segments), -r) for i in range(segments)]
    faces = [tuple(reversed(range(segments)))]
    if kind == 'CONE':
        return ring + [(0, 0, r)], faces + [(i, (i+1) % segments, segments) for i in range(segments)]
    vertices = ring + [(x, y, r) for x, y, z in ring]
    faces += [tuple(range(segments, segments*2))]
    faces += [(i, (i+1) % segments, (i+1) % segments + segments, i+segments) for i in range(segments)]
    return vertices, faces


class ObjectControl:
    def __init__(self, *, identities, scene, view_layer):
        self.identities = identities
        self.scene = scene
        self.view_layer = view_layer

    def register(self, registry):
        for name, description, schema, effects, handler in (
            ('create_primitive', 'Create a base mesh primitive in the current scene root collection.', CREATE_SCHEMA, ('object_creation',), self.create),
            ('transform', 'Set absolute parent-local location, XYZ Euler degrees and scale.', TRANSFORM_SCHEMA, ('transform',), self.transform),
            ('duplicate', 'Copy an object with a fresh UUID; independent data by default.', DUPLICATE_SCHEMA, ('object_creation',), self.duplicate),
            ('delete', 'Delete one object globally, preserving direct children world transforms.', DELETE_SCHEMA, ('object_deletion', 'hierarchy'), self.delete),
            ('set_parent', 'Set object parent, or clear it by omitting parent_id.', PARENT_SCHEMA, ('hierarchy', 'transform'), self.set_parent)):
            registry.register(ToolSpec('object.' + name, description, input_schema=schema,
                                       output_schema=OUTPUT_SCHEMA, side_effects=effects), handler)

    def _context(self):
        import bpy
        if bpy.context.mode != 'OBJECT':
            raise ToolError('UNSUPPORTED_OBJECT_MODE', 'Object control requires Object mode.')
        if not self.scene().is_editable:
            raise ToolError('OBJECT_READ_ONLY', 'Current scene is not editable.')
        self.identities.index()  # Detect unrelated identity collisions before mutation.
        self.view_layer().update()

    def _resolve(self, oid, *, writable=True):
        obj = self.identities.resolve(oid)
        if not any(object_key(candidate) == object_key(obj) for candidate in self.scene().objects):
            raise ToolError('OBJECT_NOT_IN_SCENE', 'Object is outside the current scene.')
        if obj.mode != 'OBJECT':
            raise ToolError('UNSUPPORTED_OBJECT_MODE', 'Object control requires Object mode.')
        if writable and not obj.is_editable:
            raise ToolError('OBJECT_READ_ONLY', 'Object is not editable.')
        return obj

    def _transformable(self, obj):
        if obj.constraints or obj.animation_data is not None or obj.rigid_body is not None:
            raise ToolError('UNSUPPORTED_OBJECT_STATE', 'Transform control requires an unconstrained, unanimated object without rigid-body state.')
        if obj.parent and obj.parent_type != 'OBJECT':
            raise ToolError('UNSUPPORTED_OBJECT_STATE', 'Only object parenting is supported.')

    def _values(self, args):
        if 'scale' in args and any(v == 0 for v in args['scale']):
            raise ToolError('INVALID_ARGUMENT', 'Scale components must be nonzero.')
        factor = {'m': 1, 'cm': 0.01, 'mm': 0.001}[args.get('unit', 'm')]
        values = {}
        if 'location' in args:
            values['location'] = [v * factor for v in args['location']]
        if 'rotation' in args:
            values['rotation_euler'] = [math.radians(v) for v in args['rotation']]
        if 'scale' in args:
            values['scale'] = args['scale']
        return values

    def _apply(self, obj, values):
        # Delta transforms would otherwise silently alter the requested local pose.
        obj.delta_location = (0, 0, 0)
        obj.delta_rotation_euler = (0, 0, 0)
        obj.delta_rotation_quaternion = (1, 0, 0, 0)
        obj.delta_scale = (1, 1, 1)
        obj.rotation_mode = 'XYZ'
        for name, value in values.items():
            setattr(obj, name, value)
        self.view_layer().update()

    def create(self, args):
        import bpy
        self._context()
        values = self._values(args)
        kind = args['primitive']
        if kind in ('CUBE', 'PLANE') and 'segments' in args:
            raise ToolError('INVALID_ARGUMENT', 'Segments apply only to cylinders and cones.')
        size = args.get('size', 2) * {'m': 1, 'cm': 0.01, 'mm': 0.001}[args.get('unit', 'm')]
        vertices, faces = primitive_geometry(kind, size, args.get('segments', 32))
        name = args.get('name', kind.title())
        mesh = bpy.data.meshes.new(name)
        obj = None
        try:
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
            obj = bpy.data.objects.new(name, mesh)
            self.scene().collection.objects.link(obj)
            oid = self.identities.ensure(obj)
            self._apply(obj, values)
        except Exception:
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            raise
        return MutationResult({'object_id': oid}, created_ids=[oid])

    def transform(self, args):
        self._context()
        obj = self._resolve(args['object_id'])
        self._transformable(obj)
        if not any(key in args for key in ('location', 'rotation', 'scale')):
            raise ToolError('INVALID_ARGUMENT', 'At least one transform component is required.')
        values = self._values(args)
        # Bake delta transforms and preserve every omitted component of the basis.
        location, rotation, scale = obj.matrix_basis.decompose()
        values.setdefault('location', location)
        values.setdefault('rotation_euler', rotation.to_euler('XYZ'))
        values.setdefault('scale', scale)
        self._apply(obj, values)
        return MutationResult({'object_id': args['object_id']}, modified_ids=[args['object_id']])

    def duplicate(self, args):
        import bpy
        self._context()
        source = self._resolve(args['object_id'], writable=False)
        duplicate = source.copy()
        copied_data = None
        try:
            if source.data is not None and not args.get('linked_data', False):
                copied_data = source.data.copy()
                duplicate.data = copied_data
            if 'name' in args:
                duplicate.name = args['name']
            self.scene().collection.objects.link(duplicate)
            oid = self.identities.assign_duplicate(source, duplicate)
            self.view_layer().update()
        except Exception:
            bpy.data.objects.remove(duplicate, do_unlink=True)
            if copied_data is not None and copied_data.users == 0:
                bpy.data.batch_remove(ids=[copied_data])
            raise
        return MutationResult({'object_id': oid}, created_ids=[oid])

    def _world_basis(self, obj):
        from mathutils import Matrix
        self._transformable(obj)
        world = obj.matrix_world.copy()
        location, rotation, scale = world.decompose()
        rebuilt = Matrix.LocRotScale(location, rotation, scale)
        tolerance = 1e-5 * max(1, max(abs(world[i][j]) for i in range(3) for j in range(3)))
        if any(abs(world[i][j] - rebuilt[i][j]) > tolerance for i in range(4) for j in range(4)):
            raise ToolError('UNSUPPORTED_OBJECT_STATE', 'Cannot preserve a sheared world transform in the new local basis.')
        return world

    def delete(self, args):
        import bpy
        self._context()
        obj = self._resolve(args['object_id'])
        children = list(obj.children)
        index = self.identities.index()
        ids_by_pointer = {object_key(value): key for key, value in index.items()}
        worlds = []
        for child in children:
            if not child.is_editable or object_key(child) not in ids_by_pointer:
                raise ToolError('UNSUPPORTED_OBJECT_STATE', 'All direct children must be editable and managed.')
            worlds.append(self._world_basis(child))
        modified = []
        for child, world in zip(children, worlds):
            child.parent = None
            self._apply(child, {})
            child.matrix_world = world
            modified.append(ids_by_pointer[object_key(child)])
        bpy.data.objects.remove(obj, do_unlink=True)
        self.view_layer().update()
        return MutationResult({'object_id': args['object_id']}, deleted_ids=[args['object_id']], modified_ids=sorted(modified))

    def set_parent(self, args):
        from mathutils import Matrix
        self._context()
        obj = self._resolve(args['object_id'])
        self._transformable(obj)
        parent = self._resolve(args['parent_id'], writable=False) if 'parent_id' in args else None
        ancestor = parent
        while ancestor is not None:
            if object_key(ancestor) == object_key(obj):
                raise ToolError('PARENT_CYCLE', 'Parenting would create a cycle.')
            ancestor = ancestor.parent
        keep_world = args.get('keep_world_transform', True)
        world = self._world_basis(obj) if keep_world else obj.matrix_world.copy()
        inverse = Matrix.Identity(4)
        if keep_world and parent is not None:
            try:
                inverse = parent.matrix_world.inverted()
            except ValueError:
                raise ToolError('INVALID_PARENT_TRANSFORM', 'Parent world transform is singular.') from None
        obj.parent = parent
        obj.parent_type = 'OBJECT'
        obj.parent_bone = ''
        obj.matrix_parent_inverse = inverse
        if keep_world:
            # The inverse cancels the new parent's world matrix, so the old world
            # pose becomes the child basis without depending on Blender UI state.
            self._apply(obj, {})
            obj.matrix_basis = world
        self.view_layer().update()
        return MutationResult({'object_id': args['object_id']}, modified_ids=[args['object_id']])
