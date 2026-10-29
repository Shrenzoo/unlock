"""OCCT evidence. A failed Boolean/distance is an error, never empty space."""

from __future__ import annotations

import hashlib
import io
import math
from collections import OrderedDict
from copy import deepcopy

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepTools import BRepTools
from OCP.TopTools import TopTools_FormatVersion
from OCP.gp import gp_Trsf

from .contracts import Box, EngineError, Finding, POLICY, Status, Transform, digest

# Cache only internally computed validity evidence for byte-identical BReps under
# the complete policy. Each isolated verifier starts with an empty cache. The
# cache stores no shapes, pass flags from callers, or Boolean/path results.
_VALIDITY_CACHE = OrderedDict()
_VALIDITY_CACHE_ENTRIES = 256


def box_shape(b: Box) -> cq.Shape:
    return cq.Solid.makeBox(
        *(z - a for a, z in zip(b.min, b.max)), pnt=cq.Vector(*b.min)
    )


def bounds(shape: cq.Shape) -> Box:
    b = shape.BoundingBox()
    return Box(min=(b.xmin, b.ymin, b.zmin), max=(b.xmax, b.ymax, b.zmax))


def fingerprint(shape: cq.Shape) -> str:
    stream = io.BytesIO()
    BRepTools.Write_s(
        shape.wrapped,
        stream,
        False,
        False,
        TopTools_FormatVersion.TopTools_FormatVersion_VERSION_3,
    )
    return hashlib.sha256(stream.getvalue()).hexdigest()


def validate_solid(shape: cq.Shape) -> dict:
    try:
        if shape is None or shape.wrapped.IsNull():
            raise ValueError("null shape")
        key = (fingerprint(shape), digest(POLICY))
        if key in _VALIDITY_CACHE:
            _VALIDITY_CACHE.move_to_end(key)
            return deepcopy(_VALIDITY_CACHE[key])
        if not BRepCheck_Analyzer(shape.wrapped, True).IsValid():
            raise ValueError("OCCT BRepCheck invalid")
        solids = shape.Solids()
        if len(solids) != 1:
            raise ValueError(f"expected one closed solid, found {len(solids)}")
        # A compound with a solid plus stray faces/edges is unsupported.
        if len(shape.Faces()) != len(solids[0].Faces()) or len(shape.Edges()) != len(
            solids[0].Edges()
        ):
            raise ValueError("stray unsupported topology")
        if any(not shell.Closed() for shell in solids[0].Shells()):
            raise ValueError("open shell")
        volume = shape.Volume()
        if not math.isfinite(volume) or volume <= POLICY.volume_noise_mm3:
            raise ValueError("nonpositive or nonfinite solid volume")
        b = bounds(shape)
        if len(shape.Faces()) > POLICY.max_faces:
            raise ValueError("face limit exceeded")
        result = dict(
            valid=True,
            volume_mm3=volume,
            faces=len(shape.Faces()),
            bounds_mm=b.model_dump(),
        )
        _VALIDITY_CACHE[key] = deepcopy(result)
        if len(_VALIDITY_CACHE) > _VALIDITY_CACHE_ENTRIES:
            _VALIDITY_CACHE.popitem(last=False)
        return result
    except Exception as exc:
        raise EngineError("INVALID_SOLID", str(exc)) from exc


def boolean(op: str, a: cq.Shape, b: cq.Shape) -> cq.Shape:
    try:
        cls = {
            "common": BRepAlgoAPI_Common,
            "cut": BRepAlgoAPI_Cut,
            "fuse": BRepAlgoAPI_Fuse,
        }[op]
        # OCCT Boolean operations can update tolerances/flags of their arguments.
        # Use private topology and geometry even when the binding exposes a
        # non-destructive mode, so imported revision BReps stay byte-identical.
        worker = cls(a.copy().wrapped, b.copy().wrapped)
        worker.SetNonDestructive(True)
        worker.SetRunParallel(False)
        worker.Build()
        if not worker.IsDone():
            raise ValueError(f"{op} did not complete")
        raw = worker.Shape()
        if raw.IsNull() or not BRepCheck_Analyzer(raw, True).IsValid():
            raise ValueError(f"{op} returned invalid shape")
        return cq.Shape.cast(raw)
    except Exception as exc:
        raise EngineError("GEOMETRY_FAILED", f"Boolean {op}: {exc}") from exc


def volume(shape: cq.Shape) -> float:
    # Empty commons can contain faces/edges. Their material volume is zero.
    v = sum(s.Volume() for s in shape.Solids())
    if not math.isfinite(v) or v < -POLICY.volume_noise_mm3:
        raise EngineError("GEOMETRY_FAILED", "invalid material volume")
    return max(0.0, v)


def difference_volume(a: cq.Shape, b: cq.Shape) -> float:
    return volume(boolean("cut", a, b)) + volume(boolean("cut", b, a))


def same_geometry(a: cq.Shape, b: cq.Shape) -> bool:
    # No intentional 0.01 mm material loss is accepted as equality.
    return difference_volume(a, b) <= POLICY.volume_noise_mm3


def transform(shape: cq.Shape, t: Transform) -> cq.Shape:
    m = t.matrix
    tr = gp_Trsf()
    tr.SetValues(*m[:12])
    return shape.moved(cq.Location(tr))


def inverse(t: Transform) -> Transform:
    m = t.matrix
    out = [0.0] * 16
    out[15] = 1.0
    for i in range(3):
        for j in range(3):
            out[i * 4 + j] = m[j * 4 + i]
        out[i * 4 + 3] = -sum(out[i * 4 + j] * m[j * 4 + 3] for j in range(3))
    return Transform(matrix=tuple(out))


def matrix(location) -> Transform:
    t = location.Transformation()
    return Transform(
        matrix=tuple(t.Value(i, j) for i in range(1, 4) for j in range(1, 5))
        + (0.0, 0.0, 0.0, 1.0)
    )


def distance(a: cq.Shape, b: cq.Shape) -> tuple[float, tuple[float, float, float]]:
    w = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    w.Perform()
    if not w.IsDone() or w.NbSolution() < 1:
        raise EngineError("GEOMETRY_FAILED", "minimum distance failed")
    d = w.Value()
    p = w.PointOnShape1(1)
    if not math.isfinite(d):
        raise EngineError("GEOMETRY_FAILED", "nonfinite distance")
    return d, (p.X(), p.Y(), p.Z())


def collision(
    a: cq.Shape, b: cq.Shape, clearance_mm: float = POLICY.clearance_mm, ids=()
) -> Finding:
    if not math.isfinite(clearance_mm) or clearance_mm < 0:
        return Finding(
            status=Status.INVALID,
            kind="invalid_clearance",
            component_ids=ids,
            explanation="clearance must be finite and nonnegative",
        )
    try:
        validate_solid(a)
        validate_solid(b)
        common = boolean("common", a, b)
        v = volume(common)
        if v > POLICY.volume_noise_mm3:
            p = common.Center()
            return Finding(
                status=Status.BLOCKED,
                kind="positive_volume_intersection",
                component_ids=ids,
                intersection_volume_mm3=v,
                witness_mm=p.toTuple(),
                explanation="Completed BRep common contains positive material volume",
            )
        d, p = distance(a, b)
        if d < clearance_mm - POLICY.tolerance_mm:
            return Finding(
                status=Status.BLOCKED,
                kind="insufficient_clearance",
                component_ids=ids,
                distance_mm=d,
                witness_mm=p,
                explanation="BRep gap lies below clearance minus numerical guard",
            )
        if d <= clearance_mm + POLICY.tolerance_mm:
            return Finding(
                status=Status.UNKNOWN,
                kind="numerical_boundary",
                component_ids=ids,
                distance_mm=d,
                witness_mm=p,
                explanation="Gap is inside numerical guard; tangency requires a validated contact declaration",
            )
        return Finding(
            status=Status.CLEAR,
            kind="separated",
            component_ids=ids,
            distance_mm=d,
            witness_mm=p,
            explanation="BRep minimum gap exceeds threshold plus numerical guard",
        )
    except Exception as exc:
        return Finding(
            status=Status.UNKNOWN,
            kind="kernel_failure",
            component_ids=ids,
            explanation=str(exc),
        )


def cover(shape: cq.Shape, boxes: tuple[Box, ...]) -> bool:
    """Revalidate every supplied decomposition against the actual BRep, with no trust flag."""
    if not boxes:
        return False
    try:
        residue = shape
        for box in boxes:
            residue = boolean("cut", residue, box_shape(box))
        return volume(residue) <= POLICY.volume_noise_mm3
    except EngineError:
        return False


def material_boxes(
    shape: cq.Shape, proposed: tuple[Box, ...] | None = None
) -> tuple[Box, ...]:
    boxes = (
        proposed
        if proposed is not None
        else (bounds(shape).inflate(POLICY.tolerance_mm),)
    )
    if not cover(shape, boxes):
        raise EngineError("GEOMETRY_FAILED", "proxy material coverage not established")
    return boxes
