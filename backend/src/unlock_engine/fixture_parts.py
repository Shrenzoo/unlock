"""Detailed synthetic part geometry for the gallery fixtures. Authored here.

Every builder returns one closed solid whose bounding box starts at the origin, so
fixtures place parts by lower corner. The planner proves motion with bounding
boxes, so a part that moves (a target) keeps the exact box of the block it
replaced and carries its detail inside it.

Detail has a cost: import, verification and preview evaluate exact BRep distance
between every pair of parts and tessellate every face, inside fixed time budgets.
Distance is slow between many parallel flat faces (fins, louvers, combs) and
between parallel cylinders, so repeated features stay few and small, and large
round parts avoid sharing an axis with the screws.
"""

import math

import cadquery as cq

V = cq.Vector


def box(w, d, h, x=0, y=0, z=0):
    return cq.Solid.makeBox(w, d, h, V(x, y, z))


def cyl(r, h, x=0, y=0, z=0, axis=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, h, V(x, y, z), V(*axis))


def hexagon(across_flats, h, x=0, y=0, z=0):
    wp = cq.Workplane().polygon(6, across_flats / math.cos(math.pi / 6)).extrude(h)
    return wp.val().translate(V(x, y, z))


def rounded(w, d, h, r, x=0, y=0, z=0):
    wp = cq.Workplane().box(w, d, h, centered=False).edges("|Z").fillet(r)
    return wp.val().translate(V(x, y, z))


def fuse(first, *rest):
    return first.fuse(*rest).clean() if rest else first


def cut(shape, *tools):
    return shape.cut(*tools).clean() if tools else shape


def turn(shape, degrees, axis=(0, 0, 1)):
    return shape.rotate(V(0, 0, 0), V(*axis), degrees)


def settle(shape):
    """One solid, moved so its bounding box starts at the origin."""
    solids = shape.Solids()
    if len(solids) != 1:
        raise ValueError(f"a fixture part must be one solid, not {len(solids)}")
    b = solids[0].BoundingBox()
    return solids[0].translate(V(-b.xmin, -b.ymin, -b.zmin))


# --- chassis ---------------------------------------------------------------


def plate(w, d, t=3, corner=6, holes=(), slots=(), pockets=()):
    """Base plate: rounded corners, through holes and slots, shallow pockets."""
    tools = [cyl(r, t + 2, x, y, -1) for x, y, r in holes]
    for x, y, length, width, angle in slots:
        s = cq.Workplane().slot2D(length, width, angle).extrude(t + 2).val()
        tools.append(s.translate(V(x, y, -1)))
    for x, y, pw, pd, depth in pockets:
        r = min(2.0, pw / 4, pd / 4)
        tools.append(rounded(pw, pd, depth + 1, r, x - pw / 2, y - pd / 2, t - depth))
    return settle(cut(rounded(w, d, t, corner), *tools))


def vented_wall(t=4, d=80, h=24, columns=7, lip=1):
    """Side panel with two rows of round vents and a stiffening lip on one face."""
    lip_x = t if lip > 0 else -2
    wall = fuse(box(t, d, h), box(2, d, 2, lip_x, 0, h - 2), box(2, d, 2, lip_x, 0, 0))
    pitch = (d - 16) / (columns - 1)
    vents = [
        cyl(2.2, t + 2, -1, 8 + i * pitch, z, (1, 0, 0))
        for i in range(columns)
        for z in (h * 0.36, h * 0.66)
    ]
    return settle(cut(wall, *vents))


def hat_rail(length=90, width=7.5, height=4, t=0.8, channel=5):
    """Top-hat mounting rail with a slotted base."""
    a, b = (width - channel) / 2, (width + channel) / 2
    rail = fuse(
        box(length, a + t, t, 0, 0, height - t),
        box(length, width - b + t, t, 0, b - t, height - t),
        box(length, t, height, 0, a, 0),
        box(length, t, height, 0, b - t, 0),
        box(length, channel, t, 0, a, 0),
    )
    slots = []
    for i in range(int(length // 15)):
        s = cq.Workplane().slot2D(8, 2.2).extrude(t + 2).val()
        slots.append(s.translate(V(7.5 + i * 15, width / 2, -1)))
    return settle(cut(rail, *slots))


def standoff(across_flats=5, h=12):
    body = fuse(
        hexagon(across_flats, h - 1.5), cyl(across_flats * 0.35, 1.5, 0, 0, h - 1.5)
    )
    return settle(cut(body, cyl(1.1, 3, 0, 0, h - 2.5)))


def cradle(w=48, d=26, h=13.5, saddles=2):
    """Support rack: two side rails and chamfered saddles with bolt holes."""
    rails = [box(w, 3, 3, 0, y, 0) for y in (0, d - 3)]
    pitch = (w - 4) / (saddles - 1)
    tops = [
        cq.Workplane()
        .box(4, d, h, centered=False)
        .edges(">Z and |Y")
        .chamfer(1.2)
        .val()
        .translate(V(i * pitch, 0, 0))
        for i in range(saddles)
    ]
    bolts = [
        cyl(1.1, 5, i * pitch + 2, y, -1)
        for i in range(saddles)
        for y in (1.5, d - 1.5)
    ]
    return settle(cut(fuse(*rails, *tops), *bolts))


def pedestal(w=20, d=12, h=15.5, saddle=(16, 6)):
    """Bolted pedestal: flange, round column with collar, saddle plate."""
    flange = cut(
        rounded(w, d, 2, 2),
        cyl(1.3, 4, 2.5, d / 2, -1),
        cyl(1.3, 4, w - 2.5, d / 2, -1),
    )
    column = fuse(
        cyl(3, h - 1.5, w / 2, d / 2, 0),
        cyl(4, 2, w / 2, d / 2, 2),
        cyl(3.6, 1.2, w / 2, d / 2, h - 4),
    )
    sw, sd = saddle
    top = box(sw, sd, 1.5, w / 2 - sw / 2, d / 2 - sd / 2, h - 1.5)
    return settle(fuse(flange, column, top))


def shield_can(w=22, d=22, h=40.2, wall=0.6, top=0.2):
    """Open-bottom EMI shield can: thin top sheet, plain walls, solder tabs."""
    can = cut(box(w, d, h), box(w - 2 * wall, d - 2 * wall, h - top, wall, wall, -1))
    tabs = [box(4, 2, 0.6, w / 2 - 2, y, 0) for y in (-1.4, d - 0.6)]
    return settle(fuse(can, *tabs))


def enclosure(w=26, d=16, h=23.5, wall=2):
    """Open-top service compartment with hinge knuckles and feet."""
    body = cut(
        rounded(w, d, h, 2), rounded(w - 2 * wall, d - 2 * wall, h, 1, wall, wall, 3)
    )
    knuckles = [cyl(1.4, 4, x, d - 0.2, h - 1.4, (1, 0, 0)) for x in (3, w - 7)]
    feet = [box(4, d, 1.2, x, 0, 0) for x in (2, w - 6)]
    return settle(fuse(body, *knuckles, *feet))


# --- electronics -------------------------------------------------------------


def pcb(w, d, parts=(), t=1.6):
    """Board with mounting holes and fused components: ics, caps, headers, finned sinks."""
    shapes, marks = [], []
    for kind, x, y, *size in parts:
        if kind == "ic":
            cw, cd, ch = size
            shapes.append(rounded(cw, cd, ch, 0.3, x, y, t))
            marks.append(cyl(0.45, 0.4, x + 1, y + 1, t + ch - 0.2))
        elif kind == "cap":
            r, ch = size
            shapes += [cyl(r, ch, x, y, t), cyl(r * 0.6, 0.4, x, y, t + ch)]
        elif kind == "header":
            n, pitch = size
            shapes.append(box(n * pitch, 2.5, 2.5, x, y, t))
            shapes += [
                box(0.64, 0.64, 6, x + pitch / 2 - 0.32 + i * pitch, y + 0.93, t)
                for i in range(n)
            ]
        elif kind == "sink":
            sw, sd, sh, fins = size
            step = (sw - 1) / (fins - 1)
            shapes += [box(sw, sd, 1.5, x, y, t)] + [
                box(1, sd, sh, x + i * step, y, t) for i in range(fins)
            ]
        elif kind == "conn":
            cw, cd, ch = size
            shapes.append(
                cut(
                    box(cw, cd, ch, x, y, t),
                    box(cw - 1.6, cd, ch - 1.6, x + 0.8, y - 1, t + 0.8),
                )
            )
    holes = [cyl(1.3, t + 2, hx, hy, -1) for hx in (3, w - 3) for hy in (3, d - 3)]
    return settle(cut(fuse(cut(box(w, d, t), *holes), *shapes), *marks))


def motor(length=44, r=12):
    """Foot-mounted motor along +X: banded can, end bell, shaft, fan cover, terminal box."""
    yc = zc = r + 5
    can = cyl(r, length, 10, yc, zc, (1, 0, 0))
    band = cyl(r + 1, 2.5, 16, yc, zc, (1, 0, 0))
    front = cyl(r * 0.82, 6, 4, yc, zc, (1, 0, 0))
    shaft = cyl(2.5, 13, -9, yc, zc, (1, 0, 0))
    rear = cyl(r + 1.5, 8, 10 + length, yc, zc, (1, 0, 0))
    x0 = 10 + length * 0.3
    tbox = fuse(
        box(16, 13, 8, x0, yc - 6.5, zc + r - 2),
        cyl(1.8, 3, x0 + 8, yc + 6.5, zc + r + 2, (0, 1, 0)),
    )
    cradles = [box(6, 2 * r - 4, zc, x, yc - r + 2, 0) for x in (14, length)]
    bolts = [
        cyl(1.8, 5, x, y, -1)
        for x in (14, length + 10)
        for y in (yc - r - 1.5, yc + r + 1.5)
    ]
    foot = cut(box(length + 4, 2 * r + 10, 3, 10, yc - r - 5, 0), *bolts)
    return settle(fuse(can, band, front, shaft, rear, tbox, *cradles, foot))


def battery(w=44, d=22, h=16):
    """Battery module: rounded case, recessed lid with vents, two terminal posts."""
    case = cut(
        rounded(w, d, h - 2.5, 2.5),
        rounded(w - 5, d - 5, 1.5, 1.5, 2.5, 2.5, h - 3.3),
        box(w * 0.5, 1, 2.5, w * 0.25, -0.2, h * 0.35),
        box(w * 0.5, 1, 2.5, w * 0.25, d - 0.8, h * 0.35),
    )
    vents = [
        cyl(1.4, 0.6, w * 0.38 + i * 6, d / 2 + j * 5 - 2.5, h - 3.3)
        for i in range(2)
        for j in range(2)
    ]
    posts = [
        fuse(hexagon(5.5, 0.8, x, d / 2, h - 2.5), cyl(2.2, 2.5, x, d / 2, h - 2.5))
        for x in (5.5, w - 5.5)
    ]
    return settle(fuse(case, *vents, *posts))


def relay(w=14, d=14, h=12):
    """Plug-in relay: chamfered cover, label recess, polarity dot, round pins, test button."""
    body = (
        cq.Workplane()
        .box(w, d, h - 3, centered=False)
        .edges(">Z")
        .chamfer(0.8)
        .val()
        .translate(V(0, 0, 3))
    )
    body = cut(
        body, rounded(w - 5, d - 6, 1, 1, 2.5, 3, h - 0.4), cyl(0.5, 1, 2, 2, h - 0.5)
    )
    spots = (
        (2.5, 2.5),
        (w - 2.5, 2.5),
        (2.5, d - 2.5),
        (w - 2.5, d - 2.5),
        (w / 2, d / 2),
    )
    pins = [cyl(0.45, 3.4, x, y, 0) for x, y in spots]
    return settle(fuse(body, *pins, cyl(1.4, 0.8, w - 3, 3, h - 0.4)))


def terminal_block(n=6, pitch=4, d=10, h=8):
    """Row of screw terminals with round wire entries, slotted screws and a marker strip."""
    body = (
        cq.Workplane()
        .box(n * pitch, d, h - 1.5, centered=False)
        .edges(">Z and |X")
        .chamfer(1.2)
        .val()
    )
    wells = [cyl(1.25, 3, i * pitch + pitch / 2, d * 0.62, h - 4) for i in range(n)]
    entries = [
        cyl(1.1, 4, i * pitch + pitch / 2, -0.5, 3.2, (0, 1, 0)) for i in range(n)
    ]
    body = cut(body, *wells, *entries)
    screws = [
        cut(
            cyl(1.0, 2.2, i * pitch + pitch / 2, d * 0.62, h - 4.2),
            box(2.4, 0.4, 0.5, i * pitch + pitch / 2 - 1.2, d * 0.62 - 0.2, h - 2.5),
        )
        for i in range(n)
    ]
    marker = box(n * pitch, 1.6, 1.5, 0, d * 0.05, h - 1.5)
    return settle(fuse(body, *screws, marker))


def fan(size=30, depth=12, blades=7):
    """Axial fan: frame with venturi bore and corner holes, hub, struts, pitched blades."""
    c = size / 2
    bore = c - 1.2
    corners = [
        cyl(1.6, depth + 2, x, y, -1)
        for x in (3.2, size - 3.2)
        for y in (3.2, size - 3.2)
    ]
    frame = cut(
        rounded(size, size, depth, 2.5), cyl(bore, depth + 2, c, c, -1), *corners
    )
    hub_r = size * 0.17
    hub = fuse(cyl(hub_r, depth - 2, c, c, 1), cyl(hub_r * 0.7, 0.6, c, c, depth - 1))
    struts = [
        turn(box(c, 1.4, 1.6, 0, -0.7, 0), 90 + 120 * k).translate(V(c, c, 0))
        for k in range(3)
    ]
    span = bore - 0.8 - (hub_r - 0.6)
    blade = turn(box(span, 7, 1.0, hub_r - 0.6, -3.5, -0.5), 32, (1, 0, 0)).translate(
        V(0, 0, depth / 2)
    )
    blade_set = [
        turn(blade, 360 * k / blades).translate(V(c, c, 0)) for k in range(blades)
    ]
    return settle(fuse(frame, hub, *struts, *blade_set))


def gland(r=4.5):
    """Cable gland: hex body, thread ring, dome nut and cable stub."""
    return settle(
        fuse(
            hexagon(2 * r + 2, 3),
            cyl(r + 0.4, 1.2, 0, 0, 3),
            cyl(r, 3.5, 0, 0, 4.2),
            hexagon(2 * r, 3, 0, 0, 7.7),
            cyl(r * 0.75, 1.6, 0, 0, 10.7),
            cyl(r * 0.4, 5, 0, 0, 12.3),
        )
    )


def antenna(height=40):
    """Whip antenna: threaded base, nut, knuckle and whip."""
    return settle(
        fuse(
            cyl(4.5, 3.2),
            hexagon(7, 2.2, 0, 0, 3),
            cyl(2.2, 4.5, 0, 0, 5),
            cq.Solid.makeSphere(2.6, V(0, 0, 10), angleDegrees1=-90),
            cyl(1.1, height - 13, 0, 0, 11),
            cyl(1.6, 2, 0, 0, height - 3),
        )
    )


def battery_holder(cells=2, r=4.6, length=24):
    """Cradle with cylindrical cells and end contacts."""
    pitch = 2 * r + 1.5
    w = cells * pitch + 1.5
    ys = [1.5 + r + i * pitch for i in range(cells)]
    cradle = cut(
        box(length + 6, w, r + 1),
        *[cyl(r + 0.2, length, 3, y, r + 2, (1, 0, 0)) for y in ys],
    )
    ends = [box(1.5, w, 2 * r + 2, x, 0, 0) for x in (0, length + 4.5)]
    cells_ = [cyl(r, length - 1, 3.5, y, r + 2, (1, 0, 0)) for y in ys]
    caps = [cyl(r * 0.35, 1.2, 2.5, y, r + 2, (1, 0, 0)) for y in ys]
    return settle(fuse(cradle, *ends, *cells_, *caps))


def connector(w=12, d=10, h=9):
    """Power connector housing with two contact sockets, a latch and a cable boot."""
    body = cq.Workplane().box(w, d, h, centered=False).edges("|Y").chamfer(0.8).val()
    body = cut(
        body,
        box(3.4, 6, 3.4, 1.8, -1, h * 0.35),
        box(3.4, 6, 3.4, w - 5.2, -1, h * 0.35),
    )
    contacts = [box(1.2, 4, 1.2, x, 1, h * 0.35 + 1.1) for x in (2.9, w - 4.1)]
    latch = fuse(
        box(5, 4, 1.2, w / 2 - 2.5, 2, h), box(5, 1.2, 1.4, w / 2 - 2.5, 2, h + 1.2)
    )
    boot = cyl(3, 4, w / 2, d, h / 2, (0, 1, 0))
    return settle(fuse(body, *contacts, latch, boot))


def fuse_holder(length=22, w=9):
    """Bolted fuse carrier: base, end blocks, cartridge fuse with caps and nuts."""
    base = cut(
        box(length, w, 2.5),
        cyl(1.4, 4, 2.5, w / 2, -1),
        cyl(1.4, 4, length - 2.5, w / 2, -1),
    )
    ends = [box(4, w, 7, x, 0, 0) for x in (4, length - 8)]
    body = cyl(2.6, length - 13, 6.5, w / 2, 7.5, (1, 0, 0))
    caps = [cyl(3.0, 2, x, w / 2, 7.5, (1, 0, 0)) for x in (6.5, length - 8.5)]
    nuts = [hexagon(4, 1.5, x, w / 2, 7) for x in (6, length - 6)]
    return settle(fuse(base, *ends, body, *caps, *nuts))


def duct(length=110, w=8, h=8):
    """Wiring duct, open on top, with round cable exits through both walls."""
    body = cut(box(length, w, h), box(length + 2, w - 2, h, -1, 1, 1))
    exits = [
        cyl(1.8, w + 2, 10 + i * 20, -1, h * 0.62, (0, 1, 0))
        for i in range(int((length - 10) // 20))
    ]
    return settle(cut(body, *exits))


def power_inlet(w=20, d=12, h=14):
    """Panel power inlet: body, flange with holes, keyed socket and three pins."""
    flange = cut(
        box(w + 6, 2, h + 4, -3, 0, -2),
        *[cyl(1.3, 4, x, -1, h / 2, (0, 1, 0)) for x in (-1, w + 1)],
    )
    outline = [(4, 3), (16, 3), (16, 9), (13, 11), (7, 11), (4, 9)]
    socket = (
        cq.Workplane("XZ")
        .polyline(outline)
        .close()
        .extrude(-7)
        .val()
        .translate(V(0, -1, 0))
    )
    body = cut(fuse(box(w, d, h, 0, 2, 0), flange), socket)
    pins = [box(1, 4, 2.4, x, 2, z) for x, z in ((6.5, 5), (12.5, 5), (9.5, 7.5))]
    return settle(fuse(body, *pins))


# --- fluid -------------------------------------------------------------------


def tank(r=11, length=30):
    """Horizontal coolant tank along +Y on two saddles: chamfered heads, band, filler cap,
    sight window and outlet. Its axis is deliberately unlike the motor's and the screws'."""
    xc, zc = r + 2, r + 3
    shell = (
        cq.Workplane()
        .add(cyl(r, length, xc, 0, zc, (0, 1, 0)))
        .edges()
        .chamfer(2.5)
        .val()
    )
    shell = cut(shell, box(2, 12, 5, xc + r - 1.2, length / 2 - 6, zc - 2.5))
    saddles = [box(2 * xc, 4, zc, 0, y, 0) for y in (5, length - 9)]
    band = cyl(r + 0.8, 3, xc, length / 2 - 1.5, zc, (0, 1, 0))
    neck = fuse(
        cyl(3.5, 4, xc, length * 0.3, zc + r - 1),
        cyl(4.5, 3, xc, length * 0.3, zc + r + 3),
    )
    outlet = fuse(
        cyl(2, 6, xc + r - 1, length * 0.75, zc - 4, (1, 0, 0)),
        cyl(2.6, 1.2, xc + r + 3, length * 0.75, zc - 4, (1, 0, 0)),
    )
    return settle(fuse(shell, *saddles, band, neck, outlet))


def port(r=4, length=18):
    """Bulkhead pipe port along +X: bolted mounting block, hex nut, pipe, barb, bore."""
    c = r + 4
    block = cut(
        box(8, 2 * c, 2 * c),
        *[
            cyl(1.2, 10, -1, y, z, (1, 0, 0))
            for y, z in ((2.5, 2.5), (2 * c - 2.5, 2 * c - 2.5))
        ],
    )
    nut = (
        cq.Workplane("YZ")
        .polygon(6, (2 * r + 3) / math.cos(math.pi / 6))
        .extrude(4)
        .val()
        .translate(V(8, c, c))
    )
    pipe = cyl(r, length - 8, 8, c, c, (1, 0, 0))
    barb = cyl(r + 0.7, 1.5, length - 4, c, c, (1, 0, 0))
    return settle(
        cut(fuse(block, nut, pipe, barb), cyl(r - 1.5, 8, length - 6, c, c, (1, 0, 0)))
    )


# --- service targets: exact w x d x h bounding box ----------------------------


def cartridge(w=20, d=10, h=22):
    """Pump cartridge: chamfered body, cross-axis pump head, ports, lifting handle."""
    body = cq.Workplane().box(w, d, 15, centered=False).edges("|Z").chamfer(1.2).val()
    body = cut(body, *[cyl(0.45, w - 4, 2, 0, z, (1, 0, 0)) for z in (4, 7, 10)])
    head = cyl(4.5, d - 1, w / 2, 0.5, 15, (0, 1, 0))
    ports = [
        fuse(hexagon(3.6, 1.2, x, d / 2, 15), cyl(1.4, 3.5, x, d / 2, 15))
        for x in (3.2, w - 3.2)
    ]
    handle = fuse(
        box(1.6, 3, 7, 2.4, d / 2 - 1.5, 15),
        box(1.6, 3, 7, w - 4, d / 2 - 1.5, 15),
        box(w - 4.8, 3, 1.6, 2.4, d / 2 - 1.5, h - 1.6),
    )
    return settle(fuse(body, head, *ports, handle))


def sensor_pod(w=14, d=4, h=10):
    """Sensor pod: rounded housing, lens bezel facing -Y, status LED, cable boss."""
    body = rounded(w, d - 1.2, h - 2.5, 1.2, 0, 1.2, 0)
    bezel = cut(
        cyl(3, 1.2, w / 2, 1.2, 4, (0, -1, 0)),
        cyl(2.1, 0.6, w / 2, -0.01, 4, (0, 1, 0)),
    )
    led = cyl(0.6, 0.6, 2.5, 1.2, 6.2, (0, -1, 0))
    boss = fuse(cyl(1.4, 2.5, w / 2, 2.3, h - 2.5), cyl(1.65, 0.6, w / 2, 2.3, h - 2.5))
    ribs = [box(0.5, d - 1.2, 0.5, x, 1.2, 0.8) for x in (1.5, w - 2)]
    return settle(fuse(body, bezel, led, boss, *ribs))


def hatch(w=20, d=10, t=2):
    """Service hatch: rounded plate, counterbored holes, finger grip, stiffening grooves."""
    body = cq.Workplane().box(w, d, t, centered=False).edges("|Z").fillet(1).val()
    holes = [
        fuse(cyl(0.9, t + 2, x, d / 2, -1), cyl(1.7, 1, x, d / 2, t - 0.8))
        for x in (2.2, w - 2.2)
    ]
    grip = (
        cq.Workplane()
        .slot2D(w * 0.4, 1.6)
        .extrude(1)
        .val()
        .translate(V(w / 2, d - 2.2, t - 0.8))
    )
    grooves = [cyl(0.35, w - 8, 4, y, t, (1, 0, 0)) for y in (2.5, 4.2)]
    return settle(cut(body, *holes, grip, *grooves))


def filter_cartridge(w=40, d=24, h=14, pleats=10):
    """Filter cartridge: rim frame, pleated media, support bars, pull tab."""
    rim_h = h - 2
    frame = cut(box(w, d, rim_h), box(w - 4, d - 4, rim_h + 2, 2, 2, -1))
    pts = [
        (1.5 + i * (w - 3) / pleats, 1.5 if i % 2 == 0 else rim_h - 1.5)
        for i in range(pleats + 1)
    ]
    outline = pts + [(x, z - 0.7) for x, z in reversed(pts)]
    media = (
        cq.Workplane("XZ")
        .polyline(outline)
        .close()
        .extrude(-(d - 2))
        .val()
        .translate(V(0, 1, 0))
    )
    bars = [
        box(w - 2, 1.2, 1.2, 1, d / 2 - 0.6, 0),
        box(1.2, d - 2, 1.2, w / 2 - 0.6, 1, 0),
    ]
    tab = fuse(
        box(10, 2, 1.2, w / 2 - 5, 0, rim_h), box(10, 0.8, 2, w / 2 - 5, 0, rim_h)
    )
    return settle(fuse(frame, media, *bars, tab))


PARTS = dict(
    plate=plate,
    vented_wall=vented_wall,
    hat_rail=hat_rail,
    standoff=standoff,
    cradle=cradle,
    pedestal=pedestal,
    shield_can=shield_can,
    enclosure=enclosure,
    pcb=pcb,
    motor=motor,
    battery=battery,
    relay=relay,
    terminal_block=terminal_block,
    fan=fan,
    gland=gland,
    antenna=antenna,
    battery_holder=battery_holder,
    connector=connector,
    fuse_holder=fuse_holder,
    duct=duct,
    power_inlet=power_inlet,
    tank=tank,
    port=port,
    cartridge=cartridge,
    sensor_pod=sensor_pod,
    hatch=hatch,
    filter_cartridge=filter_cartridge,
)
