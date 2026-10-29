"""OFFLINE SCRIPTED PROVIDER for demonstrations without Muse access. Not live model inference.

The script is a fixed policy that reads real tool results: it inspects the
geometric blocker, reads the server domain, proposes the smallest relief at the
domain point nearest the witness, and on a failed check widens the cut along the
axis the feedback names. Its runs are labelled offline_fake_provider and must
never be reported as live model results.
"""

from __future__ import annotations

import itertools
import json

from .provider import FakeProvider, tool_call_message


def scripted_agent() -> FakeProvider:
    st: dict = {}

    def ctx(m):
        text = m[1]["content"]
        return json.loads(text[text.index("\n") + 1 :])

    def results(m):
        out = []
        for msg in reversed(m):
            if msg["role"] == "tool":
                out.append(json.loads(msg["content"]))
            elif msg["role"] == "assistant":
                break
        return out[::-1]

    def ids(m, rid, **kw):
        run = ctx(m)["run"]
        return dict(
            project_id=run["project_id"],
            revision_id=run["revision_id"],
            target_id=run["target_id"],
            request_id=rid,
            **kw,
        )

    def stop(summary):
        return dict(
            role="assistant",
            content=json.dumps(
                dict(
                    decision="no_supported_candidate", candidate_ids=[], summary=summary
                )
            ),
        )

    def s1(m):
        c = ctx(m)
        geo = c["baseline"]["geometric_rejections"]
        brackets = c["brackets_with_constructor_binding"]
        if not geo or not brackets:
            return stop(
                "No geometric obstruction or no constructor binding in the evidence."
            )
        st["rej"], st["bracket"], st["target"] = (
            geo[0]["rejection_id"],
            brackets[0],
            c["target"],
        )
        return tool_call_message(
            ("s1a", "inspect_blocker", ids(m, "s1a", rejection_id=st["rej"])),
            ("s1b", "list_interventions", ids(m, "s1b", bracket_id=st["bracket"])),
        )

    def candidates():
        t01 = next((t for t in st["templates"] if t["template_id"] == "T01"), None)
        if t01 is None:
            t02 = next(t for t in st["templates"] if t["template_id"] == "T02")
            return [
                dict(template_id="T02", parameters=dict(offset_y_mm=v))
                for v in sorted(t02["parameters"]["offset_y_mm"], key=abs)
            ]
        p = t01["parameters"]
        x, y = st["witness"][0], st["witness"][1]
        cx = min(p["center_x_mm"], key=lambda v: abs(v - x))
        cy = min(p["center_y_mm"], key=lambda v: abs(v - y))
        sizes = sorted(
            itertools.product(p["width_mm"], p["depth_mm"]),
            key=lambda wd: (wd[0] * wd[1], wd),
        )
        return [
            dict(
                template_id="T01",
                parameters=dict(center_x_mm=cx, center_y_mm=cy, width_mm=w, depth_mm=d),
            )
            for w, d in sizes
        ]

    def propose(m, rid):
        while st["queue"]:
            nxt = st["queue"].pop(0)
            if json.dumps(nxt, sort_keys=True) not in st["tried"]:
                st["tried"].add(json.dumps(nxt, sort_keys=True))
                prop = dict(
                    candidate_request_id=rid,
                    bracket_id=st["bracket"],
                    evidence_ids=[st["rej"]]
                    + ([st["last_evidence"]] if st.get("last_evidence") else []),
                    rationale="Scripted offline policy: relief at the domain point nearest the BRep witness, smallest size first.",
                    **nxt,
                )
                return tool_call_message(
                    (rid, "construct_candidate", ids(m, rid, proposal=prop))
                )
        return stop("Every scripted proposal was attempted.")

    def s2(m):
        blocker, interventions = results(m)
        if interventions["status"] != "ok":
            return stop("No supported intervention for this bracket.")
        st["templates"] = interventions["payload"]["templates"]
        w = (blocker.get("payload") or {}).get("witnesses") or []
        st["witness"] = (
            w[0]["witness_mm"] if w and w[0].get("witness_mm") else [0, 0, 0]
        )
        st["queue"], st["tried"] = candidates(), set()
        return propose(m, "p1")

    def loop(m):
        last = results(m)
        r = last[-1]
        payload = r.get("payload") or {}
        if r.get("status") == "ok" and payload.get("final_stage") == "CONSTRUCTED":
            return tool_call_message(
                (
                    "v" + payload["candidate_id"][-6:],
                    "verify_candidate",
                    ids(
                        m,
                        "v" + payload["candidate_id"][-6:],
                        candidate_id=payload["candidate_id"],
                    ),
                )
            )
        if r.get("status") == "ok" and payload.get("final_stage") == "CHECKED":
            st["winner"] = payload["candidate_id"]
            return tool_call_message(
                (
                    "cmp",
                    "compare_candidates",
                    ids(m, "cmp", candidate_ids=[payload["candidate_id"]]),
                )
            )
        if "candidates" in payload:
            row = payload["candidates"][0]
            decision = (
                "candidate_proposed"
                if row.get("verified_improvement")
                else "no_supported_candidate"
            )
            return dict(
                role="assistant",
                content=json.dumps(
                    dict(
                        decision=decision,
                        candidate_ids=[row["candidate_id"]],
                        summary=row.get("explanation", "")[:300],
                    )
                ),
            )
        fb = r.get("feedback") or {}
        st["last_evidence"] = fb.get("evidence_id") or st.get("last_evidence")
        if not fb.get("retry_permitted", False) and fb.get("category") not in (
            "INVALID_PROPOSAL",
        ):
            return stop(
                f"Stopped after {fb.get('category')}: {fb.get('message', '')[:200]}"
            )
        return propose(m, f"p{len(st['tried']) + 1}")

    return FakeProvider([s1, s2] + [loop] * 8)
