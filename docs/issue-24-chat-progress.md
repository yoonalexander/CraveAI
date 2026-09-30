# Issue #24: animated chat progress

Implementation for [issue #24](https://github.com/yoonalexander/CraveAI/issues/24). No migrations or environment changes are needed. Release the frontend and backend together for the progress UI and stream cancellation cleanup.

## Behavior

The former 45px thinking row squeezed its dots when streamed status text appeared. `ChatProgress` now keeps a persistent dot animation beside a full-width text area, using CraveAI's existing Inter typeface and green palette. Each new status fades and moves into place gently; repeated identical text does not restart the transition. A reserved three-line status area keeps the card and composer stable on narrow screens. Only existing public stage messages appear; no private reasoning or invented progress percentage is added.

The initial state reads “Getting your search ready…” until the server emits a stage. Dots stay mounted and animated throughout understanding, retrieval, menu checking, assessment and ranking. Explicit light/dark styles preserve text contrast. Reduced motion disables both animations and uses immediate conversation scrolling. Only the changing status text sits in a polite, atomic live region; the decorative dots and repeated heading are hidden from screen readers.

The composer shows Stop while pending. Stop clears the pending card, aborts the request and stream reader, removes partial recommendation pins, and returns focus to the composer. Unmount also aborts pending work. A request identity guard ignores late stages, recommendations, replies, errors and cleanup from an older request, including when a new attempt has already started. Completion, failures and retries clear/reset the stage. JSON and legacy fallbacks share cancellation without treating it as a timeout or issuing another fallback request after Stop.

Closing or cancelling the server's streaming generator now cancels unfinished recommendation work as well as clearing its callback. Previously those exit paths could leave the background task running. Provider work already submitted and quota already reserved may still count; cancellation does not promise refunds or reversal of committed work.

## Verification

- Frontend suite: 111 tests passed, including initial/multiple stage updates, completion, provider/timeout/quota errors, cancellation, retry races, unmount and streaming/JSON/legacy cancellation.
- Backend suite: 139 tests passed. New regressions first reproduced orphaned tasks on generator close/cancellation, then passed with cleanup; explicit disconnection is also covered.
- Playwright: 48 checks passed across desktop, 390px touch and 320px touch. Fifteen exercise a real browser SSE connection with separately gated stages, normal/reduced motion, both themes, stable card/composer geometry, Stop, error and retry. Existing filter/photo checks pass. Screenshots inspected for desktop and narrow mobile layouts.
- Lint, production build and npm audit passed; audit found zero vulnerabilities. TypeScript still reports the same six pre-existing errors, with no new errors.

Browser streaming uses a controlled local fixture, not live Google/OpenAI requests. Hosted deployment and proxy streaming behavior have not been verified.
