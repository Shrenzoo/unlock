"""Fail closed before making a selected, licensed fixture snapshot public."""

import hashlib
import io
import json
from pathlib import Path
import zipfile

from ..fixture_catalog import EXPECTED
from ..fixture_license import B02_PROVENANCE, GRANTS, license_files, rights_line
from ..contracts import Provenance
from .snapshot import SnapshotStore


def _check_export(store, run, code):
    artifact = run["export"]["artifact_id"]
    if run["export"]["roundtrip_status"] != "passed":
        raise ValueError(f"The selected {code} export is not independently verified")
    with zipfile.ZipFile(io.BytesIO(store.artifacts.get(artifact))) as archive:
        bundle = json.loads(archive.read("bundle.json"))
        if bundle["status"] != "full_assembly" or set(archive.namelist()) != set(
            bundle["files"]
        ) | {"bundle.json"}:
            raise ValueError(f"{code} export inventory is invalid")
        for name, metadata in bundle["files"].items():
            expected = metadata["sha256"] if isinstance(metadata, dict) else metadata
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"{code} export member integrity failed")
        if json.loads(archive.read("manifest.json"))["provenance"] != GRANTS[code]:
            raise ValueError(
                f"{code} export provenance differs from the licensed snapshot"
            )
        for name, data in license_files(Provenance(**GRANTS[code])).items():
            if archive.read(name) != data:
                raise ValueError(
                    f"{code} export licensing notice is missing or changed"
                )
        # The original B02 export predates the rights line; its notice is checked above.
        if code != "B02" and rights_line(Provenance(**GRANTS[code]), None) not in (
            archive.read("limitations.txt").decode()
        ):
            raise ValueError(f"{code} export limitations do not state its license")
    return artifact


def validate_public_b02(root):
    root = Path(root)
    status = json.loads((root / "status.json").read_bytes())
    if status.get("state") != "completed" or status.get("fixture") != "B02":
        raise ValueError("Only a completed original B02 demonstration may be published")
    store = SnapshotStore(root)
    projects, revisions, runs = (store.list(k) for k in ("project", "revision", "run"))
    if (
        len(projects) != 1
        or projects[0]["id"] != "fixture_B02"
        or len(revisions) != 1
        or len(runs) != 1
    ):
        raise ValueError("The public snapshot must contain only the original B02 job")
    revision, run = revisions[0], runs[0]
    if (
        not revision["synthetic"]
        or revision["manifest"]["provenance"] != B02_PROVENANCE
    ):
        raise ValueError("B02 publication requires the documented CC BY 4.0 grant")
    if (
        status.get("live_model")
        or run["model"]["live"]
        or run["outcome"] != "VERIFIED_IMPROVEMENT_FOUND"
    ):
        raise ValueError("Publish only the verified recorded offline B02 demonstration")
    if status.get("export_sha256") != run["export"]["artifact_id"]:
        raise ValueError("The selected B02 export is not independently verified")
    # All downloadable blobs, not just the outer ZIP, must retain their identity.
    for path in (root / "artifacts").glob("*/*"):
        store.artifacts.get(path.name)
    artifact = _check_export(store, run, "B02")
    return dict(run_id=run["id"], export_sha256=artifact, license="CC-BY-4.0")


def validate_public_gallery(root):
    """Every project licensed, offline, one run each, and matching its pre-registered outcome."""
    root = Path(root)
    store = SnapshotStore(root)
    members = json.loads((root / "gallery.json").read_bytes())["members"]
    demo_runs = store.data.get("demo_runs") or {}
    projects, revisions, runs = (store.list(k) for k in ("project", "revision", "run"))
    if (
        {p["id"] for p in projects} != set(demo_runs)
        or len(revisions) != len(projects)
        or len(runs) != len(projects)
        or len(members) != len(projects)
        or store.data["demo_run_id"] != demo_runs.get("fixture_B02")
    ):
        raise ValueError(
            "The gallery must hold exactly one recorded run per project, B02 included"
        )
    for path in (root / "artifacts").glob("*/*"):
        store.artifacts.get(path.name)
    statuses = {m["run_id"]: m for m in members}
    published = {}
    for project in projects:
        code = project["fixture_code"]
        if (
            project["id"] != f"fixture_{code}"
            or code not in GRANTS
            or code not in EXPECTED
        ):
            raise ValueError(f"{project['id']} has no recorded publication grant")
        run = store.get("run", demo_runs[project["id"]])
        revision = store.get("revision", run["revision_id"])
        status = statuses.get(run["id"], {})
        if revision["project_id"] != project["id"] or status.get("fixture") != code:
            raise ValueError(f"{code} run does not belong to its project")
        if (
            not revision["synthetic"]
            or revision["manifest"]["provenance"] != GRANTS[code]
        ):
            raise ValueError(
                f"{code} publication requires its recorded CC BY 4.0 grant"
            )
        # A run that stops before any model request (no binding) records no model.
        if (
            status.get("state") != "completed"
            or status.get("live_model")
            or (run["model"] or {}).get("live", False) is not False
            or run["outcome"] != EXPECTED[code]
        ):
            raise ValueError(
                f"{code} is not its recorded offline pre-registered outcome"
            )
        export = None
        if run["outcome"] == "VERIFIED_IMPROVEMENT_FOUND":
            export = _check_export(store, run, code)
            if status.get("export_sha256") != export:
                raise ValueError(
                    f"The selected {code} export is not independently verified"
                )
        elif run.get("export") or status.get("export_sha256"):
            raise ValueError(f"{code} carries an export without a verified improvement")
        published[code] = dict(
            run_id=run["id"], outcome=run["outcome"], export_sha256=export
        )
    return published


def validate_public_snapshot(root):
    """The gallery when one was composed, otherwise the original single B02 job."""
    if (Path(root) / "gallery.json").is_file():
        return validate_public_gallery(root)
    return validate_public_b02(root)
