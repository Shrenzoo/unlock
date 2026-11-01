# Scroll performance and Cloudflare Pages release

Live: <https://unlock-labs.pages.dev>, published 2026-10-31 (America/Chicago).
Pages production deployment `e1c4326a-98a2-4d25-ae5f-ce8cbf0cdbb9` serves application
commit `a621071`. The upload contains 21 files, of which `_headers` is configuration
and 20 are served. This continues the existing, unmerged PR #15 branch on PR #14;
no PR was merged and the user's other checkouts were preserved.

`unlock.pages.dev` was unavailable: Cloudflare offered an address with a random
suffix. The user selected the available exact `unlock-labs.pages.dev` address.
The former `unlock-demo.unlock-labs.workers.dev` site now uses a static catch-all
301 redirect, version `73c0fcb6`. Root, Projects and a workspace URL with its run
query parameter were checked; all reach the matching Pages URL.

## Animation changes

The landing gradient plates, shader source, film-grain asset, model geometry,
materials, camera framing, antialiasing and canvas resolution budgets remain the
same. No image detail or 3D tessellation was removed. The studio environment and
3D components stay mounted as story text changes; contact shadows still refresh
at stage changes at their original 512 resolution. Pose updates run before mesh
and label projection so a paused frame does not retain a previous camera pose.

| Behavior | Before | After |
| --- | --- | --- |
| Gradient section measurements | Three layout reads every animated frame | Shared document coordinates refreshed by ResizeObserver/layout changes |
| Navigation state | Layout reads and state calls while scrolling | Cached boundaries; state changes only at a threshold crossing |
| Material fade paths | First-use shader compilation in story transitions | Both transparent and opaque material variants prepared during startup idle time |
| Scene updates | Story text changes also reconcile the 3D tree and lighting | Stable memoized scene and lighting; shadow refresh kept separate |
| Wheel easing duration | 1.1 seconds | 0.8 seconds, same easing curve |
| Story scrub catch-up | 0.6 seconds | 0.25 seconds |
| Reduced motion | Pauses decorative motion | Preserved; measured zero changing pixels at rest |

Anchor navigation durations remain unchanged. The gradient continues to move at
rest and respond to pointer movement. Canvas containment bounds its painting.
ModuleAssembly is also used in the workspace; the production journey rechecked
original/revised rendering, dragging and checked-route playback after memoization.

## Measurements and visual review

Installed Chrome was profiled with 48 wheel inputs of 165 pixels, each separated
by 45 ms, after network idle and 1.8 seconds of startup. Viewports were 1440×1000
and 390×844. WebGL compilation calls, requestAnimationFrame gaps and long tasks
were observed in the actual page. These are short samples on this computer,
not a promise for every physical phone or browser.

| Sample | Baseline desktop | Live desktop | Baseline mobile viewport | Live mobile viewport |
| --- | ---: | ---: | ---: | ---: |
| Shader program links during scroll | 6 | 0 | 6 | 2 |
| 95th percentile frame interval | 16.7 ms | 16.7 ms | 16.7 ms | 16.8 ms |
| Largest frame interval | 49.9 ms | 33.3 ms | 83.3 ms | 66.7 ms |
| Long tasks over 50 ms | 1 | 0 | 1 | 3 |

The desktop sample removed its observed long task. Mobile still had three
57–64 ms tasks and two program links with measured link call time of 0 ms.
Input-to-model catch-up is shorter, but the evidence does **not** establish
universally stall-free mobile scrolling. Aggregate scripting time varies with
sample duration and is not claimed as a measured improvement. The separate
local sample is preserved, including its 100 ms mobile maximum.

Eighteen paused visual samples covered hero and five story poses at 1774×887,
1440×1000 and 390×844. All eight measured layout rectangles had **0 px change**
in every sample. Seventeen images met the strict comparison target of mean RGB
error below 0.5/255 and fewer than 0.5% of pixels changing by eight luminance
levels. One 1440×1000 sample narrowly exceeded that pixel fraction (0.544%, mean
RGB error 0.157/255). Inspection of the amplified difference localized it to the
floor contact shadow below the model, which is captured at a different moment
with the corrected pose order. The model, text and background remain intact;
the shadow uses the same settings. The strict image-target miss is retained in
[review.json](scroll-performance/review.json), rather than relabeled as a pass.

## Production verification

- TypeScript validation and public Vite build passed; `git diff --check` passed.
- All 20 served files byte-match the release; each has `nosniff` and frame denial.
  Root, Projects and direct workspace navigation all return the SPA document.
- All 14 content-addressed B02 blobs and the 16-member export ZIP passed integrity
  checks. Export hash remains
  `473f81514fcb51eb1004d8b16444d7c89ead3a3e6aa1cb56d8b550cc3d032d9a`.
- The existing production assertion blocks completed for desktop 1600×1000,
  mobile 390×844 and the public API boundary. The runner exited normally with
  status 0. No console, page, failed-request or HTTP errors were recorded.
- Checks include actual 3D dragging/reset, original and revised geometry,
  comparison containment, engineering evidence, route playback, downloads,
  licensing, reload/navigation, disabled mutations and hidden private paths.
- Live motion checks passed idle drift, cursor response, all five story states,
  story navigation, fan isolation, no horizontal overflow, reduced motion and
  WebGL fallback on desktop/mobile. The signed-in Chrome window also opened the
  new hero and scrolled into the story successfully.
- Known Meta/API credential values and Modal token values were scanned in the
  exact public bundle without printing them. There were zero findings and no
  source maps, private Python/CAD source, engineering databases or key files.
- Modal remains read-only with missing live-model credentials. Its exact CORS
  allowlist now includes Pages and the legacy Workers origin; an unrelated
  origin receives no allow-origin response. Snapshot/job identity is unchanged.

Raw observations: [baseline](scroll-performance/baseline-profile.json),
[local profile](scroll-performance/local-profile.json),
[live profile](scroll-performance/production-profile.json),
[visual comparison](scroll-performance/visual-comparison.json),
[live motion](scroll-performance/production-motion.json),
[browser journey](scroll-performance/production-browser.json),
[assets and CORS](scroll-performance/production-assets.json),
[redirects](scroll-performance/legacy-redirects.json).
Screenshots: [desktop](scroll-performance/desktop-hero.png),
[mobile](scroll-performance/mobile-hero.png).

## Hosting and usage

Pages direct upload is static only: no Functions, Worker script, paid add-on,
purchased domain or new runtime secret. The deployment fits the documented
[Pages free limits](https://developers.cloudflare.com/pages/platform/limits/).
[Direct upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)
provides the project domain; [default SPA routing](https://developers.cloudflare.com/pages/configuration/serving-pages/)
is used because the build has no top-level `404.html`. The legacy address uses
Cloudflare's documented [static redirect rules](https://developers.cloudflare.com/workers/static-assets/redirects/).

After the production checks, reloaded native Modal UI showed Starter, a **$30
usage limit**, **$0 spend limit**, **$30.00 displayed credits**, and $0 usage and
charges in its current Usage limit panel. The Usage report selected Oct 1–31,
2026 and displayed **$0.01 total CPU usage**, **$0.00 for each deployed app** and
**0.00 GiB egress** (rounded). These panels cover different billing views; the
$0.01 historical total is not described as this deployment's precise cost.
Credits can update with delay; no unrounded remaining balance is available here.
Cloudflare's legacy static-only worker says metrics are unavailable and requests
are served at no charge. The build's actual file bytes are recorded in
[review.json](scroll-performance/review.json). No billing settings were changed,
no live inference or new engineering computation ran, and public CAD uploads
remain disabled. The API was redeployed only to add the exact Pages CORS origin.

For future releases, build with `npm run build:public` and upload only `dist/`
contents to the Pages project `unlock-labs` in Production. Keep `_headers` and
notices. Do not include the legacy `_redirects` rule in Pages, which would loop.
Rollback is available from the deployment history; the previous Workers build
also remains in that service's version history.
