"""Simple Principled PBR materials with persistent, name-independent identity."""
import uuid

from .capability_registry import ToolSpec
from .errors import ToolError
from .objects import ID, NAME
from .schemas import MutationResult, object_schema

MATERIAL_UUID_PROPERTY = 'bar_material_uuid'
FACTOR = {'type': 'number', 'minimum': 0, 'maximum': 1}
COLOR = {'type': 'array', 'items': FACTOR, 'minItems': 4, 'maxItems': 4}
CREATE_SCHEMA = object_schema({'name': NAME, 'base_color': COLOR, 'roughness': FACTOR,
                               'metallic': FACTOR})
ASSIGN_SCHEMA = object_schema({'object_id': ID, 'material_id': ID}, ('object_id', 'material_id'))
CREATE_OUTPUT = object_schema({'material_id': ID, 'name': NAME, 'base_color': COLOR,
                               'roughness': FACTOR, 'metallic': FACTOR},
                              ('material_id', 'name', 'base_color', 'roughness', 'metallic'))
ASSIGN_OUTPUT = object_schema({'object_id': ID, 'material_id': ID}, ('object_id', 'material_id'))


class MaterialControl:
    def __init__(self, *, objects):
        self.objects = objects

    def register(self, registry):
        registry.register(ToolSpec('material.create', 'Create a simple opaque Principled PBR material; color is linear RGBA.',
            input_schema=CREATE_SCHEMA, output_schema=CREATE_OUTPUT,
            side_effects=('material_creation',)), self.create)
        registry.register(ToolSpec('material.assign', 'Replace all base-mesh face materials on one object, independently of linked meshes.',
            input_schema=ASSIGN_SCHEMA, output_schema=ASSIGN_OUTPUT,
            side_effects=('material_assignment',)), self.assign)

    def resolve(self, material_id):
        import bpy
        matches = [m for m in bpy.data.materials if m.get(MATERIAL_UUID_PROPERTY) == material_id]
        if not matches:
            raise ToolError('MATERIAL_NOT_FOUND', 'Material UUID does not resolve.')
        if len(matches) != 1:
            raise ToolError('MATERIAL_ID_COLLISION', 'Material UUID is ambiguous.')
        return matches[0]

    def create(self, args):
        import bpy
        self.objects._context()
        color = args.get('base_color', [.8, .8, .8, 1])
        # Transparency modes differ between Blender versions; opaque is explicit.
        if color[3] != 1:
            raise ToolError('INVALID_ARGUMENT', 'Basic materials require opaque alpha equal to 1.')
        roughness, metallic = args.get('roughness', .5), args.get('metallic', 0)
        mat = bpy.data.materials.new(args.get('name', 'Material'))
        try:
            mid = str(uuid.uuid4())
            mat[MATERIAL_UUID_PROPERTY] = mid
            mat.use_fake_user = True  # Retain an unassigned material across save/load.
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()
            shader = nodes.new('ShaderNodeBsdfPrincipled')
            output = nodes.new('ShaderNodeOutputMaterial')
            shader.inputs['Base Color'].default_value = color
            shader.inputs['Roughness'].default_value = roughness
            shader.inputs['Metallic'].default_value = metallic
            mat.node_tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
            mat.diffuse_color, mat.roughness, mat.metallic = color, roughness, metallic
        except Exception:
            bpy.data.materials.remove(mat)
            raise
        return MutationResult({'material_id': mid, 'name': mat.name, 'base_color': list(color),
                               'roughness': roughness, 'metallic': metallic})

    def assign(self, args):
        import bpy
        self.objects._context()
        obj = self.objects._resolve(args['object_id'])
        if obj.type != 'MESH':
            raise ToolError('UNSUPPORTED_OBJECT_TYPE', 'Material assignment requires a mesh object.')
        if not obj.data.is_editable or obj.data.shape_keys is not None or obj.animation_data is not None or obj.data.animation_data is not None:
            raise ToolError('UNSUPPORTED_OBJECT_STATE', 'Assignment requires an editable mesh without shape keys or animation.')
        mat = self.resolve(args['material_id'])
        # Publish a prepared copy; existing slots and linked users remain intact
        # if preparation fails. Object-linked slots are replaced after publication.
        old = obj.data
        old_slots = [(slot.link, slot.material) for slot in obj.material_slots]
        old_active = obj.active_material_index
        mesh = old.copy()
        try:
            mesh.materials.clear()
            mesh.materials.append(mat)
            for polygon in mesh.polygons:
                polygon.material_index = 0
            obj.data = mesh
            obj.material_slots[0].link = 'DATA'
            obj.active_material_index = 0
            self.objects.view_layer().update()
        except Exception:
            obj.data = old
            for slot, (link, material) in zip(obj.material_slots, old_slots):
                slot.link = link
                if link == 'OBJECT':
                    slot.material = material
            obj.active_material_index = old_active
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            raise
        if old.users == 0:
            bpy.data.meshes.remove(old)
        return MutationResult(dict(args), modified_ids=[args['object_id']])
