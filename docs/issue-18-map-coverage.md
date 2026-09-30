# Issue #18: restaurant map coverage

## Behavior and decision

Confirmed restaurant searches now retrieve up to three Google Nearby Search
pages and retain up to 60 unique restaurants. The old service fetched one page,
and both the backend and frontend limited the pool to 20.

Fresh results take priority when merging a new viewport search. Previously
discovered restaurants still fill remaining capacity when they are inside the
confirmed bounds. Lower-rated and unrated restaurants remain eligible; filters
and personalization continue to apply after retrieval.

Additional pages are requested only as part of the initial location search or a
confirmed search/location change. Map movement, filter changes, navigation to
Discovery, and new chats do not initiate pagination. Google may return fewer
than 60 places; this is not an exhaustive inventory of every restaurant.

Each provider request, including token activation retries and sparse-area
fallbacks, reserves one unit against the existing actor/global Places quotas
before it is sent. A search normally uses one to three requests. Tokens receive
a two-second activation delay and at most one retry per subsequent page. A
shared six-request ceiling covers all pages, retries, and the existing wider
sparse-area fallback. Sparse coverage is measured after applying viewport
bounds, and the final result still respects those bounds.

Successful pages survive later provider errors or quota exhaustion. Response
headers report request/page counts and partial coverage; the toolbar explains
limited coverage. A first-page failure returns an error so the UI retains its
previous results, rather than presenting fabricated venues or an empty success.
Empty successful results remain empty.

The toolbar shows filtered versus loaded counts and offers Clear filters, which
resets both quick and advanced filters. These controls and coverage notices are
visible on mobile as well as desktop.

Google documents up to 20 results per page, up to three pages per search, token
activation delays, and separate charging for each request:
[Nearby Search (Legacy)](https://developers.google.com/maps/documentation/places/web-service/legacy/search-nearby).
The tradeoff is greater provider cost in dense areas and additional loading time
while page tokens become valid. No new Places fields, photo/detail requests, or
unbounded background searches were added.

## Verification on 2026-09-30

Live checks used the configured Google Places key. Counts describe valid unique
restaurants returned at verification time, not a guaranteed future result count.
No provider restaurant content or credentials were saved in this document.

| Area | First page | Expanded pool | Provider requests | Loaded pages | Service elapsed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Downtown Toronto, 2 km | 14 | 44 | 3 | 3 | 5.61 s |
| Caledon East, 1.5 km | 8 | 8 | 1 | 1 | 2.90 s |

The Toronto pool contained six known budget matches; Caledon East contained
three. An area with no additional provider pages spends no pagination requests.
These live checks called the service directly; endpoint quota behavior was
verified separately with isolated test databases.

Provider-shaped regression fixtures cover dense coverage (20 to 60), smaller
coverage (7 to 12), sparse viewport recovery, deduplication, lower/unrated places,
malformed/out-of-bounds results, token readiness, repeated tokens, provider
failures, and the six-request ceiling. Endpoint tests verify charging and partial
results when either the actor quota or global quota runs out.

- Full backend suite: 112 tests passed.
- Full frontend suite: 80 tests passed.
- ESLint and production Vite build passed.
- TypeScript checking reports nine existing errors, identical to checking an
  isolated copy of the unchanged HEAD frontend with the same dependencies.
- Browser checks at 1440 x 900 and 390 x 844 verified 60 loaded fixture results,
  partial coverage messaging, quick/advanced filtering, restoring the pool, no
  additional discovery request during those interactions, and no horizontal
  page overflow. Both layouts were visually inspected.
- Map component tests verified 60 individually selectable pins and no search
  request from map movement. A real Google map was not rendered in the browser
  check because the local frontend lacks `VITE_GOOGLE_MAPS_API_KEY`.

Changes are local; this verification does not deploy them or change issue state.
