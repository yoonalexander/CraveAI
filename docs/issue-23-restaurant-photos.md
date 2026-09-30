# Issue #23: restaurant photos

Implementation for [issue #23](https://github.com/yoonalexander/CraveAI/issues/23). Release the frontend and backend together; `/api/places/photo` is new. No database migration or new environment variable is required. Places API (New) must be enabled for the existing backend `GOOGLE_API_KEY`.

## Experience

The shared `RestaurantPhotos` component covers map popups, chat recommendations, Discovery cards, Home suggestion cards and Likes. A saved Place ID can load photos even when its other details cannot be hydrated. Legacy saves and recommendations without a Place ID show a branded fallback; names never substitute for venue identity. Images are genuine Google venue photos, which may include food, interiors or exteriors. We do not claim a pictured dish matches a chat recommendation.

Previews request one image only when within 100px of the viewport. Images use lazy loading, async decoding and responsive cropping. Expand opens a larger, uncropped gallery with Previous/Next controls for up to ten provider photos. Keyboard focus stays in the gallery; Escape and Close restore focus. Background content is inert while the dialog is open. A venue change unmounts the previous photo session, aborts its client request and discards stale results.

Missing photos, provider failures, broken images and quotas have separate fallback states. Retry is explicit for load failures; quota failures never trigger automatic retries. An image failure still permits browsing other gallery photos. Already-started backend work can finish after a browser abort and remains metered.

## Attribution and data handling

[Google's photo guidance](https://developers.google.com/maps/documentation/places/web-service/place-photos) prohibits caching photo resource names because they expire. Each image request fetches fresh `id,photos` metadata, checks venue identity and resource ownership, then resolves just the requested image. Resource names stay within that request. Responses use `Cache-Control: no-store`; photo content and metadata are not written to databases, localStorage, sessionStorage or service-worker caches. The active component holds only display data, with no shared completed-response cache. Reopening another view or revisiting a gallery index can make another provider request. Normal provider/browser image delivery remains subject to Google’s response headers.

[Google's attribution policy](https://developers.google.com/maps/documentation/places/web-service/policies) is implemented with all returned contributor names, profile links and available avatars, plus the supplied individual photo source and reporting links. Compact Home thumbnails retain Google Maps credit and expose full author credits in the expanded gallery, as permitted for small thumbnails. Other previews show full credits directly. Google Maps text remains unmodified, untranslated, at least 12px and readable in both themes. Invalid contributor or media URLs are discarded; missing individual source links fall back to the venue on Google Maps.

The server authenticates Google requests with `X-Goog-Api-Key`, resolves media with `skipHttpRedirect=true` and returns a key-free HTTPS Google image URL. API hosts, foreign hosts, HTTP URLs, credential-bearing URLs and API-key query parameters are rejected for image delivery. Provider errors return a generic status code without raw diagnostics or secret URLs. No client Maps SDK photo call remains; photos also work when the browser map key is absent.

## Cost and quota

The [Details field mask documentation](https://developers.google.com/maps/documentation/places/web-service/place-details) places `id,photos` in Essentials IDs Only. As checked September 30, 2026, [Google's pricing](https://developers.google.com/maps/billing-and-pricing/pricing) gives that metadata SKU unlimited free usage. Photo resolution has 1,000 monthly free requests, then US$7 per 1,000 at the first paid tier: approximately US$0.007 per image, or US$0.42 for sixty image requests, before taxes and account-specific terms. Existing discovery, filter enrichment and map costs remain separate.

Every actual metadata or media call reserves one existing Places quota unit before contacting Google. A venue with no photos consumes one unit; a successful image consumes two. The endpoint accepts one validated Place ID and index 0–9, returns at most one 800×600-bounded image and allows 30 endpoint calls per minute per actor. Existing Guest/Free daily and global limits apply, including global limits for admins. Photo use shares the balance with discovery and filter checks; it cannot bypass provider cost ceilings. Both Google calls have six-second timeouts and no automatic retries. No all-photo prefetch or fan-out occurs.

## Verification

- Backend: 136 tests passed, including matching venue/resource identity, fresh metadata on each image request, all-author attribution, safe media URLs, sanitized provider failures, missing configuration and quota exhaustion between metadata and media.
- Frontend: 100 tests passed, including the actual App across all four issue surfaces, unresolved/legacy saves, no photo persistence, stale-response cancellation, gallery navigation, focus restoration, lazy requests, retry and quotas.
- Playwright: 33 checks passed across desktop, 390px touch and 320px touch, with light/dark screenshots inspected. Gallery and saved-card layouts fit the viewport, controls work and photo requests remain below the full loaded collection size. Existing filter checks also pass. Browser image fixtures are synthetic test assets, never production restaurant photos.
- Lint, production build, Python compilation and npm audit passed; audit reports zero vulnerabilities. TypeScript reports six existing errors; the old `Photo.googleMapsURI` error was removed with the obsolete SDK code. No new type errors remain; this is not a clean project type-check claim.
- Live Google check: an IDs-only text search located PAI Northern Thai Kitchen in Toronto; the new service fetched ten-photo metadata and resolved one image with attribution and an individual source link. The key-free image loaded successfully as JPEG (145,234 bytes). No credentials, photo resource names or provider content were persisted by the check.

Hosted deployment and hosted quota behavior have not been verified.
