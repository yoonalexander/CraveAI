# Issue #22: restaurant filters and evidence

Implemented locally for [issue #22](https://github.com/yoonalexander/CraveAI/issues/22). No database migration is needed. Frontend and backend must be released together for the new `/api/places/filter-data` endpoint.

## Experience and semantics

Home and Discovery use the same filter state, result pool and sorting. Filters govern the loaded nearby discovery pool; numbered chat-recommendation pins use the separate Show on map flow and are not included in discovery counts. Discovery's duplicate collection filters were removed; its optional text search narrows that collection and has its own visible count and Clear search action. The toolbar shows matching versus loaded restaurants, including on mobile. It does not imply that the loaded pool contains every restaurant in the area.

Filters combine with AND. Multiple selected price levels combine with OR. Selected advanced groups appear as removable chips. All / Clear filters resets quick and advanced choices; Reset advanced filters resets the dialog draft, which is applied only by Show results. Closing the dialog discards changes. Applying explicit price levels replaces Budget-friendly; enabling Budget-friendly clears explicit price levels. Personalization can exclude disliked restaurants, but only the Relevance sort promotes favourites/saved places.

| Filter | Source | Exact rule |
| --- | --- | --- |
| Budget-friendly | Google price category | Only free (0) or inexpensive (1). Replaces the unsupported “Under $20” claim. |
| Price level | Google price category | Exact selected categories, 0–4. Free is distinct from unknown. |
| Open Now | Google's opening status | Explicit `true` at the last fetch. Unknown and closed are excluded; this is a snapshot. |
| Cuisine | Explicit Google restaurant types, optionally official-menu inference | Exact, case-insensitive catalogue label. No substring matching or restaurant-name guesses. |
| Minimum rating | Google rating | Numeric rating at least the selected threshold. Unrated places remain available with Any rating. |
| Distance | Coordinates and confirmed area centre | Straight-line distance within 2, 5 or 10 km. Any in map area adds no distance constraint. |
| Takeout / Delivery / Reservations | Google Details boolean attributes | Explicit `true` only. False and absent remain distinct in the data. |
| Accessible entrance | Google `accessibilityOptions.wheelchairAccessibleEntrance` | Explicit `true`; does not claim full venue accessibility. |
| Vegetarian / Vegan | Explicit Google categories/vegetarian offering; optionally menu evidence | Google vegetarian offering supports vegetarian only. A vegan category also supports vegetarian. Menu inference needs an explicit complete dish or whole-menu declaration. |
| Gluten-free / Halal | Official menu/site evidence interpreted by GPT | Explicit support only; no inference from ingredients or cuisine. No certification or allergen safety guarantee. |
| Combined dietary choices | Linked evidence | All chosen requirements must share supporting evidence. Separate vegan and halal dishes do not establish a vegan halal dish. |
| Include menu labels | User choice | Enabled by default; disabling it excludes every inferred label from cuisine and dietary filtering. Google data still qualifies. |
| Sort | Loaded data | Relevance, descending rating, ascending distance, or ascending price. Unknown price sorts last. |

The cuisine catalogue contains American, Brazilian, Chinese, French, Greek, Indian, Indonesian, Italian, Japanese, Korean, Lebanese, Mediterranean, Mexican, Middle Eastern, Spanish, Thai, Turkish and Vietnamese. Other cuisines remain unclassified until the catalogue is expanded. Google has [explicit restaurant types, including vegan and vegetarian categories](https://developers.google.com/maps/documentation/places/web-service/place-types); broad food/restaurant tags do not prove a cuisine. Discovery no longer adds cuisine guesses based on restaurant names.

## Enrichment and missing data

Restaurant data explains checked versus loaded coverage and the number of menus assessed. The advanced dialog reports service yes/unknown counts. Users explicitly choose Check next N restaurants, at most ten per click. This scans the loaded pool in order, including places currently excluded by filters. No request occurs just from opening/applying filters, navigating to Discovery, or loading the homepage.

Each check fetches Google Details, follows the existing bounded official-site/menu reader, then makes at most one GPT classification request for the batch. Native Google cuisine labels take priority. Dietary Google support is preserved even if GPT fails. Missing data never counts as a match and is not silently converted into a negative fact. Selected filters remain applied during loading, errors and quota failures. Provider/model failures preserve other restaurants' data and can be retried after the unchecked pool has been processed. Missing or unreadable menus count as no evidence and are rechecked after an area refresh.

Inferred cuisine requires an explicit cuisine statement or at least two characteristic complete dishes. Dietary inference requires explicit status tied to a complete dish or whole menu. Sauces, toppings, sides, ambiguous labels, negations and ingredient-only guesses do not qualify. Multiple dietary requirements must share evidence IDs. Website content is treated as untrusted data. Model output is allowlisted and cannot introduce new place IDs, evidence IDs, quotations or URLs. Source links and original evidence labels are constructed by the server and shown under Label sources on map details and Discovery cards.

Menu reads sample at most six structured dishes and four visible text blocks per candidate. Dynamic sites, PDFs, inaccessible menus, sampled sections and changing menus limit coverage; an absent label is not proof that an option is unavailable. No lexical keyword fallback creates dietary matches. The older dietary endpoint now uses the same validated classifier and shared-evidence rule.

Results live in component memory, are cleared on a refreshed restaurant pool, and use `Cache-Control: no-store`. No restaurant enrichment is written to the database or local storage. Client aborts discard stale responses; already-started server requests may still finish and remain metered.

## Provider cost and latency

The existing Nearby discovery paging remains unchanged. The new per-place request asks only for `id,types,priceLevel,currentOpeningHours,takeout,delivery,reservable,accessibilityOptions,websiteUri,servesVegetarianFood`. [Google Details documentation](https://developers.google.com/maps/documentation/places/web-service/place-details) assigns service/dietary fields to Enterprise + Atmosphere, so the narrow mask still reaches that tier. Reviews, photos, generated summaries and exact price ranges are not requested for this feature.

As checked September 30, 2026, [Google's published pricing](https://developers.google.com/maps/billing-and-pricing/pricing) lists 1,000 monthly free Enterprise + Atmosphere Details requests and US$25 per 1,000 at the first paid volume tier. Outside that free cap, ten checks are approximately US$0.25; checking sixty is approximately US$1.50, before existing discovery requests, model costs, taxes or account-specific terms. This is why details are requested on demand rather than for every initial pin.

Every unique Details request reserves one actor/global Places quota unit before any paid work. An insufficient balance rejects the batch atomically. Map searches also consume this quota, so a guest may not be able to check all sixty places in one day. Both filter-data and the legacy dietary endpoint are bounded to ten IDs and five batches/minute per actor. Admin access still respects global limits. Failed provider requests remain reserved; there are no automatic paid retries.

Details use concurrency five and a six-second deadline per place; a ten-place batch can take two waves. Official-menu enrichment has an eighteen-second deadline, keeps the existing fetch/size/redirect/SSRF limits, and preserves partial evidence. GPT has a twelve-second deadline, no automatic retry, low reasoning effort and at most 3,000 completion tokens. The complete batch has about a 42-second maximum network-work budget plus processing overhead. UI shows a checking status during this time.

`FILTER_LABEL_MODEL` optionally selects a dedicated model; blank inherits the existing `MODEL_NAME`. It must support structured outputs and low reasoning effort. [Structured output parsing](https://developers.openai.com/api/docs/guides/structured-outputs) enforces the response shape, while application validation enforces evidence references. Model cost depends on the configured model and actual tokens; input is bounded to ten candidates and ten snippets each, with each label/detail capped at 240 characters. GPT receives official-site evidence and opaque IDs, not Google reviews, business descriptions or user/account information. `store=False` is used. Provider/refusal/timeout errors produce unknown labels rather than guessed matches.

Deployment must enable Places API (New) and authorize the backend key for its endpoint. Existing `GOOGLE_API_KEY` and `OPENAI_API_KEY` are reused. No change to infrastructure or credentials was made.

## Verification

- Backend suite: 122 passed, including successful Google → official HTML/JSON-LD → model → source-link flow, unknown/false preservation, model failure, native vegetarian support, invalid IDs and per-call quota enforcement.
- Frontend suite: 93 passed, including actual app/map-marker filtering, error/retry, inference exclusion, price-choice replacement and explicit sorting with personalization.
- Playwright: 24 passed across desktop, 390px touch and 320px touch, in light and dark themes. Covers selected appearance, shared Discovery counts, advanced apply/cancel/reset, enrichment and source links. Desktop/narrow screenshots inspected; no horizontal overflow.
- Lint, production build and npm audit passed; audit reported zero vulnerabilities.
- TypeScript still reports the seven pre-existing errors; this change introduced none. Build success is not a clean type-check claim.
- Live GPT smoke: nine synthetic evidence cases passed with the locally configured `gpt-6-luna`, in 7.73 seconds. Covers complete dishes, two-dish cuisine support, whole-menu statements, condiments, negation, fusion, ambiguous names, ingredients-only guesses and injected instructions. Reproduce with `.venv\Scripts\python.exe -m scripts.evaluate_filter_labels --live`; this deliberately makes one paid model call and is not run by CI.
- One live Google Details → official menu → GPT check completed successfully. Only one of four service attributes was known and no cuisine/dietary label was supported in that sample, exercising abstention. This is connectivity/sparse-data evidence, not a broad real-world accuracy benchmark.

Hosted deployment and hosted quotas have not been verified.
