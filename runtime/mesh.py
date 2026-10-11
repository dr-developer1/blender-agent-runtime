"""Bounded base-mesh edits, staged in independent datablocks before publication."""
import math

from .capability_registry import ToolSpec
from .errors import ToolError
from .identity import object_key
from .objects import ID, UNIT, vector, OUTPUT_SCHEMA
from .schemas import MutationResult, object_schema
from .selection import MAX_MESH_ELEMENTS

LENGTH = {'type': 'number', 'minimum': 1e-9, 'maximum': 1e6}
HANDLE = {'selection_handle': ID, 'unit': UNIT}
EXTRUDE_SCHEMA = object_schema({**HANDLE, 'offset': vector(1e6)}, ('selection_handle', 'offset'))
INSET_SCHEMA = object_schema({**HANDLE, 'thickness': LENGTH}, ('selection_handle', 'thickness'))
BEVEL_SCHEMA = object_schema({**HANDLE, 'width': LENGTH,
    'segments': {'type': 'integer', 'minimum': 1, 'maximum': 16}}, ('selection_handle', 'width'))
BOOLEAN_SCHEMA = object_schema({'object_id': ID, 'operand_id': ID,
    'operation': {'type': 'string', 'enum': ['UNION', 'DIFFERENCE', 'INTERSECT']}},
    ('object_id', 'operand_id', 'operation'))
CLEANUP_SCHEMA = object_schema({'object_id': ID, 'unit': UNIT, 'merge_distance': LENGTH,
    'recalculate_normals': {'type': 'boolean'}}, ('object_id',))


class MeshControl:
    def __init__(self, *, objects, selections, depsgraph):
        self.objects, self.selections, self.depsgraph = objects, selections, depsgraph

    def register(self, registry):
        for name, schema, handler, kind in (
            ('extrude', EXTRUDE_SCHEMA, self.extrude, 'FACE'),
            ('inset', INSET_SCHEMA, self.inset, 'FACE'),
            ('bevel', BEVEL_SCHEMA, self.bevel, 'EDGE')):
            registry.register(ToolSpec('mesh.' + name, 'Edit selected base-mesh ' + kind.lower() + ' elements in local space.',
                input_schema=schema, output_schema=OUTPUT_SCHEMA, side_effects=('topology_change',),
                supports={'semantic_selection': True, 'transactions': False}), handler,
                prepare=lambda args, kind=kind: self._selection(args, kind))
        registry.register(ToolSpec('mesh.cleanup', 'Merge nearby base vertices and/or recalculate face normals.',
            input_schema=CLEANUP_SCHEMA, output_schema=OUTPUT_SCHEMA, side_effects=('topology_change',)), self.cleanup)
        if self.depsgraph is not None:
            registry.register(ToolSpec('mesh.boolean', 'Bake an exact boolean into the target base mesh, retaining the operand.',
                input_schema=BOOLEAN_SCHEMA, output_schema=OUTPUT_SCHEMA, side_effects=('topology_change',)), self.boolean)

    def _selection(self, args, kind):
        selected = self.selections.resolve(args['selection_handle'])
        if selected['element_type'] != kind:
            raise ToolError('INVALID_ARGUMENT', 'Operation requires ' + kind + ' elements.')
        if not selected['indices']:
            raise ToolError('EMPTY_SELECTION', 'Operation requires a nonempty selection.')
        return selected

    def _target(self, oid):
        self.objects._context()
        obj = self.objects._resolve(oid)
        if obj.type != 'MESH':
            raise ToolError('OBJECT_NOT_MESH', 'Mesh control requires a mesh object.')
        mesh = obj.data
        if not mesh.is_editable or mesh.shape_keys is not None or obj.modifiers or obj.vertex_groups:
            raise ToolError('UNSUPPORTED_OBJECT_STATE', 'Mesh control requires editable data without shape keys, modifiers or vertex groups.')
        self._budget(mesh)
        return obj

    @staticmethod
    def _budget(mesh):
        if len(mesh.vertices) + len(mesh.edges) + len(mesh.polygons) + len(mesh.loops) > MAX_MESH_ELEMENTS:
            raise ToolError('SELECTION_LIMIT_EXCEEDED', 'Mesh exceeds the element budget.')
        if any(not math.isfinite(value) for v in mesh.vertices for value in v.co):
            raise ToolError('INVALID_GEOMETRY', 'Mesh coordinates must be finite.')

    @staticmethod
    def _factor(args):
        return {'m': 1, 'cm': .01, 'mm': .001}[args.get('unit', 'm')]

    def _publish(self, obj, mesh, oid):
        self._budget(mesh)
        # Replacing data gives copy-on-write semantics even for linked duplicates.
        obj.data = mesh
        self.objects.view_layer().update()
        return MutationResult({'object_id': oid}, modified_ids=[oid])

    def _edit(self, oid, operation):
        import bpy
        import bmesh
        obj = self._target(oid)
        bm = bmesh.new()
        mesh = None
        try:
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            operation(bm)
            bm.normal_update()
            mesh = obj.data.copy()
            bm.to_mesh(mesh)
            mesh.update()
            return self._publish(obj, mesh, oid)
        finally:
            bm.free()
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    def extrude(self, args, selected):
        import bmesh
        from mathutils import Vector
        offset = Vector(args['offset']) * self._factor(args)
        if offset.length == 0:
            raise ToolError('INVALID_ARGUMENT', 'Extrusion offset must be nonzero.')
        def operation(bm):
            faces = [bm.faces[i] for i in selected['indices']]
            # Include region edges so the operator removes the original cap and
            # retains a single closed boundary instead of overlapping inner faces.
            edges = {edge for face in faces for edge in face.edges}
            result = bmesh.ops.extrude_face_region(bm, geom=faces + list(edges))
            bmesh.ops.translate(bm, verts=[v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)], vec=offset)
        return self._edit(selected['object_id'], operation)

    def inset(self, args, selected):
        import bmesh
        return self._edit(selected['object_id'], lambda bm: bmesh.ops.inset_region(bm,
            faces=[bm.faces[i] for i in selected['indices']], thickness=args['thickness'] * self._factor(args),
            use_boundary=True, use_even_offset=True, use_interpolate=True))

    def bevel(self, args, selected):
        import bmesh
        return self._edit(selected['object_id'], lambda bm: bmesh.ops.bevel(bm,
            geom=[bm.edges[i] for i in selected['indices']], offset=args['width'] * self._factor(args),
            segments=args.get('segments', 1), affect='EDGES', clamp_overlap=True, profile=.5))

    def cleanup(self, args):
        import bmesh
        normals = args.get('recalculate_normals', True)
        if 'merge_distance' not in args and not normals:
            raise ToolError('INVALID_ARGUMENT', 'Request merging or normal recalculation.')
        def operation(bm):
            if 'merge_distance' in args:
                bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=args['merge_distance'] * self._factor(args))
            if normals:
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        return self._edit(args['object_id'], operation)

    def boolean(self, args):
        import bpy
        target = self._target(args['object_id'])
        operand = self._target(args['operand_id'])
        if object_key(target) == object_key(operand):
            raise ToolError('INVALID_ARGUMENT', 'Boolean requires distinct objects.')
        for obj in (target, operand):
            if abs(obj.matrix_world.determinant()) < 1e-12:
                raise ToolError('UNSUPPORTED_OBJECT_STATE', 'Boolean requires nonsingular world transforms.')
        temporary = target.copy()
        mesh = None
        try:
            self.objects.scene().collection.objects.link(temporary)
            modifier = temporary.modifiers.new('BAR Boolean', 'BOOLEAN')
            modifier.operation = args['operation']
            modifier.solver = 'EXACT'
            modifier.object = operand
            self.objects.view_layer().update()
            graph = self.depsgraph()
            mesh = bpy.data.meshes.new_from_object(temporary.evaluated_get(graph),
                preserve_all_data_layers=True, depsgraph=graph)
            return self._publish(target, mesh, args['object_id'])
        finally:
            bpy.data.objects.remove(temporary, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
