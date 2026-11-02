# A five-minute local walkthrough

[← Back to the README](../README.md)

This path runs the real CAD engine with the labelled offline policy. It needs no API key and spends nothing. For setup, see [Try UNLOCK](../README.md#11--try-unlock).

Start the backend with `AI_PROVIDER=mock` and the frontend, then open <http://localhost:5183/projects>. The first backend start generates and imports the bundled fixtures, so give it a minute or two.

## 1. Watch it fail

Open **B02**. Select `target` in the tree and choose **Set as repair target**, then **Run baseline analysis**.

The planner reports `no_path_supported`, complete, with two `CONFIRMED_GEOMETRIC_OBSTRUCTION` rejections and a BRep witness at (0, −20, 36) mm after 13 mm of travel, where 640 mm³ of the target overlaps the bracket. There is no invented operation count. The original has no route, so no percentage improvement can be reported later.

## 2. Watch the loop

Choose **Explore a redesign**, then **Request redesign**. The scripted policy reads the real tool results and proposes:

1. **T01 24 × 8.** It is built and checked, and replanning rejects it: `NO_REPAIR_PATH`, `INSUFFICIENT_CLEARANCE`. An 8 mm cut over an 8 mm target leaves less than the 0.5 mm policy gap.
2. **T01 24 × 12**, citing that rejection. It passes.

This is not a replay of the live run. Live, Muse proposed 24 × 12 with the wrong citations, was refused before construction, and then chose 40 × 16. See [the agent loop](agent-loop.md#the-live-records).

## 3. Read the verdict

Open the verification panel on the accepted candidate. Each check carries its provenance. The frontend paints a pass green only when computed evidence backs it (`ui/Evidence.tsx`). An illustrative pass would be drawn as an outline.

## 4. Compare

Switch to the comparison. Left: `no_path_supported`. Right: `feasible`, `target TRANSLATE Z+ 80 mm`, cost (0, 0, 0, 1), with forward replay and reverse insertion passed.

## 5. Export

Accept the candidate and export. The bundle is reimported and rechecked before it is reported as a success. Open the STEP in any CAD tool to see the relief.

## With a key

Put `MODEL_API_KEY` in `backend/.env`, set `AI_PROVIDER=meta` and restart the backend. The same clicks now perform real inference, which spends credits. Live runs have cost about three cents each at list price and vary in the design they choose.

To read a live run without spending anything, open [`backend/evidence/live-b02/live_run.json`](../backend/evidence/live-b02/live_run.json).

## Illustrative mode

`VITE_UNLOCK_MODE=fixture npm run dev` runs the interface against prepared records with no engineering computation, and it says so in the header. It is for interface work only.
