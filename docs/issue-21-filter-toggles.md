# Issue #21: filter buttons staying highlighted

## Reproduction and cause

Reproduced on desktop Chromium (1440px) and Chromium touch emulation (390px and
320px), including both light and dark theme classes. The new browser
regression initially failed in all six viewport/theme combinations.

1. Load Home with four restaurants: two open, two budget-priced, with one in
   both groups and one with unknown open/price data.
2. Click or tap Open Now. It becomes pressed/green and two results remain.
3. Click or tap it again without moving the desktop pointer away.
4. `aria-pressed` becomes false, the active class disappears, and all four
   results return, but the button keeps its selected green appearance.

The CSS assigned identical styles to `:hover` and `.is-active`. Touch Chromium
retained hover after tapping, while desktop hover remained under the pointer.
There was no lost filter state in this reproduced sequence: the visual state
disagreed with the working filter state. Repeated taps could leave both All and
an inactive filter looking selected.

## Fix

Selected green styling now follows `aria-pressed="true"`. Unselected hover has a
separate neutral appearance, limited to devices supporting hover with a fine
pointer. Touch hover no longer changes an inactive filter's appearance. Native
keyboard focus remains available; the fix does not blur buttons or suppress
clicks. Filter selection, matching rules, and data retrieval remain unchanged.

The repeated-toggle check now reports:

| After toggling Open Now off | Desktop | Touch |
| --- | --- | --- |
| Pressed state | false | false |
| Results | 4 restaurants | 4 restaurants |
| Inactive background | neutral `rgb(247, 248, 246)` hover | white `rgb(255, 255, 255)` |

The selected background remains green `rgb(237, 244, 233)`.

## Regression coverage and verification

- Added Playwright because this bug depends on real CSS hover behavior, which
  jsdom does not render. `npm run test:e2e` runs 18 cases across desktop, touch,
  narrow touch, and both themes. The workflow installs Chromium and runs this
  suite alongside the existing frontend checks.
- Browser cases cover sticky hover/deselection, repeated touch/click toggles,
  an 81-click burst in one event turn, selection during a pending restaurant
  request, state after results arrive, combined filters, All/Clear filters,
  advanced apply/cancel/draft clearing, and Discovery card visibility.
- Added an App integration test using the real toolbar, filter logic, MapView,
  and restaurant marker components. Only the external Maps SDK and network
  responses are substituted. Visible marker names, counts, and pressed states
  agree after repeated toggles and clearing quick/advanced filters.
- Full frontend suite: 88 tests passed. Browser suite: 18 passed, including a
  local run with `CI=true` and the workflow's two-worker configuration. Lint,
  production build, dependency audit (zero vulnerabilities), and
  `git diff --check` passed.
- TypeScript still reports the same seven existing errors in chat/client APIs,
  App tests, ProductPages, and SuggestionCard. No new TypeScript errors remain.
- Browser APIs use fixed restaurant fixtures. Marker integration uses a fake
  Maps SDK. Live provider calls, physical mobile devices, Safari, deployment,
  and a remote GitHub Actions run were not exercised.

To run the browser regressions after installing frontend dependencies:

```powershell
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

Playwright starts its own local Vite server on port 4175; no backend or real Maps
API key is required. Traces from failures are stored in ignored test-results.

Implemented and verified locally on 2026-09-30. Deployment has not been verified.
