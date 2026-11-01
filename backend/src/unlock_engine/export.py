"""Genuine solid/assembly STEP export, independent reimport, and evidence packaging."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile

import cadquery as cq

from .artifacts import ArtifactStore, atomic_write
from .assembly import export_assembly, import_step
from .contracts import EngineError, POLICY, digest
from .geometry import (
    boolean,
    bounds,
    difference_volume,
    fingerprint,
    same_geometry,
    validate_solid,
    volume,
)
from .preview import preview_meshes
from .fixture_license import license_files
from .service import Candidate, Revision, shapes_hash
from .verification import UNVERIFIED, verify_candidate


def export_bundle(revision: Revision, candidate: Candidate, output_root: Path):
    report = verify_candidate(revision, candidate)
    # Geometry inspection exports are useful, but do not masquerade as verified handoff.
    if report.status != "passed":
        raise EngineError(
            "VERIFICATION_UNKNOWN"
            if report.status == "unknown"
            else "CONSTRAINT_VIOLATION",
            "candidate has no current passing independent geometry report",
        )
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore(output_root / "artifacts")
    files = {}

    def save(name, data):
        if not isinstance(data, bytes):
            data = json.dumps(data, sort_keys=True, indent=2, allow_nan=False).encode()
        files[name] = store.put(data)

    with tempfile.TemporaryDirectory(prefix=".export-", dir=output_root) as tmp:
        work = Path(tmp)
        changed = work / "changed_bracket.step"
        cq.exporters.export(candidate.shapes[candidate.bracket_id].copy(), str(changed))
        if not changed.exists() or not changed.stat().st_size:
            raise EngineError("GEOMETRY_FAILED", "changed-part writer produced no STEP")
        imported_part = cq.importers.importStep(str(changed)).val()
        validate_solid(imported_part)
        if not same_geometry(imported_part, candidate.shapes[candidate.bracket_id]):
            raise EngineError(
                "GEOMETRY_FAILED", "changed-part round trip geometry mismatch"
            )
        save("changed_bracket.step", changed.read_bytes())
        save("original.step", revision.assembly.source_step)
        revised_manifest = revision.manifest.model_dump(mode="json")
        for component in revised_manifest["components"]:
            component["bounds_mm"] = bounds(
                candidate.shapes[component["id"]]
            ).model_dump(mode="json")
        save("manifest.json", revised_manifest)
        save("template_parameters.json", candidate.record())
        save("verification.json", report.model_dump(mode="json"))
        save("paths.json", list(report.path_certificates))
        original = revision.by_id()[candidate.bracket_id].shape
        modified = candidate.shapes[candidate.bracket_id]
        removed = boolean("cut", original, modified)
        added = boolean("cut", modified, original)
        diff = dict(
            changed_component_id=candidate.bracket_id,
            removed_volume_mm3=volume(removed),
            added_volume_mm3=volume(added),
            symmetric_difference_mm3=difference_volume(original, modified),
            region_mm=bounds(removed).model_dump()
            if removed.Solids()
            else bounds(added).model_dump(),
            original_geometry_hash=fingerprint(original),
            revised_geometry_hash=fingerprint(modified),
            protected_unchanged=["feet", "posts", "hole_material_and_void_regions"],
        )
        save("geometry_difference.json", diff)
        save("preview.json", preview_meshes(candidate.shapes))
        full = False
        roundtrip = {}
        try:
            revised = work / "revised.step"
            replacements = {
                revision.by_id()[candidate.bracket_id].source_occurrence_path: modified
            }
            export_assembly(revision.assembly, revised, replacements)
            imported = import_step(revised)
            mapping = {o.source_occurrence_path: o for o in imported.occurrences}
            expected = revision.by_id()
            if set(mapping) != {o.source_occurrence_path for o in expected.values()}:
                raise ValueError("roundtrip occurrence hierarchy mismatch")
            shapes = {
                k: mapping[o.source_occurrence_path].shape for k, o in expected.items()
            }
            placement_checks = {
                k: max(
                    abs(a - b)
                    for a, b in zip(
                        mapping[o.source_occurrence_path].placement.matrix,
                        o.placement.matrix,
                    )
                )
                for k, o in expected.items()
            }
            if any(v > POLICY.algebraic_tolerance for v in placement_checks.values()):
                raise ValueError("roundtrip placement mismatch")
            diffs = {
                k: difference_volume(shapes[k], candidate.shapes[k]) for k in shapes
            }
            if any(v > POLICY.volume_noise_mm3 for v in diffs.values()):
                raise ValueError(f"roundtrip material mismatch {diffs}")
            gh = shapes_hash(shapes)
            cid = digest(
                [
                    revision.input_hash,
                    candidate.constraint_hash,
                    candidate.bracket_id,
                    candidate.template_id,
                    dict(candidate.parameters),
                    gh,
                    POLICY.model_dump(),
                ]
            )
            reimported = replace(
                candidate,
                id=cid,
                shapes=shapes,
                geometry_hash=gh,
                placements={
                    k: mapping[o.source_occurrence_path].placement
                    for k, o in expected.items()
                },
            )
            independent = verify_candidate(revision, reimported)
            if independent.status != "passed":
                raise ValueError(
                    "reimported candidate independent constraints/path recheck did not pass: "
                    + str(
                        [
                            (c.constraint_id, c.result)
                            for c in independent.checks
                            if c.result != "pass"
                        ]
                    )
                )
            full = True
            roundtrip = dict(
                status="passed",
                occurrences=len(mapping),
                placements_max_difference=placement_checks,
                symmetric_differences_mm3=diffs,
                independent_verification=independent.model_dump(mode="json"),
                shared_definition_count=len(
                    {o.definition_id for o in imported.occurrences}
                ),
                identity_policy="semantic IDs map to structural source occurrence paths; source-byte-derived native IDs change across STEP files",
            )
            save("revised.step", revised.read_bytes())
        except Exception as exc:
            roundtrip = dict(
                status="failed", explanation=str(exc), changed_part_roundtrip="passed"
            )
        save("roundtrip.json", roundtrip)
        save(
            "metrics.json",
            dict(
                modified_occurrences=1,
                removed_volume_mm3=diff["removed_volume_mm3"],
                added_volume_mm3=diff["added_volume_mm3"],
                baseline_operations=None,
                revised_operations=None,
                note="No disassembly search is integrated; operation metrics and complete route feasibility are unmeasured.",
            ),
        )
        summary = (
            "UNLOCK synthetic geometry engineering evidence\n"
            + (
                "Full assembly STEP round trip passed.\n"
                if full
                else "CHANGED PART ONLY: full assembly export/verification FAILED.\n"
            )
            + "Scope: geometry constraints and requested direct segments, not a complete optimized repair route.\n"
            + "Unverified: "
            + "; ".join(UNVERIFIED)
            + ".\nOriginal source and constructor parameters are included; STEP does not preserve native feature history or mates.\n"
            + "Runtime: CadQuery 2.6.1, cadquery-ocp 7.8.1.1.post1, policy_v1.\nRedistribution rights for fixtures must be confirmed before publication.\n"
        )
        save("limitations.txt", summary.encode())
        save(
            "attribution.txt",
            json.dumps(revision.manifest.provenance.model_dump(), indent=2).encode(),
        )
        for name, data in license_files(revision.manifest.provenance).items():
            save(name, data)
    record = dict(
        status="full_assembly" if full else "changed_part_only",
        candidate_id=candidate.id,
        policy_version=POLICY.version,
        roundtrip_status=roundtrip["status"],
        files=files,
    )
    key = store.put_json(record)
    import zipfile
    import io

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for name, hash in sorted(files.items()):
            z.writestr(name, store.get(hash))
        z.writestr("bundle.json", json.dumps(record, sort_keys=True, indent=2))
    zip_key = store.put(stream.getvalue())
    atomic_write(output_root / f"{key}.zip", stream.getvalue())
    # Publish the completion marker only after every referenced byte and the ZIP
    # are durable. Interrupted native work can leave orphan blobs, never a pass marker.
    atomic_write(
        output_root / f"{key}.bundle.json",
        json.dumps(record, sort_keys=True, indent=2).encode(),
    )
    return dict(
        bundle_id=key,
        zip_artifact_id=zip_key,
        zip_path=str((output_root / f"{key}.zip").resolve()),
        **record,
    )
