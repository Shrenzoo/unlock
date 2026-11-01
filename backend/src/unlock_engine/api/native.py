"""Native coordinator operations. Called exclusively inside the existing worker."""

from __future__ import annotations
import json
from pathlib import Path

from ..artifacts import atomic_write
from ..contracts import EngineError


def run(work: Path, operation):
    from ..service import import_revision, construct_candidate
    from ..preview import preview_meshes

    request = json.loads((work / "request.json").read_text())
    if operation == "http_fixture":
        from ..fixtures import GALLERY, generate_fixture

        code = request["code"]
        if code not in ("B01", "B02", "B03", *GALLERY):
            raise EngineError("INVALID_PACKAGE", "unsupported bundled fixture")
        generate_fixture(work, code)
    revision = import_revision(
        work / "assembly.step", json.loads((work / "manifest.json").read_text())
    )
    if operation in ("http_fixture", "http_import"):
        inv = revision.inventory()
        if revision.manifest is not None:
            preview = preview_meshes({k: o.shape for k, o in revision.by_id().items()})
        else:
            preview = preview_meshes(
                {o.id: o.shape for o in revision.assembly.occurrences}
            )
        atomic_write(
            work / "preview.json", json.dumps(preview, allow_nan=False).encode()
        )
        return dict(inventory=inv)
    if operation == "http_export":
        from ..export import export_bundle
        from ..fixture_license import rights_line
        from ..planning.problem import Problem
        from ..planning.service import plan_problem
        from ..planning.contracts import SearchPolicy

        candidate = construct_candidate(revision, **request["template"])
        if candidate.id != request["candidate_id"]:
            raise EngineError(
                "STALE_REVISION", "export reconstruction differs from checked candidate"
            )
        plan = plan_problem(
            Problem(revision, request["target_id"], SearchPolicy(), candidate=candidate)
        )
        if not plan.replacement_verified:
            raise EngineError(
                "VERIFICATION_UNKNOWN",
                "export candidate did not pass fresh planning and reverse insertion",
            )
        bundle = export_bundle(revision, candidate, work / "export")
        # Keep geometry-only export's scope honest, and attach actual planner evidence.
        import io
        import zipfile

        import hashlib

        with zipfile.ZipFile(bundle["zip_path"]) as source:
            files = {
                name: source.read(name)
                for name in source.namelist()
                if name
                not in ("bundle.json", "metrics.json", "paths.json", "limitations.txt")
            }
        files["paths.json"] = json.dumps(
            plan.model_dump(mode="json"), indent=2
        ).encode()
        files["metrics.json"] = json.dumps(
            dict(
                baseline=request["baseline_metrics"],
                revised=plan.metrics.model_dump(mode="json") if plan.metrics else None,
                comparison=request["comparison"],
            ),
            indent=2,
        ).encode()
        files["ai_run.json"] = json.dumps(request["ai_report"], indent=2).encode()
        files["limitations.txt"] = (
            "UNLOCK checked CAD export\nStatus: "
            + bundle["status"]
            + "; STEP round trip: "
            + bundle["roundtrip_status"]
            + "\nFull deterministic removal replay and reverse insertion passed for the frozen target.\n"
            "Strength, electrical safety, manufacturing feasibility and restored product function were not assessed.\n"
            "STEP does not preserve native feature history or mates.\n"
            + rights_line(
                revision.manifest.provenance,
                "Synthetic fixture rights remain pending author approval.\n",
            )
        ).encode()
        record = dict(
            status=bundle["status"],
            roundtrip_status=bundle["roundtrip_status"],
            candidate_id=candidate.id,
            files={
                name: hashlib.sha256(data).hexdigest() for name, data in files.items()
            },
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name, data in sorted(files.items()):
                out.writestr(name, data)
            out.writestr("bundle.json", json.dumps(record, indent=2))
        atomic_write(work / "checked_export.zip", buf.getvalue())
        return dict(
            status=bundle["status"],
            roundtrip_status=bundle["roundtrip_status"],
            candidate_id=candidate.id,
        )
    raise EngineError("FORBIDDEN", "unsupported coordinator native operation")
