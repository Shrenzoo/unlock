"""Fail closed before making a selected, licensed B02 snapshot public."""

import hashlib
import io
import json
from pathlib import Path
import zipfile

from ..fixture_license import B02_PROVENANCE, b02_license_files
from ..contracts import Provenance
from .snapshot import SnapshotStore


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
    artifact = run["export"]["artifact_id"]
    if (
        run["export"]["roundtrip_status"] != "passed"
        or status.get("export_sha256") != artifact
    ):
        raise ValueError("The selected B02 export is not independently verified")
    # All downloadable blobs, not just the outer ZIP, must retain their identity.
    for path in (root / "artifacts").glob("*/*"):
        store.artifacts.get(path.name)
    with zipfile.ZipFile(io.BytesIO(store.artifacts.get(artifact))) as archive:
        bundle = json.loads(archive.read("bundle.json"))
        if bundle["status"] != "full_assembly" or set(archive.namelist()) != set(
            bundle["files"]
        ) | {"bundle.json"}:
            raise ValueError("B02 export inventory is invalid")
        for name, metadata in bundle["files"].items():
            expected = metadata["sha256"] if isinstance(metadata, dict) else metadata
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("B02 export member integrity failed")
        if json.loads(archive.read("manifest.json"))["provenance"] != B02_PROVENANCE:
            raise ValueError("B02 export provenance differs from the licensed snapshot")
        for name, data in b02_license_files(Provenance(**B02_PROVENANCE)).items():
            if archive.read(name) != data:
                raise ValueError("B02 export licensing notice is missing or changed")
    return dict(run_id=run["id"], export_sha256=artifact, license="CC-BY-4.0")
