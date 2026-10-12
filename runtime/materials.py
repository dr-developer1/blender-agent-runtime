"""Simple Principled PBR materials with persistent, name-independent identity."""
import uuid

from .capability_registry import ToolSpec
from .errors import ToolError
from .objects import ID, NAME
from .schemas import MutationResult, object_schema

MATERIAL_UUID_PROPERTY = 'bar_material_uuid'
FACTOR = {'type': 'number', 'minimum': 0, 'maximum': 1}
COLOR = {'type': 'array', 'items': FACTOR, 'minItems': 4, 'maxItems': 4}
SURFACE = {'type': 'string', 'enum': ['plain', 'wood', 'coated_metal', 'ceramic', 'polymer']}
GRAIN_AXIS = {'type': 'string', 'enum': ['X', 'Y', 'Z']}
CREATE_SCHEMA = object_schema({'name': NAME, 'base_color': COLOR, 'roughness': FACTOR,
                               'metallic': FACTOR, 'surface': SURFACE, 'grain_axis': GRAIN_AXIS})
ASSIGN_SCHEMA = object_schema({'object_id': ID, 'material_id': ID}, ('object_id', 'material_id'))
CREATE_OUTPUT = object_schema({'material_id': ID, 'name': NAME, 'base_color': COLOR,
                               'roughness': FACTOR, 'metallic': FACTOR,
                               'surface': SURFACE, 'grain_axis': GRAIN_AXIS},
                              ('material_id', 'name', 'base_color', 'roughness', 'metallic'))
ASSIGN_OUTPUT = object_schema({'object_id': ID, 'material_id': ID}, ('object_id', 'material_id'))


class MaterialControl:
    def __init__(self, *, objects):
        self.objects = objects

    def register(self, registry):
        registry.register(ToolSpec('material.create', 'Create an opaque Principled PBR material with an optional bounded procedural surface; color is linear RGBA.',
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
        surface, axis = args.get('surface', 'plain'), args.get('grain_axis', 'X')
        if 'grain_axis' in args and surface != 'wood':
            raise ToolError('INVALID_ARGUMENT', 'grain_axis requires the wood surface.')
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
            if surface != 'plain':
                self._surface(mat, shader, surface, axis, color, roughness)
            mat.diffuse_color, mat.roughness, mat.metallic = color, roughness, metallic
        except Exception:
            bpy.data.materials.remove(mat)
            raise
        result = {'material_id': mid, 'name': mat.name, 'base_color': list(color),
                  'roughness': roughness, 'metallic': metallic}
        if 'surface' in args:
            result['surface'] = surface
        if surface == 'wood':
            result['grain_axis'] = axis
        return MutationResult(result)

    @staticmethod
    def _surface(mat, shader, surface, axis, color, roughness):
        """Small deterministic node recipes, without external images or UV requirements.

        Generated coordinates intentionally fit each base mesh. These are visual
        approximations, not physically measured materials or an arbitrary node API.
        """
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        coords = nodes.new('ShaderNodeTexCoord')
        mapping = nodes.new('ShaderNodeVectorMath')
        mapping.operation = 'MULTIPLY'
        stretch = [18, 18, 18]
        if surface == 'wood':
            stretch['XYZ'.index(axis)] = 1.2
        mapping.inputs[1].default_value = stretch
        links.new(coords.outputs['Generated'], mapping.inputs[0])
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 3 if surface == 'wood' else 6
        noise.inputs['Detail'].default_value = 2
        noise.inputs['Roughness'].default_value = .65
        links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
        ramp = nodes.new('ShaderNodeValToRGB')
        lo, hi = ramp.color_ramp.elements
        lo.position, hi.position = .25, .75
        contrast = .26 if surface == 'wood' else .035
        lo.color = tuple(c*(1-contrast) for c in color[:3]) + (1,)
        hi.color = tuple(min(1, c*(1+contrast)) for c in color[:3]) + (1,)
        links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
        rough = nodes.new('ShaderNodeMapRange')
        rough.inputs['To Min'].default_value = max(0, roughness-.06)
        rough.inputs['To Max'].default_value = min(1, roughness+.06)
        links.new(noise.outputs['Fac'], rough.inputs['Value'])
        links.new(rough.outputs['Result'], shader.inputs['Roughness'])
        bump = nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = .12 if surface == 'wood' else .055
        bump.inputs['Distance'].default_value = .00015 if surface == 'wood' else .00004
        links.new(noise.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], shader.inputs['Normal'])

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
