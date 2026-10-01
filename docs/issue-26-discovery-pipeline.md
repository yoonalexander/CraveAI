# Issue #26: source-backed restaurant discovery

Implemented 2026-09-30. Discovery now has a separate regional news collection, with source evidence, Google photos and an in-app **Show on map** action. Nearby map filters still apply to the existing nearby collection. Initial news coverage is **Toronto and the GTA**, not worldwide.

## Source and feasibility assessment

| Source | Decision and evidence |
| --- | --- |
| GDELT DOC 2.0 news metadata | Initial enabled source. GDELT permits commercial reuse of its datasets with attribution and a link; the interface includes both. Only titles, article URLs and index timestamps are read. No publisher article bodies or images are fetched. See [GDELT terms](https://gdeltproject.org/about.html), [DOC API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/amp/) and its [headline/LLM example](https://blog.gdeltproject.org/doc-2-0-api-llms-summarizing-headlines-turkish-investment-inflation-the-niger-coup/amp/). |
| Licensed RSS or official owner announcements | UTF-8 RSS 2.0 adapter implemented and fixture-tested. No live publisher feed is approved by default. Add an exact, code-reviewed HTTPS feed and permission/licence link to `SOURCES` only after obtaining applicable reuse rights, including model processing. RSS availability alone is not permission. |
| blogTO | Direct ingestion excluded. Its [robots.txt](https://www.blogto.com/robots.txt) expressly restricts automated collection, AI/LLM use and commercial reuse without written permission; see [publisher policy](https://zoomermedia.ca/legal-privacy-policy/). Links found in GDELT remain links, not authorization to fetch the publisher's articles. |
| Toronto Life / Toronto Food Blog | Candidate publishers, not approved direct sources. During assessment, the [Toronto Life feed](https://torontolife.com/food/feed/) returned 403 and the [Toronto Food Blog feed](https://torontofoodblog.com/feed/) returned 429. No access controls were bypassed and no broad reuse licence was established. |
| Toronto business licences | Possible future structured source under the [Toronto Open Government Licence](https://open.toronto.ca/open-data-licence/); [dataset](https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/). Not integrated: a newly issued licence does not prove that a restaurant has opened. |
| Beli | **No scraping or app reverse-engineering integration.** Its [terms](https://beliapp.com/terms-of-service) restrict crawling/scraping and reuse. No documented public integration API was found in the reviewed official pages; that is not proof that a private API or export is unavailable. Pursue the official [Partnerships channel](https://beliapp.com/contact-us) for licensed access. No outreach has been sent. A future owner-provided export needs an agreed schema and rights; it does not grant permission to aggregate other users' rankings. |

GDELT reuse rights cover its released metadata, not a blanket licence for the original articles. Stored and displayed evidence is limited to literal quotes of at most 20 words / 160 characters. Readers open the original source to read the article. Licensed RSS text is transient model input; it is not stored as a copied article. Publisher photos are never republished; photos use the existing attributed Google Places gallery.

### Live assessment boundary

The live DOC API returned HTTP 429 on multiple spaced source checks; a source-only CLI check also received a non-JSON response. **No successful live ingestion, live model extraction, live Google match, or hosted release is claimed.** The end-to-end demonstrations use controlled HTTP/model fixtures through the real parser, validation, database, quotas, lease, matching and public API. The RSS demonstration uses a fictional permission-approved owner feed. Demo venues are not seeded into production.

GDELT availability and headline detail determine coverage. A headline often lacks a literal restaurant name, city or opening year, so the pipeline abstains. A sparse news collection is preferable to inventing openings. If live throttling persists, obtain an approved publisher/owner feed or a licensed metadata service and review its adapter and usage rights before enabling it. Do not change hosts or scrape publisher pages to bypass a denial.

## Ingestion and identity

1. Fetch one GDELT `ArtList` page: restaurant/cafe plus the region's city names, 14-day window, newest first, at most 50 metadata records and 1 MB decoded response. Redirects and HTTP errors fail the refresh. Source URLs come from trusted code constants, not public request input.
2. Canonicalize HTTPS article URLs, strip tracking/fragment/AMP variations and deduplicate by SHA-256 URL key. Extract from at most ten unseen articles with one structured GPT call. No model browsing or tools; all source text is untrusted data.
3. Require literal restaurant name, allowed city and quoted evidence in the supplied metadata. An address must also be grounded if supplied. Exclude closures/recalls and unrelated records. Publication time is retained only when provided by an approved RSS feed; GDELT `seendate` is an **index observation**, not a publisher date or opening date.
4. Match at most ten unique name/city/address combinations per run through Google Places Text Search (New), restricted to operational restaurants in the region rectangle. Require normalized exact names, matching city/address and finite coordinates. Multiple branches or truncated results without an address remain ambiguous. Unmatched/ambiguous signals are not shown. They may retry once per day while unexpired.
5. Deduplicate cards by Place ID. Matching failures do not guess an identity. Store source facts, source/publisher IDs, dates, quote, label evidence, expiry and match status. **Only the Place ID from Google is persisted**; Google names, addresses, coordinates and photos remain transient. See [Places storage/attribution policies](https://developers.google.com/maps/documentation/places/web-service/policies).
6. Serve at most eight cards via the read-only `GET /api/discovery/signals?lat=...&lng=...`. This endpoint reads the database and does not call paid providers. On map click, the existing `/api/places/resolve` hydrates one Place ID and opens the map's existing detail window, including places absent from the nearby pool. Photos retain the existing lazy loading, attribution and quotas.

The rectangle is 43.35–44.20 latitude / -80.00–-78.60 longitude. Allowed cities: Toronto, Mississauga, Markham, Brampton, Vaughan, Richmond Hill, Oakville, Burlington, Ajax, Pickering, Whitby and Oshawa. Coverage is regional: news picks are not promised to be within the nearby map radius. Areas outside this rectangle receive an explicit unsupported-region response.

## Label criteria and expiry

| Label | Required evidence | Signal lifetime |
| --- | --- | --- |
| Newly opened | Literal opening statement for the named venue, already opened, with an explicit year and ISO or English month/day/year date matching the extracted date. Date must be within the last 60 days. Planned/reopened/relative or future dates do not qualify. | Until 60 days after the opening date. |
| Trending in coverage | At least two known independent publisher groups with different normalized headlines for the same matched Place ID, observed within 14 days. Unknown ownership cannot establish independence. | Recomputed from unexpired evidence; downgrade when fewer than two qualifying groups remain. |
| Recently spotted | Grounded recent source mention plus a verified Place ID, without the stronger opening/trending evidence. | 14 days after first observation. |

Priority is newly opened, then trending, then recently spotted. “Trending” measures editorial coverage, **not visits, ratings or demand**. Identical headlines count only once across publishers. This catches exact normalized syndication, not every paraphrased reprint; absence of article bodies prevents a stronger editorial independence claim. The qualifying opening or independent publisher links are prioritized among the four visible source links.

The owner registry groups CTV/CP24 together, blogTO/Daily Hive together, and National Post/Toronto Sun together. Toronto Life belongs to SJC, separately from Zoomer properties. Revisit the registry when ownership changes. Primary references: [Bell brands](https://www.bellmedia.ca/about-us/), [Zoomer properties](https://zoomermedia.ca/our-properties/digital/), [SJC Toronto Life](https://www.stjoseph.com/brands/toronto-life), [Torstar brands](https://notices.torstar.com/privacy-policy/index.html), [Postmedia](https://www.postmedia.com/), [Corus brands](https://www.corusent.com/our-brands/), [CBC mandate](https://www.canada.ca/en/canadian-heritage/news/2025/02/backgrounder-role-of-the-government---cbcradio-canada.html). Unknown publishers can provide a cited recent mention but cannot add a trending vote.

A successful source check remains current for **24 hours**. Any failed refresh immediately hides that source's cards; a later successful refresh restores only still-valid signals. Re-fetching an article never advances its original observation or expiry. Expired rows are removed after a seven-day grace period on a completed refresh (up to 67 days after an opening); physical cleanup pauses while the worker is disabled, but API expiry always applies.

The browser reads snapshots at most every five minutes and at their expiry boundary. It hides expired badges before waiting for a replacement, clears failed data, and aborts stale area/map requests. The server returns `Cache-Control: no-store`.

## Refresh operations and costs

Default cadence is six hours, clamped to one–24 hours. A worker checks durable due times once per minute. A ten-minute database lease prevents multiple backend workers from duplicating a run; a lease token fences late writes after reclamation. HTTP clients time out at 25 seconds and model retries are disabled. Errors store sanitized codes, not provider bodies or keys. Status/attempt/success/next-refresh fields are in `discovery_refreshes`; the CLI prints safe outcomes and exits nonzero for errors.

| Setting | Default | Effect |
| --- | --- | --- |
| `DISCOVERY_REFRESH_ENABLED` | `false` | Opt in to the lifespan background worker after migration/source readiness. |
| `DISCOVERY_REFRESH_MINUTES` | `360` | Durable cadence, shared across workers. |
| `DISCOVERY_MODEL` | empty | Inherits `MODEL_NAME` (currently defaults to `gpt-5-nano`); use a model supporting structured outputs and low reasoning effort. |
| `DISCOVERY_DAILY_MODEL_CALLS` | `4` | Daily UTC durable call ceiling across discovery sources/workers. Zero disables extraction. |
| `DISCOVERY_DAILY_PLACE_MATCHES` | `40` | Daily UTC durable Google matching ceiling. Zero disables matching. |

GDELT has no dataset access fee or availability guarantee. Each model call contains at most ten short metadata records and has a 2,000 completion-token ceiling; a conservative input-byte-plus-output reservation also consumes the existing shared global token quota and a 100,000 daily discovery reservation ceiling. Failures consume reservations. Model prices depend on the selected model and account; inspect provider billing before raising ceilings. Non-venue/abstained headlines are not stored as restaurant signals and may be assessed again on a later refresh, within these ceilings.

Google matching uses the **Text Search Pro** field mask, rather than IDs-only search, to validate identity. At the reviewed [Google price list](https://developers.google.com/maps/billing-and-pricing/pricing), this SKU has a 5,000 monthly free usage cap and a first paid tier of **US$32 per 1,000 requests**. Forty matches/day means at most about 1,200 matching requests per 30 days, or **US$38.40 before free caps/discounts**, if every request is billable. Free caps are shared with other application usage; this is not a total app bill estimate. Existing map detail/photo requests have separate SKU costs and app quotas. Paid matching reserves both discovery and shared Places ceilings before calling Google. Manual `--force` bypasses cadence, not leases or daily caps.

### Deployment/runbook

1. Deploy the code with automatic refresh disabled, using the existing backend database owner/service role. Run `alembic upgrade head` against the intended production database; revision `0004_discovery_pipeline` follows `0003_profile_username`. It adds refresh/signal tables and an expiry index, enables RLS on PostgreSQL and revokes Supabase browser-role access. Local SQLite/test schemas are supported. Do not reset/reseed production.
2. Run the free source probe: `python -m scripts.refresh_discovery`. It does not write signals or call Google/OpenAI. Investigate a failed source check before expecting cards.
3. With source access and existing server `OPENAI_API_KEY` / `GOOGLE_API_KEY` available, run `python -m scripts.refresh_discovery --live` for one bounded ingestion. Check the JSON outcome, matched/unmatched evidence and public endpoint; do not expose credential contents. No browser key changes are needed.
4. Set `DISCOVERY_REFRESH_ENABLED=true` and retain the default daily ceilings. Use an always-running backend for the background loop. A sleeping/free host does not refresh while asleep; alternatively an external scheduler can run the same `--live` CLI against the same database every six hours. No scheduler or hosting account was provisioned by this change.
5. Check fresh source links, photos and repeatable map focus in the hosted app. Inspect errors/next refresh and provider billing. Disable the worker to stop future refresh work; daily reservations and read-time expiry remain effective.

No production migration, environment change, paid live extraction/matching or scheduled infrastructure setup has been performed as part of local implementation.

## Verification

Regression coverage exercises both GDELT and permission-approved RSS adapters through real ingestion and persistence, Place ID/URL deduplication, exact/ambiguous/closed/out-of-region matching, independent/related publishers, visible badge evidence, grounded opening dates, source failure/expiry, quota boundaries, concurrent/reclaimed leases and migration upgrade/downgrade on an isolated SQLite database. The endpoint is tested as database-only and geographically validated.

Frontend tests cover API requests, source/index date presentation, retry, expiry during pending refresh/map lookup, area-change races, repeated map focus and App navigation for a news-only venue. Browser checks cover three widths (1440/390/320), light/dark themes, photos/credits, sources, criteria, minimum 44px map controls, no horizontal overflow, expired/error states and chat-free map navigation. These are fixture-based checks; the Google Maps SDK focus behavior is covered by existing MapView tests with an SDK mock.

Local results: **164 backend tests, 122 frontend tests and 69 Playwright checks passed**. Frontend lint/build, Python compilation, isolated migration upgrade/downgrade, PostgreSQL offline migration rendering and `npm audit` (zero vulnerabilities) passed. `tsc --noEmit` still reports the same six pre-existing errors in `api/chat.ts`, `api/client.ts`, `App.test.tsx` and `ProductPages.tsx`; no new TypeScript errors remain. The source-only CLI failed safely on the live GDELT response. No claim is made about a deployed migration or live provider integration.
