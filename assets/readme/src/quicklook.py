"""Still of each exported fixture, used to frame shots.

usage: Blender -b -P assets/readme/src/quicklook.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402

from render_lib import (  # noqa: E402
    BUILD,
    EDGE_COLOR,
    PART_TONES,
    add_camera,
    add_ground,
    add_lights,
    add_solid,
    load_scene,
    material,
    place_camera,
    reset,
    scene_bounds,
)

for code in ("B02", "B04", "B05", "B06", "B07", "B08"):
    data = load_scene(code)
    scene = reset()
    scene.render.resolution_x = 900
    scene.render.resolution_y = 560
    scene.cycles.samples = 48
    edge = material("edge", EDGE_COLOR, 0.9)
    for c in data["components"]:
        tone = PART_TONES.get(c["role"], PART_TONES["chassis"])
        if c["id"] == "target":
            tone = PART_TONES["service_module"]
        add_solid(c["id"], c, material(f"m.{c['id']}", tone), edge)
    low, high = scene_bounds(data)
    center = [(a + b) / 2 for a, b in zip(low, high)]
    size = max(b - a for a, b in zip(low, high))
    add_ground(low[2] - 0.05)
    add_lights(center, size)
    camera = add_camera(70)
    place_camera(camera, center, -58, 28, size * 2.55)
    out = BUILD / "quicklook" / f"{code}.png"
    out.parent.mkdir(exist_ok=True)
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
