"""Timeline for the fixture outcome clips, shared by the renderer and the compositor."""

from timeline import ramp

CELL_FPS = 12.5
CELL_FRAMES = 66
ROUTE_MM = 80.0
SCREW_MM = 30.0  # REMOVE_FASTENER distance in the B08 plan.
# B07: offsets from the driver's engaged pose on the screw head (z=14). Its tip stops
# on the fixed shield's top face at z=35.2, the blockage the verifier records.
B07_DRIVER_START_MM = 60.0
B07_DRIVER_STOP_MM = 21.2


def cell_state(code, frame):
    lift = ROUTE_MM * ramp(frame, 34, 56)
    if code in ("B02", "B04", "B06"):
        block = ramp(frame, 4, 10) * (1 - ramp(frame, 18, 26))
        return dict(
            block=round(block, 3),
            block_lift=round(30.0 * ramp(frame, 14, 26), 2),
            cut=1.0 if frame >= 14 else 0.0,
            verified=round(ramp(frame, 26, 33), 3),
            lift=round(lift, 2),
        )
    if code == "B05":
        return dict(
            web=round(ramp(frame, 6, 24), 3),
            verified=round(ramp(frame, 26, 33), 3),
            lift=round(lift, 2),
        )
    if code == "B07":
        descend = ramp(frame, 6, 24)
        return dict(
            driver=round(B07_DRIVER_START_MM + (B07_DRIVER_STOP_MM - B07_DRIVER_START_MM) * descend, 2),
            blocked=round(ramp(frame, 22, 28), 3),
            verified=0.0,
            lift=0.0,
        )
    if code == "B08":
        return dict(
            screw1=round(SCREW_MM * ramp(frame, 4, 15), 2),
            screw2=round(SCREW_MM * ramp(frame, 14, 25), 2),
            verified=0.0,
            lift=round(lift, 2),
        )
    raise ValueError(code)
