# Independent product presentation

[← Back to the README](../README.md)

Updated 2026-11-14. UNLOCK is presented as an independent open-source research
prototype for mechanical repairability. The README, landing page, project gallery
and private access form describe the product without an event name, track, theme
or judging role.

## Changes

- The README introduces the repairability problem and the workflow, with no
  event badge or event-specific positioning. Credits identify both authors.
- The landing page explains AI-assisted CAD redesign and opens the six-project
  gallery from its primary calls to action. The sample workspace remains
  available in the workspace preview.
- The footer links to the source, documentation and verification limits.
- Private demo access replaces the public judge terminology. The form keeps its
  existing authentication, quotas and private result handling, and displays a
  loading label while checking an access code.
- Search and social descriptions use the same product positioning.

## Technical attribution and historical records

The live model integration still uses Muse Spark 1.3 through the Meta Model API.
Its provider configuration, attribution, licenses and recorded evidence remain
accurate. The hosted public demo continues to serve recorded offline CAD results;
private uploads use the existing bounded offline worker.

The original access service retains the `unlock-judges` deployment name,
`VITE_UNLOCK_JUDGE_API`, the session storage key and `?judge=` links. Existing
private result links and deployment settings continue to work.

Original engineering records, the initial requirements and previous validation
reports retain their dates and historical context. Git history and evidence have
not been rewritten. Presentation changes do not make a claim about when the
underlying work was built.

## Validation

- `npm run build:public` with the existing public and private Modal origins:
  passed, including TypeScript and production bundling.
- `python3 docs/check_docs.py`: passed for all 17 documents, including local
  links, anchors, image budgets and credential-pattern checks.
- `ruff check tests/browser/test_production.py tests/browser/test_journey.py`:
  passed. Existing browser assertions now follow the gallery entry point and use
  the private demo labels.
- `git diff --check`: passed.
- Built asset inspection: all 22 public files were inventoried; compiled scripts
  contain the new labels, no old event branding, and the existing private API
  origin. No source maps or server source files are in the upload.
- Safari visual review: the current React components were bundled into an
  isolated file preview and inspected at 1440 × 1000 and 390 × 844. Hero copy,
  3D presentation, footer layout and the 390-pixel private access form rendered
  correctly. This was a layout review, not an end-to-end backend test.

No CAD algorithms, model selection, authentication rules, quotas or billing
settings were changed. The geometry regression suite was not rerun for these
presentation changes.

## Production release

Published to the existing Cloudflare Pages project `unlock-labs` on
2026-11-14 at 21:15 UTC, from application commit
`5d3a497eec3053db7c380ae30d7b81ce740b8968` (merged PR #33).

- Website: <https://unlock-labs.pages.dev>.
- Production deployment: `15a3e613-f031-4fb5-834d-8b7c379d29ff`.
- Deployment URL: <https://15a3e613.unlock-labs.pages.dev>.
- Upload: 22 static files, packaged as a 638,937-byte ZIP. Every archive member
  and local build file matched the pre-upload SHA-256 inventory. Cloudflare
  confirmed all 22 files uploaded and the production deployment succeeded.

Safari checks on the live production origin confirmed the updated homepage
copy, gallery entry point, independent product footer and resource links. All
six assemblies loaded, and the private access form showed **Private demo access**
and **Unlock private demo**. B02 loaded its recorded BRep geometry and evidence;
its workspace URL survived a reload, and comparison displayed the original
`no_path_supported` and revised `feasible` results side by side.

The published build uses the existing public and private Modal origins. No new
private analysis, model inference or private session was started for these checks.
The full automated production browser suite was not rerun; these were targeted
manual Safari checks following the earlier production build and responsive
layout review.
