"""Render the hero animation's frames from exported B05 geometry.

usage: Blender -b -P assets/readme/src/render_hero.py -- [--frames 0,50,120] [--scale 0.5]
Frames with an identical scene state share one render, recorded in frames.json.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402

from render_lib import (  # noqa: E402
    BUILD,
    COBALT,
    EDGE_COLOR,
    PART_TONES,
    SIGNAL,
    VERIFIED,
    add_camera,
    add_edges,
    add_ground,
    add_lights,
    add_mesh,
    add_solid,
    load_scene,
    material,
    place_camera,
    reset,
    srgb,
)
from timeline import LAST_FRAME, state  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
only = None
scale = 1.0
samples = 32
for i, arg in enumerate(argv):
    if arg == "--frames":
        only = {int(x) for x in argv[i + 1].split(",")}
    if arg == "--scale":
        scale = float(argv[i + 1])
    if arg == "--samples":
        samples = int(argv[i + 1])

WEB_UNDERSIDE_MM = 30.0
OUT = BUILD / "hero"
OUT.mkdir(exist_ok=True)

data = load_scene("B05")
scene = reset()
scene.render.resolution_x = int(1200 * scale)
scene.render.resolution_y = int(676 * scale)
scene.cycles.samples = samples
scene.render.use_persistent_data = False

edge = material("edge", EDGE_COLOR, 0.9)
parts = {c["id"]: c for c in data["components"]}
for c in data["components"]:
    if c["id"] in ("target", "bridge"):
        continue
    add_solid(c["id"], c, material(f"m.{c['id']}", PART_TONES[c["role"]]), edge)

pack_material = material("pack", COBALT, 0.42)
pack_root, _, _ = add_solid("pack", parts["target"], pack_material, edge)

ghost_material = material("ghost", COBALT, 0.4)
ghost_edge = material("ghost.edge", COBALT, 0.9)
ghost_root, ghost_surface, ghost_edges = add_solid(
    "ghost", parts["target"], ghost_material, ghost_edge
)
ghost_surface.visible_shadow = False
ghost_edges.visible_shadow = False

bracket_material = material("bracket", PART_TONES["bracket"], 0.5)
bracket_edge = material("bracket.edge", EDGE_COLOR, 0.9)

overlap_material = material("overlap", SIGNAL, 0.45)
bsdf = overlap_material.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Emission Color"].default_value = srgb(SIGNAL)
bsdf.inputs["Emission Strength"].default_value = 0.85
overlap_root, overlap_surface, overlap_edges = add_solid(
    "overlap", data["interference"], overlap_material, material("overlap.edge", SIGNAL, 0.9)
)

positions = []
for allowed in data["allowed_positions"]:
    chosen = allowed["offset_y_mm"] == data["design"]["parameters"]["offset_y_mm"]
    mat = material(f"pos.{allowed['offset_y_mm']}", COBALT if chosen else "#5b6472", 0.9)
    # Only the web moves, so only the web is drawn at each allowed position.
    web_edges = [
        flat for flat in allowed["edges"] if min(flat[2::3]) >= WEB_UNDERSIDE_MM - 0.01
    ]
    positions.append(
        (
            add_edges(
                f"pos.{allowed['offset_y_mm']}",
                web_edges,
                mat,
                0.16 if chosen else 0.11,
            ),
            mat,
        )
    )

web_frames = []
for i, step in enumerate(data["web_motion"]):
    root, surface, edges = add_solid(f"web.{i}", step, bracket_material, bracket_edge)
    root.hide_render = True
    surface.hide_render = True
    edges.hide_render = True
    web_frames.append((root, surface, edges))

ground_z = min(c["bounds_mm"][0][2] for c in data["components"]) - 0.02
add_ground(ground_z)
focus = (0.0, -2.0, 27.0)
add_lights((0, 0, 20), 190, key=1.0)
camera = add_camera(58)
camera.data.shift_x = -0.075
camera.data.shift_y = 0.035

neutral = srgb(PART_TONES["bracket"])
signal = srgb(SIGNAL)
green = srgb(VERIFIED)
cobalt_ink = srgb(COBALT)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def set_alpha(mat, value):
    mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = value


def set_color(mat, color):
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color


def set_visible(obj, visible):
    obj.hide_render = not visible


def apply(s):
    place_camera(camera, focus, s["azimuth"], s["elevation"], 528.0 * s["distance"])
    pack_root.location = (0, 0, s["lift"])
    ghost_root.location = (0, 0, s["ghost"])
    ghost_on = s["ghost_alpha"] > 0.001
    set_visible(ghost_surface, ghost_on)
    set_visible(ghost_edges, ghost_on)
    set_alpha(ghost_material, 0.2 * s["ghost_alpha"])
    set_alpha(ghost_edge, s["ghost_alpha"])
    overlap_on = s["overlap"] > 0.001
    set_visible(overlap_surface, overlap_on)
    set_visible(overlap_edges, overlap_on)
    set_alpha(overlap_material, s["overlap"])
    color = neutral
    if s["verified"] > 0:
        color = mix(neutral, green, s["verified"])
    elif s["reveal"] > 0:
        color = mix(neutral, signal, 0.3 * s["reveal"])
    set_color(bracket_material, color)
    set_alpha(bracket_material, 1.0 - 0.62 * s["reveal"])
    set_alpha(bracket_edge, 1.0 - 0.3 * s["reveal"])
    index = round(s["web"] * (len(web_frames) - 1))
    for i, (root, surface, edges) in enumerate(web_frames):
        set_visible(root, i == index)
        set_visible(surface, i == index)
        set_visible(edges, i == index)
    for obj, mat in positions:
        set_visible(obj, s["choices"] > 0.001)
        set_alpha(mat, s["choices"])
    bpy.context.view_layer.update()


def project(point):
    from bpy_extras.object_utils import world_to_camera_view

    co = world_to_camera_view(scene, camera, __import__("mathutils").Vector(point))
    return [co.x, 1 - co.y]


ANCHORS = dict(
    witness=data["witnesses"][0]["point_mm"],
    route_start=(0.0, 15.0, 26.0),
    route_end=(0.0, 15.0, 106.0),
    pack_top=(0.0, 15.0, 26.0),
)

renders = {}
frames = []
for frame in range(LAST_FRAME):
    s = state(frame)
    key = json.dumps(s, sort_keys=True)
    first = key not in renders
    if first:
        renders[key] = frame
    apply(s)
    frames.append(
        dict(
            frame=frame,
            render=renders[key],
            anchors={k: project(v) for k, v in ANCHORS.items()},
        )
    )
    if first and (only is None or any(json.dumps(state(f), sort_keys=True) == key for f in only)):
        path = OUT / f"f{frame:04d}.png"
        if not path.exists():
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
        print(f"rendered {frame}", flush=True)

(OUT / "frames.json").write_text(json.dumps(frames))
print("unique renders", len(renders))
