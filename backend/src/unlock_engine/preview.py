"""Disposable, explicitly scaled presentation assets; never verification inputs."""

from .contracts import EngineError, POLICY


def preview_meshes(shapes, linear_deflection_mm=0.1, angular_deflection_rad=0.1):
    components = []
    total = 0
    for id, shape in sorted(shapes.items()):
        # OCCT attaches triangulations to topology; mesh a private copy.
        vertices, triangles = shape.copy().tessellate(
            linear_deflection_mm, angular_deflection_rad
        )
        total += len(triangles)
        if total > POLICY.max_triangles:
            raise EngineError("LIMIT_EXCEEDED", "preview exceeds 200,000 triangles")
        components.append(
            dict(
                occurrence_id=id,
                vertices_m=[tuple(v * 0.001 for v in p.toTuple()) for p in vertices],
                triangles=triangles,
            )
        )
    return dict(
        authoritative=False,
        units="m",
        frame=dict(handedness="right", up="Z"),
        scale_from_cad_mm=0.001,
        scale_already_applied=True,
        linear_deflection_mm=linear_deflection_mm,
        angular_deflection_rad=angular_deflection_rad,
        triangle_count=total,
        components=components,
    )
