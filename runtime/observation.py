"""Deterministic framing and isolated diagnostic rendering; bpy is imported lazily."""
import base64
import itertools
import math
import os
from pathlib import Path
import tempfile

from .capability_registry import ToolSpec
from .errors import ToolError
from .identity import UUID_PROPERTY, object_key, validate_uuid
from .schemas import object_schema

VIEWS = ('front', 'back', 'left', 'right', 'top', 'perspective', 'bottom')
DEFAULT_VIEWS = VIEWS[:6]
MAX_RENDER_SIZE = 768
MAX_RENDER_PIXELS = 1024 * 1024
MAX_RENDER_BYTES = 700_000  # Combined raw PNG budget; base64 fits the 1 MiB frame.
MAX_OBSERVATION_ELEMENTS = 200_000
MAX_OBSERVATION_OBJECTS = 100
VECTOR = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}
VIEW = {'type': 'string', 'enum': list(VIEWS)}
COMMON = {
    'object_ids': {'type': 'array', 'items': {'type': 'string', 'minLength': 1, 'maxLength': 36},
                   'minItems': 1, 'maxItems': MAX_OBSERVATION_OBJECTS},
    'width': {'type': 'integer', 'minimum': 32, 'maximum': MAX_RENDER_SIZE},
    'height': {'type': 'integer', 'minimum': 32, 'maximum': MAX_RENDER_SIZE},
    'padding': {'type': 'number', 'minimum': 1.05, 'maximum': 3},
}
RENDER_OPTIONS = {'engine': {'type': 'string', 'enum': ['WORKBENCH', 'EEVEE']},
                  'mode': {'type': 'string', 'enum': ['solid', 'wireframe', 'silhouette']}}
CAMERA_INPUT = object_schema({**COMMON, 'view': VIEW})
RENDER_INPUT = object_schema({**COMMON, **RENDER_OPTIONS, 'view': VIEW})
MULTI_INPUT = object_schema({**COMMON, **RENDER_OPTIONS,
    'views': {'type': 'array', 'items': VIEW, 'minItems': 1, 'maxItems': 6}})
BOUNDS = object_schema({'min': VECTOR, 'max': VECTOR}, ('min', 'max'))
CAMERA = object_schema({
    'view': VIEW, 'projection': {'type': 'string', 'enum': ['ORTHO', 'PERSP']},
    'location': VECTOR, 'target': VECTOR,
    'world_matrix': {'type': 'array', 'items': {'type': 'array', 'items': {'type': 'number'},
        'minItems': 4, 'maxItems': 4}, 'minItems': 4, 'maxItems': 4},
    'ortho_scale': {'type': 'number'}, 'lens_mm': {'type': 'number'},
    'sensor_width_mm': {'type': 'number'}, 'clip_start': {'type': 'number'},
    'clip_end': {'type': 'number'}, 'width': {'type': 'integer'}, 'height': {'type': 'integer'},
}, ('view', 'projection', 'location', 'target', 'world_matrix', 'ortho_scale', 'lens_mm',
    'sensor_width_mm', 'clip_start', 'clip_end', 'width', 'height'))
BASE_OUTPUT = {'object_ids': {'type': 'array', 'items': {'type': 'string'}},
               'bounds': BOUNDS, 'geometry_source': {'type': 'string'}}
CAMERA_OUTPUT = object_schema({**BASE_OUTPUT, 'camera': CAMERA}, (*BASE_OUTPUT, 'camera'))
IMAGE = object_schema({'camera': CAMERA, 'mime_type': {'type': 'string'},
    'png_base64': {'type': 'string'}, 'byte_count': {'type': 'integer'}},
    ('camera', 'mime_type', 'png_base64', 'byte_count'))
RENDER_OUTPUT = object_schema({**BASE_OUTPUT, 'engine': {'type': 'string'},
    'mode': {'type': 'string'}, 'images': {'type': 'array', 'items': IMAGE}},
    (*BASE_OUTPUT, 'engine', 'mode', 'images'))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def normalized(a):
    length = math.sqrt(dot(a, a))
    return [x / length for x in a]


def frame_camera(bounds, view, width=384, height=384, padding=1.15):
    """Fit all world AABB corners, including depth, with horizontal sensor fit."""
    low, high = bounds['min'], bounds['max']
    if (view not in VIEWS or len(low) != 3 or len(high) != 3 or
            any(not math.isfinite(v) or abs(v) > 1_000_000 for v in (*low, *high)) or
            any(a > b for a, b in zip(low, high))):
        raise ToolError('INVALID_GEOMETRY', 'Framing requires finite ordered bounds within one million metres.')
    target = [(a + b) / 2 for a, b in zip(low, high)]
    directions = {'front': (0,-1,0), 'back': (0,1,0), 'left': (-1,0,0),
                  'right': (1,0,0), 'top': (0,0,1), 'bottom': (0,0,-1),
                  'perspective': (1,-1,1)}
    outward = normalized(directions[view])
    forward = [-v for v in outward]
    up_hint = (0,1,0) if view == 'top' else (0,-1,0) if view == 'bottom' else (0,0,1)
    right = normalized(cross(forward, up_hint))
    up = cross(right, forward)
    corners = [[v - c for v, c in zip(point, target)]
               for point in itertools.product(*zip(low, high))]
    radius = max(max(math.sqrt(dot(c, c)) for c in corners), 1e-5)
    aspect = width / height
    scale = max(2 * max(abs(dot(c, right)) for c in corners),
                2 * max(abs(dot(c, up)) for c in corners) * aspect, 2e-5) * padding
    distance = radius * 3
    if view == 'perspective':
        tan_x = 36 / (2 * 50)
        tan_y = tan_x / aspect
        distance = max(radius * 1.1, max(dot(c, outward) + padding * max(abs(dot(c, right)) / tan_x,
                       abs(dot(c, up)) / tan_y) for c in corners) + radius * .05)
    location = [c + distance * d for c, d in zip(target, outward)]
    return {'view': view, 'projection': 'PERSP' if view == 'perspective' else 'ORTHO',
            'location': location, 'target': target,
            'world_matrix': [[right[i], up[i], outward[i], location[i]] for i in range(3)] + [[0,0,0,1]],
            'ortho_scale': scale, 'lens_mm': 50., 'sensor_width_mm': 36.,
            'clip_start': max(1e-6, (distance - radius) * .5),
            'clip_end': distance + radius * 2, 'width': width, 'height': height}


class ObservationService:
    def __init__(self, *, identities, scene, view_layer, depsgraph):
        self.identities, self.scene = identities, scene
        self.view_layer, self.depsgraph = view_layer, depsgraph

    def register(self, registry):
        for name, description, schema, output, handler in (
            ('observe.camera', 'Describe a deterministic camera fitted to evaluated mesh bounds.',
             CAMERA_INPUT, CAMERA_OUTPUT, self.camera),
            ('observe.render', 'Render one isolated diagnostic view to inline PNG.',
             RENDER_INPUT, RENDER_OUTPUT, self.render),
            ('observe.render_multiview', 'Render up to six diagnostic views from the same evaluated snapshot.',
             MULTI_INPUT, RENDER_OUTPUT, self.render_multiview)):
            registry.register(ToolSpec(name, description, input_schema=schema, output_schema=output,
                supports={'transactions': True}, transaction_safe=True), handler)

    def _targets(self, arguments):
        scene, layer = self.scene(), self.view_layer()
        if any(obj.mode != 'OBJECT' for obj in scene.objects):
            raise ToolError('UNSUPPORTED_OBJECT_MODE', 'Observation requires Object mode.')
        index = self.identities.index()
        explicit = arguments.get('object_ids')
        if explicit is not None:
            if len(set(explicit)) != len(explicit):
                raise ToolError('INVALID_ARGUMENT', 'Object IDs must be unique.')
            for oid in explicit:
                validate_uuid(oid)
                if oid not in index:
                    raise ToolError('OBJECT_NOT_FOUND', 'No current object has this UUID.', {'object_id': oid})
            objects = [index[oid] for oid in sorted(explicit)]
        else:
            objects = [obj for obj in scene.objects if obj.type == 'MESH' and not obj.hide_render
                       and obj.visible_get(view_layer=layer)]
        if len(objects) > MAX_OBSERVATION_OBJECTS:
            raise ToolError('OBSERVATION_LIMIT_EXCEEDED', 'Too many observation objects.')
        for obj in objects:
            if obj.name not in scene.objects:
                raise ToolError('OBJECT_NOT_IN_SCENE', 'Target is not in the active scene.')
            if obj.type != 'MESH':
                raise ToolError('UNSUPPORTED_OBJECT_TYPE', 'Observation targets must be meshes.')
            if obj.hide_render or not obj.visible_get(view_layer=layer):
                raise ToolError('OBJECT_NOT_VISIBLE', 'Target must be visible and render enabled.')
            if UUID_PROPERTY not in obj:
                raise ToolError('OBJECT_NOT_MANAGED', 'Target has no managed identity.')
        if not objects:
            raise ToolError('EMPTY_OBSERVATION', 'No visible render-enabled meshes to observe.')
        objects.sort(key=lambda obj: obj[UUID_PROPERTY])
        layer.update()
        graph = self.depsgraph()
        keys = {object_key(obj) for obj in objects}
        # Instancing would otherwise be silently absent from the evaluated mesh copy.
        for instance in graph.object_instances:
            if instance.is_instance and (
                    (instance.parent is not None and object_key(instance.parent.original) in keys) or
                    (instance.object is not None and object_key(instance.object.original) in keys)):
                raise ToolError('UNSUPPORTED_INSTANCING', 'Instanced observation targets are not supported.')
        evaluated, low, high, total = [], [math.inf]*3, [-math.inf]*3, 0
        for obj in objects:
            current = obj.evaluated_get(graph)
            if not current.is_evaluated:
                raise ToolError('OBJECT_NOT_EVALUATED', 'Target is excluded from the dependency graph.')
            mesh = current.data
            total += len(mesh.vertices) + len(mesh.edges) + len(mesh.polygons)
            if total > MAX_OBSERVATION_ELEMENTS:
                raise ToolError('OBSERVATION_LIMIT_EXCEEDED', 'Evaluated mesh scan budget exceeded.')
            for vertex in mesh.vertices:
                point = current.matrix_world @ vertex.co
                if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in point):
                    raise ToolError('INVALID_GEOMETRY', 'Observation coordinates must be finite and within one million metres.')
                low = [min(a, b) for a, b in zip(low, point)]
                high = [max(a, b) for a, b in zip(high, point)]
            evaluated.append(current)
        if not all(math.isfinite(v) for v in low):
            raise ToolError('EMPTY_OBSERVATION', 'Targets have no evaluated vertices.')
        return graph, evaluated, {'object_ids': [obj[UUID_PROPERTY] for obj in objects],
            'bounds': {'min': low, 'max': high}, 'geometry_source': 'evaluated_viewport_mesh'}

    def camera(self, arguments):
        _, _, base = self._targets(arguments)
        return {**base, 'camera': frame_camera(base['bounds'], arguments.get('view', 'perspective'),
            arguments.get('width', 384), arguments.get('height', 384), arguments.get('padding', 1.15))}

    def render(self, arguments):
        return self._render(arguments, [arguments.get('view', 'perspective')])

    def render_multiview(self, arguments):
        return self._render(arguments, arguments.get('views', list(DEFAULT_VIEWS)))

    def _render(self, arguments, views):
        width, height = arguments.get('width', 384), arguments.get('height', 384)
        engine, mode = arguments.get('engine', 'WORKBENCH'), arguments.get('mode', 'solid')
        if len(set(views)) != len(views):
            raise ToolError('INVALID_ARGUMENT', 'Views must be unique.')
        if width * height * len(views) > MAX_RENDER_PIXELS:
            raise ToolError('OBSERVATION_LIMIT_EXCEEDED', 'Combined render pixel budget exceeded.')
        if engine == 'EEVEE' and mode != 'solid':
            raise ToolError('INVALID_ARGUMENT', 'Wireframe and silhouette require Workbench.')
        graph, objects, base = self._targets(arguments)
        cameras = [frame_camera(base['bounds'], v, width, height, arguments.get('padding', 1.15)) for v in views]
        try:
            images = self._render_blender(graph, objects, cameras, engine, mode, base['bounds'])
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError('RENDER_FAILED', 'Diagnostic rendering failed; temporary resources were discarded.') from exc
        return {**base, 'engine': engine, 'mode': mode, 'images': images}

    def _render_blender(self, graph, objects, cameras, engine, mode, bounds):
        import bpy
        from mathutils import Matrix

        # All allocations are owned explicitly. Never clear global orphan data.
        owned = []
        def own(collection, value):
            owned.append((collection.rna_type.identifier, value))
            return value
        try:
            stage = own(bpy.data.scenes, bpy.data.scenes.new('BAR observation'))
            source_scene = self.scene()
            stage.frame_set(source_scene.frame_current, subframe=source_scene.frame_subframe)
            if engine == 'WORKBENCH':
                stage.render.engine = 'BLENDER_WORKBENCH'
            else:
                # Blender 5 renamed EEVEE_NEXT back to EEVEE.
                try:
                    stage.render.engine = 'BLENDER_EEVEE_NEXT'
                except TypeError:
                    stage.render.engine = 'BLENDER_EEVEE'
            stage.render.resolution_x, stage.render.resolution_y = cameras[0]['width'], cameras[0]['height']
            stage.render.resolution_percentage = 100
            stage.render.image_settings.file_format = 'PNG'
            stage.render.image_settings.color_mode = 'RGBA'
            stage.render.image_settings.color_depth = '8'
            stage.render.image_settings.compression = 100
            stage.render.dither_intensity = 0
            stage.render.film_transparent = False
            stage.render.use_file_extension = True
            stage.render.use_compositing = False
            stage.render.use_sequencer = False
            # Blender otherwise embeds dates, filenames and timing in PNG metadata.
            for prop in stage.render.bl_rna.properties:
                if prop.identifier.startswith('use_stamp') and prop.type == 'BOOLEAN':
                    setattr(stage.render, prop.identifier, False)
            stage.view_settings.view_transform = 'Standard'
            stage.view_settings.look = 'None'
            stage.view_settings.exposure = 0
            stage.view_settings.gamma = 1
            shading = stage.display.shading
            shading.light = 'STUDIO' if mode == 'solid' else 'FLAT'
            shading.studio_light = 'paint.sl'
            shading.color_type = 'SINGLE'
            shading.single_color = (.65,.65,.65) if mode == 'solid' else (0,0,0)
            shading.background_type = 'WORLD'
            shading.show_shadows = mode == 'solid'
            shading.show_cavity = mode == 'solid'
            shading.cavity_type = 'BOTH'
            shading.show_object_outline = False
            stage.display.render_aa = '8'
            world = own(bpy.data.worlds, bpy.data.worlds.new('BAR observation world'))
            world.color = (1,1,1)
            stage.world = world
            if engine == 'EEVEE':
                world.use_nodes = True
                world.node_tree.nodes['Background'].inputs['Color'].default_value = (.15,.15,.15,1)
                world.node_tree.nodes['Background'].inputs['Strength'].default_value = .5
                if hasattr(stage, 'eevee'):
                    stage.eevee.taa_render_samples = 16
            for source in objects:
                if mode == 'wireframe':
                    # Actual evaluated edges, including loose edges, with no triangle diagonals.
                    data = own(bpy.data.curves, bpy.data.curves.new('BAR edges', 'CURVE'))
                    data.dimensions = '3D'
                    data.resolution_u = 1
                    data.bevel_resolution = 0
                    data.bevel_depth = max(c['ortho_scale'] / c['width'] for c in cameras) * .6
                    for edge in source.data.edges:
                        spline = data.splines.new('POLY')
                        spline.points.add(1)
                        for point, vi in zip(spline.points, edge.vertices):
                            co = source.matrix_world @ source.data.vertices[vi].co
                            point.co = (*co, 1)
                    matrix = Matrix.Identity(4)
                else:
                    data = own(bpy.data.meshes, bpy.data.meshes.new_from_object(source,
                        preserve_all_data_layers=engine == 'EEVEE', depsgraph=graph))
                    matrix = source.matrix_world.copy()
                obj = own(bpy.data.objects, bpy.data.objects.new('BAR observed mesh', data))
                stage.collection.objects.link(obj)
                obj.matrix_world = matrix
            cam_data = own(bpy.data.cameras, bpy.data.cameras.new('BAR observation camera'))
            cam = own(bpy.data.objects, bpy.data.objects.new('BAR observation camera', cam_data))
            stage.collection.objects.link(cam)
            stage.camera = cam
            if engine == 'EEVEE':
                target = cameras[0]['target']
                radius = max(math.dist(bounds['min'], bounds['max']), 1e-5)
                for direction, energy in (((-1,-2,3), 600), ((2,1,2), 250)):
                    light_data = own(bpy.data.lights, bpy.data.lights.new('BAR diagnostic light', 'AREA'))
                    light_data.energy, light_data.shape, light_data.size = energy * radius**2, 'DISK', radius * 2
                    light = own(bpy.data.objects, bpy.data.objects.new('BAR diagnostic light', light_data))
                    stage.collection.objects.link(light)
                    light.location = [c + radius*d for c, d in zip(target, direction)]
                    light.rotation_euler = (Matrix.Translation(target).translation - light.location).to_track_quat('-Z','Y').to_euler()
            images, total = [], 0
            with tempfile.TemporaryDirectory(prefix='bar-observation-', dir=os.environ.get('BAR_RECOVERY_ROOT')) as directory:
                for i, camera in enumerate(cameras):
                    cam.matrix_world = Matrix(camera['world_matrix'])
                    cam_data.type = camera['projection']
                    cam_data.sensor_fit = 'HORIZONTAL'
                    cam_data.sensor_width = camera['sensor_width_mm']
                    cam_data.lens, cam_data.ortho_scale = camera['lens_mm'], camera['ortho_scale']
                    cam_data.clip_start, cam_data.clip_end = camera['clip_start'], camera['clip_end']
                    path = Path(directory) / f'{i}.png'
                    stage.render.filepath = str(path)
                    status = self._write_render(stage)
                    if status != {'FINISHED'} or not path.is_file():
                        raise ToolError('RENDER_FAILED', 'Blender did not produce a PNG.')
                    size = path.stat().st_size
                    total += size
                    if total > MAX_RENDER_BYTES:
                        raise ToolError('RESPONSE_TOO_LARGE', 'PNG budget exceeded; reduce resolution or views.')
                    images.append({'camera': camera, 'mime_type': 'image/png', 'byte_count': size,
                                   'png_base64': base64.b64encode(path.read_bytes()).decode('ascii')})
            return images
        finally:
            # Objects must go before their data, and scenes before their world.
            for collection_name in ('objects', 'scenes', 'meshes', 'curves', 'cameras', 'lights', 'worlds'):
                collection = getattr(bpy.data, collection_name)
                for owner, value in reversed(owned):
                    if owner == collection.rna_type.identifier:
                        collection.remove(value, do_unlink=True)

    @staticmethod
    def _write_render(stage):
        import bpy
        return bpy.ops.render.render(write_still=True, scene=stage.name)
