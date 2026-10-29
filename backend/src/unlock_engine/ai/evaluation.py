"""Frozen AI evaluation cases and the model-versus-rule comparison runner (PRD §21, BL025/BL027).

Expected outcomes below were written from the fixture geometry and the template
domains BEFORE any evaluation run, and are never derived from a model response.
Variants are correlated (one constructor family); they cannot establish
industrial generalization.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from ..fixtures import generate_fixture

# improvement_supported: True = at least one supported candidate should verify;
# False = no bracket edit can resolve the blocker; outcomes = acceptable final statuses.
ORACLES = {
    "B01": dict(
        target="target",
        improvement_supported=False,
        outcomes=["NO_SUPPORTED_CANDIDATE"],
        rationale="Accessible cartridge, one-operation route; no binding. Nothing to redesign.",
    ),
    "B02": dict(
        target="target",
        improvement_supported=True,
        outcomes=["VERIFIED_IMPROVEMENT_FOUND"],
        rationale="Web z=34..38 blocks target x[-10,10] y[-24,-16]. T01 at (0,-20) with width>=24 and depth 12/16 opens the corridor; T02 +24 clears it.",
    ),
    "B02_heldout": dict(
        target="target",
        improvement_supported=True,
        outcomes=["VERIFIED_IMPROVEMENT_FOUND"],
        rationale="Span 104, target 22 mm wide (x[-10,12]): width 24 at x=0 no longer covers; width>=40 does.",
    ),
    "B02_T02_only": dict(
        target="target",
        improvement_supported=True,
        outcomes=["VERIFIED_IMPROVEMENT_FOUND"],
        rationale="Binding enables only T02; an offset of +24 or +36 moves the web clear of the target Y band.",
    ),
    "B02_tight_cut": dict(
        target="target",
        improvement_supported=True,
        outcomes=["VERIFIED_IMPROVEMENT_FOUND"],
        rationale="maximum_cut_volume 1200 mm3 leaves only 24x12 (and smaller) reliefs; (0,-20,24,12) still covers the target.",
    ),
    "B03": dict(
        target="target",
        improvement_supported=True,
        outcomes=["VERIFIED_IMPROVEMENT_FOUND"],
        rationale="Same bridge obstruction as B02 for the target; the thin tool plate only affects the cover screw.",
    ),
    "B03_cover": dict(
        target="cover",
        improvement_supported=False,
        outcomes=["NO_VERIFIED_IMPROVEMENT", "NO_SUPPORTED_CANDIDATE"],
        rationale="The cover's screw is blocked by a thin fixed plate, not by the editable bracket; no template can clear it.",
    ),
}


def build_cases(root: Path) -> list[dict]:
    root = Path(root)
    built = {}
    for code in ("B01", "B02", "B03"):
        built[code] = generate_fixture(root / code, code)
    built["B02_heldout"] = generate_fixture(root / "B02_heldout", "B02", held_out=True)
    cases = []
    for name, oracle in ORACLES.items():
        source = built.get(name) or built["B03" if name.startswith("B03") else "B02"]
        manifest = json.loads((source / "manifest.json").read_text())
        if name == "B02_T02_only":
            manifest["template_bindings"][0]["templates"] = [
                t
                for t in manifest["template_bindings"][0]["templates"]
                if t["id"] == "T02"
            ]
        if name == "B02_tight_cut":
            manifest["template_bindings"][0]["maximum_cut_volume_mm3"] = 1200
        if name == "B03_cover":
            for c in manifest["components"]:
                if c["id"] == "cover":
                    c["replaceable"] = True
            manifest["constraints"][0]["component_ids"] = ["cover"]
        cases.append(
            dict(
                id=name,
                step=(source / "assembly.step").read_bytes(),
                manifest=manifest,
                **oracle,
            )
        )
    return cases


def summarize(case: dict, condition: str, report: dict) -> dict:
    cands = report["candidates"]
    constructs = [e for e in report["events"] if e.get("tool") == "construct_candidate"]
    valid = [e for e in constructs if e.get("status") in ("ok", "failed")]
    first_valid = (
        (constructs[0].get("status") in ("ok", "failed")) if constructs else None
    )
    verifications = [c["verification"] for c in cands if c.get("verification")]
    usage = report["usage"]
    return dict(
        case=case["id"],
        condition=condition,
        outcome=report["outcome"],
        stop_reason=report["stop_reason"],
        expected=case["outcomes"],
        correct=report["outcome"] in case["outcomes"],
        false_success=report["outcome"] == "VERIFIED_IMPROVEMENT_FOUND"
        and not case["improvement_supported"],
        candidates_attempted=len(cands),
        constructed=sum(bool((c.get("construction") or {}).get("ok")) for c in cands),
        checked=sum(
            c["final_stage"] in ("CHECKED", "VERIFIED_IMPROVEMENT") for c in cands
        ),
        verified_improvements=sum(
            c["final_stage"] == "VERIFIED_IMPROVEMENT" for c in cands
        ),
        failed_mandatory=sum(len(v.get("failed", [])) for v in verifications),
        unknown_mandatory=sum(len(v.get("unknown", [])) for v in verifications),
        proposal_calls=len(constructs),
        proposals_valid=len(valid),
        first_proposal_valid=first_valid,
        tool_calls=usage["tool_calls"],
        schema_errors=usage["schema_errors"],
        model_turns=usage["turns"],
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        estimated_usd=usage["cost"].get("estimated_usd"),
        runtime_s=report["timings"]["total_s"],
        selected=next(
            (
                c["proposal"]["template_id"]
                + " "
                + json.dumps(c["proposal"]["parameters"])
                for c in cands
                if c["final_stage"] == "VERIFIED_IMPROVEMENT"
            ),
            None,
        ),
    )


def aggregate(rows: list[dict]) -> dict:
    out = {}
    for condition in sorted({r["condition"] for r in rows}):
        rs = [r for r in rows if r["condition"] == condition]
        times = sorted(r["runtime_s"] for r in rs if r["runtime_s"] is not None)
        supported = [r for r in rs if r["expected"] == ["VERIFIED_IMPROVEMENT_FOUND"]]
        out[condition] = dict(
            cases=len(rs),
            correct=sum(r["correct"] for r in rs),
            false_successes=sum(r["false_success"] for r in rs),
            verified_on_supported_cases=f"{sum(r['outcome'] == 'VERIFIED_IMPROVEMENT_FOUND' for r in supported)}/{len(supported)}",
            candidates_attempted=sum(r["candidates_attempted"] for r in rs),
            mean_candidates_per_case=round(
                statistics.mean(r["candidates_attempted"] for r in rs), 2
            ),
            proposals_valid=f"{sum(r['proposals_valid'] for r in rs)}/{sum(r['proposal_calls'] for r in rs)}",
            first_proposal_valid=f"{sum(bool(r['first_proposal_valid']) for r in rs if r['first_proposal_valid'] is not None)}/{sum(r['first_proposal_valid'] is not None for r in rs)}",
            failed_mandatory_checks=sum(r["failed_mandatory"] for r in rs),
            unknown_mandatory_checks=sum(r["unknown_mandatory"] for r in rs),
            median_runtime_s=round(statistics.median(times), 2) if times else None,
            p95_runtime_s=None
            if len(times) < 20
            else times[int(0.95 * (len(times) - 1))],
            output_tokens=sum(r["output_tokens"] for r in rs),
            note="p95 withheld below 20 samples; correlated synthetic variants, no statistical claim",
        )
    return out
