"""Blender helpers for rendering exported UNLOCK geometry. Runs inside Blender.

Geometry comes only from export_scene.py. Colors follow frontend/src/styles/tokens.css:
cobalt is the target, signal is an obstruction, verified is a passed check.
"""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BUILD = HERE / ".build"


def srgb(hex_color):
    def linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    h = hex_color.lstrip("#")
    return tuple(linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


COBALT = "#3268f5"
SIGNAL = "#e4602f"
VERIFIED = "#34866b"
PART_TONES = dict(
    chassis="#c3cad4",
    cover="#c3cad4",
    bracket="#dde2e9",
    electronics="#7f8896",
    fastener="#eef1f5",
    service_module=COBALT,
)
EDGE_COLOR = "#20252c"


def load_scene(code):
    return json.loads((BUILD / f"{code}.json").read_text())


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = True
    cycles.use_denoising = True
    cycles.denoiser = "OPENIMAGEDENOISE"
    cycles.use_adaptive_sampling = True
    cycles.adaptive_threshold = 0.02
    cycles.max_bounces = 4
    cycles.diffuse_bounces = 3
    cycles.glossy_bounces = 2
    cycles.transparent_max_bounces = 8
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    # Standard keeps tokens exact; Filmic and AgX would shift cobalt and signal.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    return scene


def material(name, color, roughness=0.5, metallic=0.0, specular=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = srgb(color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Specular IOR Level"].default_value = specular
    return mat


def fade_material(name, color, roughness=0.5):
    """A material whose base color and alpha can be animated per frame."""
    mat = material(name, color, roughness)
    mat.surface_render_method = "DITHERED"
    return mat


def add_mesh(name, payload, mat, parent=None):
    vertices = payload["vertices"]
    triangles = payload["triangles"]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [tuple(vertices[i : i + 3]) for i in range(0, len(vertices), 3)],
        [],
        [tuple(triangles[i : i + 3]) for i in range(0, len(triangles), 3)],
    )
    mesh.update()
    # Vertices are per BRep face, so smooth shading never crosses a CAD edge.
    mesh.shade_smooth()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def add_edges(name, polylines, mat, radius=0.09, parent=None):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 1
    curve.fill_mode = "FULL"
    for flat in polylines:
        points = [flat[i : i + 3] for i in range(0, len(flat), 3)]
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, co in zip(spline.points, points):
            point.co = (*co, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def add_solid(name, payload, mat, edge_mat, parent=None, edge_radius=0.09):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    if parent:
        root.parent = parent
    surface = add_mesh(f"{name}.surface", payload["mesh"], mat, root)
    edges = None
    if payload.get("edges"):
        edges = add_edges(f"{name}.edges", payload["edges"], edge_mat, edge_radius, root)
    return root, surface, edges


def add_ground(z):
    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, z))
    ground = bpy.context.active_object
    ground.is_shadow_catcher = True
    return ground


def add_lights(center, scale, key=1.0):
    world = bpy.data.worlds.new("studio")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (1, 1, 1, 1)
    background.inputs[1].default_value = 0.62
    bpy.context.scene.world = world

    def area(name, offset, power, size):
        light = bpy.data.lights.new(name, "AREA")
        light.size = size * scale
        light.energy = power * scale * scale * key
        obj = bpy.data.objects.new(name, light)
        bpy.context.collection.objects.link(obj)
        obj.location = Vector(center) + Vector(offset) * scale
        direction = Vector(center) - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return obj

    area("key", (-1.1, -1.3, 2.0), 6.5, 1.6)
    area("rim", (1.5, 1.2, 1.1), 2.2, 1.2)


def add_camera(lens=70):
    data = bpy.data.cameras.new("camera")
    data.lens = lens
    data.clip_end = 20000
    camera = bpy.data.objects.new("camera", data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def place_camera(camera, focus, azimuth_deg, elevation_deg, distance):
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    offset = Vector(
        (
            distance * math.cos(el) * math.cos(az),
            distance * math.cos(el) * math.sin(az),
            distance * math.sin(el),
        )
    )
    camera.location = Vector(focus) + offset
    direction = Vector(focus) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def scene_bounds(scene_data):
    lows = [min(c["bounds_mm"][0][i] for c in scene_data["components"]) for i in range(3)]
    highs = [max(c["bounds_mm"][1][i] for c in scene_data["components"]) for i in range(3)]
    return lows, highs
