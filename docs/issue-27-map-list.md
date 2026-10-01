# Issue #27: synchronized Home map and restaurant list

Implemented 2026-09-30. Home now has a **Map / List** control with the loaded restaurant count. Users can browse restaurants, photos, ratings, addresses and distance without starting a chat. **Show on map** selects the same restaurant, opens its existing details and returns to the map; **Open in Google Maps** works even when the in-app SDK is unavailable.

## Scope and synchronization

- The list represents **all loaded restaurant pins**, including pins outside the visible viewport. It does not fetch another page or search on scroll. The existing nearby cap and explicit **Search this area** action remain in effect.
- Markers and list entries use one shared restaurant collection. Nearby restaurants follow the active filters; coordinate-bearing chat picks remain included, matching the existing chat overlay behavior. The list explains this scope and identifies chat picks by their original recommendation numbers. Its total includes chat-only additions; the search toolbar count continues to describe filtered nearby results.
- Deduplication uses the Google place ID when both entries have one. An ID-less entry must match both the normalized name and coordinates within 0.00001 degrees. Same-name branches at different locations remain separate. Invalid or missing coordinates never create a pin or list entry. Nearby data remains authoritative; chat can fill missing public details.
- Selection is shared between marker clicks, list actions and chat map focus. Repeated selection works. Removing a selected pin through filtering or refresh clears its details; recentering also clears selection. The map stays mounted while the list is open, preserving its camera.
- Current pins remain available during refresh and on failures. The list labels the last successfully loaded area until new results arrive. Retry follows the existing quota restrictions; partial-coverage notices are shown. Loading and empty states remain accessible.

On mobile, the list uses the map surface and hides the chat sheet while open. Returning to Map restores the chat sheet; starting a new chat or using a chat/news **Show on map** action closes the list. Desktop retains the adjacent chat panel. List selection and Escape return keyboard focus to the Map control. The photo gallery retains its own keyboard behavior.

## Data and cost

Opening the list and selecting a pin require no additional nearby search, place resolution or model call. Photos reuse the existing lazy, attributed Google Places component and its quotas; photo requests may occur as visible entries are browsed. No environment variables, database migration or backend changes are required.

## Verification

Local results: **127 frontend tests, 164 backend tests and 78 Playwright checks passed**. Frontend lint and the production build passed; `npm audit` reported zero vulnerabilities.

The full browser run passed 77 checks initially; one existing filter test could not navigate to the local server because Chromium reported `ERR_NO_BUFFER_SPACE`. That check passed on an isolated rerun without a code change.

New unit coverage verifies duplicate removal, branch identity, invalid coordinates, original chat numbering, shared selection, repeated map focus, refresh retention, filter removal, recentering and keyboard focus. Browser checks cover 60 entries, shared filters, lazy photos, scrolling, loading/error/quota states, and chat-free browsing at desktop, mobile and 320px widths in light/dark themes. Screenshots were inspected for desktop and narrow mobile layouts.

Browser fixtures intentionally omit the Google Maps key. Actual App/list integration is exercised with controlled HTTP responses; SDK camera and popup behavior is verified with the MapView SDK mock. No live Google/OpenAI calls or hosted release are claimed. `tsc --noEmit` still reports the same six pre-existing errors in `api/chat.ts`, `api/client.ts`, `App.test.tsx` and `ProductPages.tsx`; the issue changes introduce no additional TypeScript errors.
