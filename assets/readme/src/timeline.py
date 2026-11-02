"""The hero animation as data, shared by the Blender render and the compositor."""

FPS = 20

# name, first frame, last frame (exclusive). Captions come from CAPTIONS below.
BEATS = [
    ("original", 0, 34),
    ("obstruction", 34, 80),
    ("choices", 80, 106),
    ("construct", 106, 136),
    ("verify", 136, 164),
    ("route", 164, 204),
    ("verdict", 204, 242),
]
LAST_FRAME = 242
DISSOLVE_FRAMES = 8

# Every number below is checked against evidence by compose.py before it is drawn.
CAPTIONS = dict(
    original=("Battery pack, lift only.", "fixture B05 · 9 parts · real STEP geometry"),
    obstruction=("A fixed strap blocks the lift.", "no_path_supported · BRep overlap 1,397 mm³ at 12 mm"),
    choices=("The model picks from a finite list.", "T02 offset_y: −12, +12, +24 or +36 mm, and nothing else"),
    construct=("A trusted constructor builds −12 mm.", "Muse Spark 1.3, live · the model writes no geometry"),
    verify=("A separate verifier rebuilds and checks it.", "12 of 12 checks · model claims carry no authority"),
    route=("The pack lifts straight out.", "target TRANSLATE Z+ 80 mm · 4 mm clear"),
    verdict=("Verified, on this geometry.", "replay and reverse passed · not a safety claim"),
)


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (6 * t - 15) + 10)


def ramp(frame, start, end):
    if end <= start:
        return 1.0 if frame >= end else 0.0
    return smooth((frame - start) / (end - start))


def state(frame):
    """Scene state at a frame. Pure, so identical states reuse one render."""
    settle = ramp(frame, 0, 34)
    lift_try = ramp(frame, 38, 52) * (1 - ramp(frame, 80, 90))
    overlap = ramp(frame, 50, 58) * (1 - ramp(frame, 80, 90))
    reveal = ramp(frame, 36, 50) * (1 - ramp(frame, 80, 90))
    choices = ramp(frame, 84, 96) * (1 - ramp(frame, 112, 124))
    web = ramp(frame, 108, 132)
    verified = ramp(frame, 140, 152)
    lift = ramp(frame, 166, 202)
    return dict(
        azimuth=66.0 + 12.0 * (1 - settle),
        elevation=21.0 + 4.0 * (1 - settle),
        distance=1.0 + 0.10 * (1 - settle),
        ghost=round(12.0 * lift_try, 4),
        ghost_alpha=round(min(1.0, lift_try * 4), 4),
        overlap=round(overlap, 4),
        reveal=round(reveal, 4),
        choices=round(choices, 4),
        web=round(web, 4),
        verified=round(verified, 4),
        lift=round(80.0 * lift, 4),
    )
