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

No CAD algorithms, model selection, authentication rules, quotas or billing
settings were changed. The geometry regression suite was not rerun for these
presentation changes.
