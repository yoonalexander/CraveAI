# Issue #19: one font family throughout CraveAI

## Implementation

Inter now supplies the application's normal and italic text, including headings,
navigation, forms, dialogs, legal pages, and CraveAI's map labels and popups.
The shared `--font-family-sans` token also backs Tailwind's font utilities.
Six Georgia/Times heading overrides were removed. Heading hierarchy uses the
existing sizes and spacing with semibold weight; the large authentication
heading has slightly more line height to suit Inter.

Previously, Inter was named in CSS but no font file was loaded, so its presence
depended on the visitor's installed fonts. Unmodified Inter 4.1 variable WOFF2
files are now served locally with their SIL Open Font License. The normal face
is preloaded (352,240 bytes); italic loads when needed (387,976 bytes). No external
font service or package dependency is required.

`font-display: optional` keeps the shared system sans-serif fallback on a slow
or failed first load, without a late font swap during that page view. Inter can
be used on a later navigation when cached. This favors stable layout over
forcing Inter onto an already rendered page.

Sources: [Inter download](https://rsms.me/inter/download/),
[upstream license](https://raw.githubusercontent.com/rsms/inter/v4.1/LICENSE.txt),
and [MDN font-display](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@font-face/font-display).

## Verification

- Full frontend suite: 80 tests passed. The five MapView tests also passed after
  explicitly applying the shared family to the device-location marker label.
- Frontend lint, production build, and `git diff --check` passed.
- Browser checks covered 16 routes at 1440, 390, and 320 pixels in both light
  and dark theme classes: 96 combinations. Rendered headings, text, links, and
  controls shared the same font stack, with no heading clipping, page-level
  horizontal overflow, or browser page errors. Home's advanced filter dialog
  was checked in each combination.
- Chrome's rendered-font inspection confirmed the bundled Inter font was
  actually used. Delayed and failed font requests preserved heading geometry
  and produced zero additional layout shift after the initial render. The
  italic face loaded successfully.
- Custom map marker/popup styles retained Inter inside a simulated provider
  boundary using Roboto. A live Google map was not exercised because the local
  frontend has no Maps API key. Browser API responses were mocked, including
  authenticated account/settings and empty likes/history data.
- TypeScript still reports the same nine existing errors in chat/client APIs,
  App/AccountMenu/Sidebar tests, ProductPages, and SuggestionCard. No new errors
  were introduced; this is not a TypeScript-clean result.

Implemented and verified locally on 2026-09-30. Deployment has not been
verified.
