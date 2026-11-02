"""Render one fixture's recorded outcome as a short animation.

Each fixture acts out what its recorded run established, on exported geometry:
a cut, a move, a blocked driver, or a route that needed no edit.

usage: Blender -b -P assets/readme/src/render_cells.py -- --code B02 --size 480x300 --samples 18
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
    add_ground,
    add_lights,
    add_solid,
    load_scene,
    material,
    place_camera,
    reset,
    srgb,
)
from cell_timeline import CELL_FRAMES, cell_state  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1 :]
code = argv[argv.index("--code") + 1]
width, height = (int(v) for v in argv[argv.index("--size") + 1].split("x"))
samples = int(argv[argv.index("--samples") + 1])
tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "cell"
close = "--close" in argv
only = {int(v) for v in argv[argv.index("--only") + 1].split(",")} if "--only" in argv else None

data = load_scene(code)
OUT = BUILD / f"{tag}_{code}"
OUT.mkdir(exist_ok=True)
scene = reset()
scene.render.resolution_x = width
scene.render.resolution_y = height
scene.cycles.samples = samples

edge = material("edge", EDGE_COLOR, 0.9)
parts = {c["id"]: c for c in data["components"]}
moving = {"target", "bridge", "screw1", "screw2"}
for c in data["components"]:
    if c["id"] in moving and (code != "B07" or c["id"] != "screw2"):
        continue
    tone = PART_TONES.get(c["role"], PART_TONES["chassis"])
    add_solid(c["id"], c, material(f"m.{c['id']}", tone), edge)

target_root, _, _ = add_solid("target", parts["target"], material("target", COBALT, 0.42), edge)

screws = {}
for sid in ("screw1", "screw2"):
    if sid in parts and not (code == "B07" and sid == "screw2"):
        tone = "#eef1f5"
        screws[sid] = add_solid(sid, parts[sid], material(f"m.{sid}", tone), edge)[0]

bracket_material = material("bracket", PART_TONES["bracket"], 0.5)
bracket_edge = material("bracket.edge", EDGE_COLOR, 0.9)
bracket_original = None
bracket_revised = None
removed_material = material("removed", SIGNAL, 0.45)
removed_node = removed_material.node_tree.nodes["Principled BSDF"]
removed_node.inputs["Emission Color"].default_value = srgb(SIGNAL)
removed_node.inputs["Emission Strength"].default_value = 0.7
removed_root = None
web_frames = []
design = data.get("gallery_design") if "--gallery-design" in argv else data.get("design")
if "bridge" in parts:
    bracket_original = add_solid("bracket.o", parts["bridge"], bracket_material, bracket_edge)
if design:
    if design["template"] == "T01":
        bracket_revised = add_solid("bracket.r", design["revised"], bracket_material, bracket_edge)
        removed_root, removed_surface, removed_edges = add_solid(
            "removed", design["removed"], removed_material, material("removed.edge", SIGNAL, 0.9)
        )
    else:
        for i, step in enumerate(data["web_motion"]):
            web_frames.append(add_solid(f"web.{i}", step, bracket_material, bracket_edge))

driver_parts = []
if code == "B07":
    # The driver the manifest declares: 2 mm shaft radius, 50 mm long; 8 mm handle radius, 30 mm long.
    screw = parts["screw1"]["bounds_mm"]
    cx = (screw[0][0] + screw[1][0]) / 2
    cy = (screw[0][1] + screw[1][1]) / 2
    tip_z = screw[1][2]
    driver_material = material("driver", "#5b6472", 0.5)
    bpy.ops.mesh.primitive_cylinder_add(radius=2, depth=50, location=(cx, cy, tip_z + 25), vertices=32)
    shaft = bpy.context.active_object
    bpy.ops.mesh.primitive_cylinder_add(radius=8, depth=30, location=(cx, cy, tip_z + 65), vertices=48)
    handle = bpy.context.active_object
    for obj in (shaft, handle):
        obj.data.materials.append(driver_material)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.shade_smooth()
    driver_parts = [shaft, handle]
    driver_rest = [o.location.z for o in driver_parts]
    shield_material = next(m for m in bpy.data.materials if m.name == "m.shield")

lows = [min(c["bounds_mm"][0][i] for c in data["components"]) for i in range(3)]
highs = [max(c["bounds_mm"][1][i] for c in data["components"]) for i in range(3)]
span = max(highs[0] - lows[0], highs[1] - lows[1])
add_ground(lows[2] - 0.02)
add_lights((0, 0, 20), span * 1.05)
camera = add_camera(62)
focus = ((lows[0] + highs[0]) / 2, (lows[1] + highs[1]) / 2, 40.0)
distance = span * (2.72 if not close else 2.7)
views = dict(B02=(-62, 30), B04=(-62, 30), B05=(66, 26), B06=(-62, 30), B07=(-62, 30), B08=(-62, 30))
azimuth, elevation = views[code]
place_camera(camera, focus, azimuth, elevation, distance)
if close:
    # Keep the lifted part clear of the caption at the top left.
    camera.data.shift_x = -0.135

neutral = srgb(PART_TONES["bracket"])
green = srgb(VERIFIED)
signal = srgb(SIGNAL)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def show(group, visible):
    if not group:
        return
    for obj in group:
        obj.hide_render = not visible


rendered = {}
frames = []
for frame in range(CELL_FRAMES):
    s = cell_state(code, frame)
    key = json.dumps(s, sort_keys=True)
    first = key not in rendered
    if first:
        rendered[key] = frame
    frames.append(rendered[key])
    if not first or (only is not None and frame not in only):
        continue
    path = OUT / f"f{frame:04d}.png"
    if path.exists():
        continue
    target_root.location = (0, 0, s["lift"])
    for sid, root in screws.items():
        root.location = (0, 0, s.get(sid, 0.0))
    nodes = bracket_material.node_tree.nodes["Principled BSDF"]
    nodes.inputs["Base Color"].default_value = mix(neutral, green, s["verified"])
    if design and design["template"] == "T01":
        show(bracket_original, s["cut"] < 0.5)
        show(bracket_revised, s["cut"] >= 0.5)
        removed_visible = s["block"] > 0.001
        show((removed_root, removed_surface, removed_edges), removed_visible)
        removed_root.location = (0, 0, s["block_lift"])
        removed_node.inputs["Alpha"].default_value = s["block"]
    elif design:
        show(bracket_original, False)
        index = round(s["web"] * (len(web_frames) - 1))
        for i, group in enumerate(web_frames):
            show(group, i == index)
    if driver_parts:
        for obj, rest in zip(driver_parts, driver_rest):
            obj.location.z = rest + s["driver"]
        shield = shield_material.node_tree.nodes["Principled BSDF"]
        shield.inputs["Base Color"].default_value = mix(srgb(PART_TONES["chassis"]), signal, s["blocked"])
    bpy.context.view_layer.update()
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f"rendered {code} {frame}", flush=True)

(OUT / "frames.json").write_text(json.dumps(frames))
print("unique renders", len(rendered))
