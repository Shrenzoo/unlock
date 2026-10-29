"""CLI: python -m unlock_engine.ai {smoke,demo,eval}. Exit 0 on a completed run, 1 on configuration errors."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ..artifacts import atomic_write


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, default=str).encode())


def summary_text(report: dict) -> str:
    lines = [
        f"UNLOCK AI run {report['run_id']}  [{report['provenance']}]",
        f"  outcome     {report['outcome']}  (stop: {report['stop_reason']})",
        f"  why         {report['explanation']}",
        f"  target      {report['identity']['target_id']}  revision {report['identity'].get('revision_handle')}",
    ]
    if report.get("baseline"):
        b = report["baseline"]
        geo = [
            r
            for r in b["rejections"]
            if r["category"] not in ("SEMANTICALLY_BLOCKED", "UNSUPPORTED_OPERATION")
        ]
        lines.append(
            f"  baseline    {b['status']} complete={b['complete']} geometric blocks={[(r['component_id'], r['axis'], r['category']) for r in geo]}"
        )
    for c in report["candidates"]:
        p = c["proposal"]
        fb = c.get("feedback") or {}
        plan = c.get("revised_plan") or {}
        lines.append(
            f"  candidate {c['attempt']} {p['template_id']} {p['parameters']} -> {c['final_stage']}"
            + (f"  [{fb.get('category')}: {fb.get('message', '')[:90]}]" if fb else "")
            + (
                f"  revised={plan.get('status')} reverse={plan.get('reverse')} metrics={(plan.get('metrics') or {}).get('cost')}"
                if plan
                else ""
            )
        )
    u = report["usage"]
    lines.append(
        f"  usage       turns={u['turns']} tool_calls={u['tool_calls']} candidates={u['candidates_constructed']} "
        f"tokens in/out={u['input_tokens']}/{u['output_tokens']} cost={u['cost'].get('estimated_usd')} total={report['timings']['total_s']}s"
    )
    lines.append("  limits      " + "; ".join(report["limitations"][:4]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m unlock_engine.ai")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "smoke",
        help="live provider smoke test (needs FIREWORKS_API_KEY and UNLOCK_AI_LIVE=1)",
    ).add_argument("--output", type=Path)
    demo = sub.add_parser("demo", help="end-to-end redesign run on a synthetic fixture")
    demo.add_argument("--fixture", default="B02", choices=["B01", "B02", "B03"])
    demo.add_argument("--target", default="target")
    demo.add_argument(
        "--offline",
        action="store_true",
        help="use the labelled offline scripted provider instead of Muse",
    )
    demo.add_argument("--output", type=Path, default=Path(".work/ai-demo"))
    sch = sub.add_parser("schema", help="write the AIRunReport JSON Schema")
    sch.add_argument(
        "--output", type=Path, default=Path("schemas/AIRunReport.schema.json")
    )
    ev = sub.add_parser(
        "eval", help="model versus deterministic selectors on frozen cases"
    )
    ev.add_argument(
        "--conditions",
        default="c2_stable,c2_geometry",
        help="comma list of c2_stable, c2_geometry, muse",
    )
    ev.add_argument("--cases", default="", help="comma list of case ids (default: all)")
    ev.add_argument("--output", type=Path, default=Path(".work/ai-eval"))
    args = parser.parse_args(argv)

    from .config import load_config

    if args.command == "smoke":
        from .smoke import run_smoke

        report = run_smoke(load_config())
        print(json.dumps(report, indent=2))
        if args.output:
            _write(args.output, report)
        return 0 if report["status"] in ("passed", "skipped") else 2

    if args.command == "schema":
        from .report_schema import AIRunReport

        _write(args.output, AIRunReport.model_json_schema())
        print(args.output)
        return 0

    if args.command == "demo":
        from ..fixtures import generate_fixture
        from .controller import run_with_model
        from .demo import scripted_agent
        from .provider import build_provider

        source = generate_fixture(args.output / "input", args.fixture)
        step, manifest = (
            (source / "assembly.step").read_bytes(),
            json.loads((source / "manifest.json").read_text()),
        )
        config = load_config()
        if args.offline:
            provider = scripted_agent()
            print(
                "OFFLINE SCRIPTED PROVIDER: not Muse Spark Open. Engineering results are real.",
                file=sys.stderr,
            )
        else:
            if not config.has_credentials:
                print(
                    f"{config.api_key_env} is not set. Use --offline for the labelled scripted demo.",
                    file=sys.stderr,
                )
                return 1
            provider = build_provider(config)
        report = run_with_model(
            step,
            manifest,
            args.target,
            provider,
            prices=config.prices,
            request_timeout_s=config.request_timeout_s,
            max_retries=config.max_retries,
        )
        _write(args.output / "run.json", report)
        text = summary_text(report)
        (args.output / "summary.txt").write_text(text + "\n")
        print(text)
        return 0

    from .baseline import run_selector
    from .controller import run_with_model
    from .evaluation import aggregate, build_cases, summarize
    from .provider import build_provider

    conditions = [c for c in args.conditions.split(",") if c]
    config = load_config()
    if "muse" in conditions and not config.has_credentials:
        print(
            f"muse condition requested but {config.api_key_env} is not set; it will not run.",
            file=sys.stderr,
        )
        conditions = [c for c in conditions if c != "muse"]
    cases = build_cases(args.output / "inputs")
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    rows = []
    for case in cases:
        for condition in conditions:
            started = time.monotonic()
            if condition == "muse":
                report = run_with_model(
                    case["step"],
                    case["manifest"],
                    case["target"],
                    build_provider(config),
                    prices=config.prices,
                )
            else:
                rule = (
                    "stable_enumeration"
                    if condition == "c2_stable"
                    else "geometry_ranked"
                )
                report = run_selector(
                    case["step"], case["manifest"], case["target"], rule
                )
            _write(args.output / "runs" / f"{case['id']}.{condition}.json", report)
            row = summarize(case, condition, report)
            rows.append(row)
            print(
                f"{case['id']:<14} {condition:<12} {row['outcome']:<27} correct={row['correct']!s:<5} cands={row['candidates_attempted']} {time.monotonic() - started:5.1f}s {row['selected'] or ''}",
                flush=True,
            )
    result = dict(
        conditions=conditions,
        model=config.public() if "muse" in conditions else None,
        rows=rows,
        aggregate=aggregate(rows),
        oracle_note="Expected outcomes frozen in evaluation.ORACLES before running; analytic, not exhaustively enumerated.",
    )
    _write(args.output / "evaluation.json", result)
    print(json.dumps(result["aggregate"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
