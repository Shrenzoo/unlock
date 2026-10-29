"""Collect real local execution records into a portable, explicitly offline evidence bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(".work/meta-browser-qa"))
    parser.add_argument("--output", type=Path, default=Path("evidence/meta"))
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.data / "unlock.sqlite3")
    runs = [
        json.loads(row[0])
        for row in db.execute(
            "SELECT data FROM records WHERE kind='run' ORDER BY rowid"
        )
    ]
    run = next(
        r
        for r in reversed(runs)
        if r.get("export") and r.get("outcome") == "VERIFIED_IMPROVEMENT_FOUND"
    )

    def artifact(id):
        data = (args.data / "artifacts" / id[:2] / id).read_bytes()
        if hashlib.sha256(data).hexdigest() != id:
            raise ValueError("artifact hash mismatch")
        return data

    report = json.loads(artifact(run["ai_report_artifact_id"]))
    if report["live_model"] or report["provenance"] != "offline_fake_provider":
        raise ValueError("this collector is specifically for labeled offline evidence")
    (out / "offline-run.json").write_bytes(artifact(run["ai_report_artifact_id"]))
    (out / "checked-export.zip").write_bytes(artifact(run["export"]["artifact_id"]))
    with ZipFile(out / "checked-export.zip") as z:
        if z.testzip():
            raise ValueError("ZIP integrity failure")
        manifest = json.loads(z.read("bundle.json"))
        for name, id in manifest["files"].items():
            if hashlib.sha256(z.read(name)).hexdigest() != id:
                raise ValueError("ZIP member hash mismatch")
    native = report["engineering_evidence"]
    selected = next(
        c for c in report["candidates"] if c["handle"] == report["selected_candidate"]
    )
    plan = native["verified"][selected["candidate_id"]]["plan"]
    summary = dict(
        provenance="explicit offline scripted provider; real CAD, planner, independent verification and export",
        model=report["model"],
        baseline=native["baseline"]["status"],
        outcome=report["outcome"],
        proposals=[
            dict(
                template=c["proposal"]["template_id"],
                parameters=c["proposal"]["parameters"],
                stage=c["final_stage"],
                feedback=c["feedback"],
            )
            for c in report["candidates"]
        ],
        revised_status=plan["status"],
        steps=plan["steps"],
        cost=plan["metrics"]["cost"],
        replay=plan["replay"]["status"],
        reverse=plan["reverse"]["status"],
        replacement_verified=plan["replacement_verified"],
        export=run["export"],
        usage=report["usage"],
        live_meta_verified=False,
    )
    (out / "engineering-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    source = Path(".work/meta-validation")
    for name in (
        "baseline-pytest.txt",
        "baseline-unrestricted.txt",
        "final-pytest.txt",
        "final-pytest.xml",
        "meta-focused.txt",
        "ruff.txt",
        "format.txt",
        "meta-smoke.json",
        "pip-check.txt",
        "live-pytest.txt",
    ):
        if (source / name).is_file():
            if name == "baseline-pytest.txt":
                (out / (name + ".gz")).write_bytes(
                    gzip.compress((source / name).read_bytes(), mtime=0)
                )
            else:
                shutil.copy2(source / name, out / name)
    for name in ("compare.png", "export.png", "report.json"):
        if (source / "browser" / name).is_file():
            shutil.copy2(source / "browser" / name, out / ("browser-" + name))
    build = Path("/private/tmp/unlock-meta-frontend-build.txt")
    if build.is_file():
        shutil.copy2(build, out / "frontend-build.txt")
    xml = ET.parse(source / "final-pytest.xml").getroot()
    suite = xml.find("testsuite") if xml.tag == "testsuites" else xml
    validation = dict(
        generated_at=datetime.now(timezone.utc).isoformat(),
        python=sys.version.split()[0],
        branch=subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip(),
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        baseline=dict(
            passed=220, failed=0, seconds=175.56, restricted_sandbox_failures=10
        ),
        final_pytest=dict(
            tests=int(suite.attrib["tests"]),
            failures=int(suite.attrib["failures"]),
            errors=int(suite.attrib["errors"]),
            skipped=int(suite.attrib["skipped"]),
            seconds=float(suite.attrib["time"]),
            live_tests="2 deselected from ordinary pytest",
        ),
        browser=json.loads((source / "browser/report.json").read_text()),
        live_meta=dict(
            status="unverified",
            reason="no key and explicit live-test flag configured during this execution",
            paid_requests=0,
        ),
        commands=dict(
            backend=".venv/bin/python -m pytest -q --junitxml=.work/meta-validation/final-pytest.xml",
            frontend="npm run build",
            lint=".venv/bin/ruff check src tests scripts",
            format=".venv/bin/ruff format --check src tests scripts",
            dependencies=".venv/bin/python -m pip check",
            browser=".venv/bin/python scripts/browser_qa.py (real loopback servers; AI_PROVIDER=mock)",
        ),
    )
    if validation["final_pytest"]["failures"] or validation["final_pytest"]["errors"]:
        raise ValueError(
            "final regression run is not passing; evidence cannot be marked complete"
        )
    (out / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir()
        if p.is_file() and p.name != "SHA256.json"
    }
    (out / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                output=str(out.resolve()),
                files=len(hashes),
                validation=validation["final_pytest"],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
