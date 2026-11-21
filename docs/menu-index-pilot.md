# CraveAI menu index pilot

The pilot tests whether a small menu index helps chat find specific dishes
nearby with fewer Google Places calls. Use the existing Toronto and Mississauga
restaurant catalog to identify locations. Start with hand-checked dish records
from menus the pilot has permission to store. The catalog alone establishes the
location and website, while each item needs its own evidence.

## Source check

The backend parser was run in memory against six official menu URLs before
and after adding support for visible menu markup. The check made no Google
Places or model calls and saved no menu content. Counts are records extracted
from the direct menu URLs. They do not measure discovery from the restaurant
homepage, and only selected dish and description pairs were checked by hand.

| Area | Official source | Before | After | What the parser could read |
| --- | --- | ---: | ---: | --- |
| Downtown Toronto | [555 Boat Noodles](https://555noodles.com/noodle-soup) | 0 | 8 | Names and descriptions, with protein options and spice indicators where shown on the same dish card. |
| Downtown Toronto | [Bangkok Garden](https://bangkokgarden.ca/toronto-thai-food-menu/) | 0 | 33 | Names and descriptions grouped in the individual dish entries. |
| Downtown Toronto | [Flipper’s](https://www.flipperscanada.com/menus?menu=dinner-menu) | 0 | 52 | Named items, 27 with a description. |
| Central Mississauga | [Udupi Madras Cafe](https://www.udupimadrascafe.ca/dosas) | 0 | 22 | Names and descriptions from the individual Wix containers. |
| Central Mississauga | [Roman Zaman](https://www.romanzaman.com/menu) | 0 | 0 | A browser render returned HTTP 200 and exposed a named dish. Candidate for offline browser-assisted import. |
| Central Mississauga | Andhra Mess | — | — | The former menu URL returns HTTP 404 in both the backend and the browser. Excluded from the pilot until a usable menu source is available. |

Public access was checked for feasibility. Permission to store these menus
has not been confirmed. Start the first ingestion with sources that grant
reuse or with menus provided for the pilot.

## Catalog website experiment

The original homepage crawl found zero dishes in a 20-restaurant sample with
website URLs. The offline probe follows up to five food-menu links from each
starting website and tries structured HTML, recognizable menu layouts,
restaurant-linked text PDFs, and item cards on ordering pages. The report
includes the source URL and any prices for each example. It does not write to the
database or call Google Places or a model. For shared ordering previews it
keeps the dish names and leaves the branch price unknown.

Run the original sample with `python -m scripts.probe_menu_index --count 20
--seed 20261120`. The optional PDF pass uses `pdftotext` on PATH. It caps
downloads at 6 MB and accepts only clearly named and priced text rows.

| Nov 20, 2026 batch | Restaurants | At least 2 dish candidates | Selected dishes with published prices |
| --- | ---: | ---: | ---: |
| Original sample, used to develop extraction | 20 | 8 | 68 |
| Follow-up sample, also used to develop extraction | 20 | 7 | 34 |
| Holdout with no domains from the development samples | 20 | 3 | 19 |

These are extraction counts, not a complete manual accuracy audit. The
holdout contained published menus the probe missed, including
[Kingsway Fish & Chips](https://kingswayfishandchips.com/fish-dinners/) and
[Le Lert](https://lelert.ca/menu.html). The same two direct URLs produced zero
candidates in the probe. A review pass can recover a few dishes from a known
menu while format handling improves. Image-only and client-rendered menus
still need a separate extraction pass. Verify the exact restaurant location,
menu channel, and price before importing records.

## Storage and pricing

Cap the first index at **10 distinct dishes per restaurant**. Pass all parsed
menu pages for that location to `select_menu_index_dishes` before applying the
cap. It deduplicates names, groups known dish names and common topping variants,
then selects one representative from each family before adding a second. When
there are more than ten families, it reserves one slot for the largest family
and spreads the other picks across the menu order. Explicitly categorized
beverages are excluded from the selection. It keeps at most two dishes
per family, even when that leaves slots open. Within a
family it prefers a published price, then a description, and uses menu order
to break ties. Sizes and published options stay attached to the selected dish.
Family grouping uses name rules, so unfamiliar dish names may need review.
Record how many candidates were extracted so coverage is visible during evaluation.

The parser extracted at least one published price for 103 of 115 dishes on the
four readable pilot menus. It returns integer cents and keeps labeled portions
on the same dish. When the menu leaves the currency implicit, import should use
the currency verified for that source and location. Keep the source URL and
check date with the imported record.

The eight 555 dishes with prices, descriptions, and source metadata used 3,561
bytes as compact JSON, about 445 bytes per dish before database overhead. For
planning, allow 750–1,250 bytes per dish including row and index overhead and
500 bytes per restaurant. Reserve 100 MB of the
[500 MB Supabase database quota](https://supabase.com/pricing) for other app
data and growth. That leaves room for roughly 30,000–50,000 restaurants at 10
dishes each. Budget about 34–56 MB for the initial 4,265 restaurants at 10
dishes each. These figures estimate capacity
for text and prices with basic indexes. Measure actual Postgres relation sizes
once the first batch is loaded.

For a strict budget, match the requested dish and portion against its published
price. Items without verified prices cannot satisfy a strict budget. Compute
restaurant price ranges from comparable main dishes before applying the storage
cap. Exclude add-ons, beverages, and party trays. Label the part of the menu
covered, such as **Noodle mains CA$14–$22** for the
[555 noodle menu](https://555noodles.com/noodle-soup). Leave the range unknown
when there are too few verified prices or the scope is unclear. The website
budget filter can consume these fields once the menu index is populated.

## Comparison cases

The prompts below are a draft for the comparison. A reviewer should verify the
expected dish against the version of each approved menu used in the run. A
negative case applies to the named restaurant or test fixture and says nothing
about what other restaurants offer.

| Case | Search | Expected behaviour |
| --- | --- | --- |
| T1 | Spicy Thai boat noodle soup with beef near Grosvenor | Find the boat noodles when the source links beef and spice to that dish. |
| T2 | Spicy seafood noodle soup near Grosvenor | Find the seafood noodle soup with menu evidence for spice. |
| T3 | Find beef noodle soup, preferably spicy, in a fixture where the source only verifies beef and noodles | Show a close match with spice level unverified. |
| T4 | Find beef noodle soup that must be spicy in the same fixture | Omit it as a match when the source gives no spice evidence. |
| T5 | Chicken pad thai near Elm Street | Find the named chicken dish at Bangkok Garden. |
| T6 | Matcha soufflé pancakes near Elm Street | Find the matcha dish at Flipper’s. |
| T7 | Plain pork noodle soup at 555 that must be spicy | Leave spice unverified for that dish even if another pork noodle dish has a spice indicator. |
| M1 | Mysore masala dosa with potato near Square One | Find the potato-filled dosa at Udupi. |
| M2 | A crispy paper dosa near Square One | Find the paper dosa at Udupi. |
| M3 | A paper dosa that must contain potato at Udupi | Avoid borrowing the potato filling from another dosa. |
| M4 | Hummus with beef near Central Parkway West | Include Roman Zaman only if the specific dish and location are verified in an approved source. |
| M5 | Matcha soufflé pancakes within 2 km of Square One, using only the eight approved fixture dishes | Do not move the Toronto result into the Mississauga radius. Report absence of a verified fixture match. |

## Reviewed search comparison

The Nov 20, 2026 evaluation fixture contains two dishes from each of six
Toronto and four Mississauga locations. Each record ties the dish and its
published CAD price options to a catalog ID and an official source.
Manual review supplied records or price options the extractor missed,
including the Phở Hưng menu's public CSV and page two of Kamen's image-only
PDF. These are evaluation records for the ten reviewed locations.

Run `python -m scripts.evaluate_menu_index_pilot` for the paired results by
query. Both arms use the current recommendation pipeline, the same hand-set
intents and search bounds, and the same deterministic lexical assessment.
Places responses are replayed from the ten catalog locations in bounds.
The current path fetches restaurant websites as usual, with their responses
held in memory for both arms during the run. The index-first path adds a
same-dish budget and portion check and uses the current path when it finds no
verified local match. There are no actual Places or model calls in the run.

| Metric | Current | Index first |
| --- | ---: | ---: |
| Expected dish and location in the top 3 | 4 / 11 | 11 / 11 |
| Positive queries without a budget | 4 / 6 | 6 / 6 |
| Positive queries with a strict budget | 0 / 5 | 5 / 5 |
| Correct abstentions | 4 / 4 | 4 / 4 |
| Recommendations outside the fixture's expected matches | 0 | 0 |
| Places retrieval calls in replay | 15 | 5 |

Phở Hưng's regular bowl qualified at CA$14 on the under-CA$18 query. The
large bowl at CA$18 failed the strict limit. The Mississauga dish also stayed
out of the downtown Toronto query. Chicken Phad Thai was deliberately left
out of the index, and both paths still found it at Bangkok Garden through
the current website fallback.

The prompts are a small, targeted set tied to the reviewed dishes. The first
arm does not have the pilot's structured budget check, so the budget subset
measures both changes together. The run does not measure live Google retrieval
quality, model intent extraction, billing savings, or broad catalog coverage.
The production database and chat path have not been changed by the pilot.

## v0.2 holdout

We froze 28 new queries and their search areas before running the comparison.
The same author prepared the reviewed dish fixture and the new queries, so
this is a held-out query set without independent blinding. It covers ordinary
cravings, strict budgets, portion sizes, and incomplete menu coverage. Both
arms use the same ten-restaurant provider replay and 3 km search bounding box.

Run the comparison with:

```sh
python -m scripts.evaluate_menu_index_pilot --queries evaluation/menu_index_holdout.json
```

We reviewed the top three results against the official menus. A result
qualified when its displayed evidence identified an actual dish that
matched the requested attributes and location. Budget queries also required
a source-backed amount for the applicable portion. Provider-only matches
did not qualify. A blank result means the replay did not surface a verified
match. It cannot establish that the dish is unavailable.

| Metric | Current | Index first |
| --- | ---: | ---: |
| Queries returning any top-three result | 13 / 28 | 18 / 28 |
| Queries with at least one source-verified result | 7 / 28 | 13 / 28 |
| Queries returning results but yielding no verified match | 6 | 5 |
| Places retrieval calls in replay | 28 | 18 |

The index improved six Mississauga queries, including 12-inch pepperoni
pizza at CA$14.25 and three deep-fried pork gyoza at CA$8. It correctly
declined the six-piece grilled gyoza under CA$15 since that portion costs
CA$15.50. [Mama Molinaro's menu](https://mamamolinaros.ca/mississauga-mama-molinaro-s-pizzeria-food-menu) ·
[Kamen's official PDF](https://www.ramenkamen.com/_files/ugd/6dfc81_a8dcec9484cf4b7caa5a6fac644598ff.pdf)

### Per-query review

The IDs refer to the frozen query set. A dash means the arm returned no
menu-verified match for the query.

| ID | Current | Index first | Review note |
| --- | --- | --- | --- |
| t01 | Bangkok Garden, Le Lert | Bangkok Garden | The early return omitted Le Lert's wings. |
| t02 | — | — | Le Lert's reviewed burger was over budget. |
| t03 | — | — | Bangkok Garden returned without dish evidence. |
| t04 | Bangkok Garden, Soos, Le Lert | Same | Soos had a valid pineapple curry alongside an unrelated beef description. |
| t05 | Le Lert | Bangkok Garden | Le Lert's evidence included actual garlic beef dishes, omitted by the early return. |
| t06 | — | — | Soos lists CA$17 chicken tacos outside the two-dish index. |
| t07 | — | — | Provider-only hit despite a menu-listed shrimp appetizer at Le Lert. |
| t08 | Bangkok Garden, Le Lert | Same | Both paths fell back to menu evidence for spring rolls. |
| t09 | — | — | The displayed evidence did not tie shrimp to fried rice. Le Lert lists that combination separately. |
| t10 | — | — | No priced match returned. |
| t11 | Le Lert | Same | Le Lert's evidence identifies crispy chicken with rice. Bangkok Garden's listed chicken dishes did not verify crispiness. |
| t12 | — | — | Kingsway publishes halibut fish and chips at CA$24.90. |
| t13 | Kingsway Fish & Chips | Same venue | Both paths returned the Seafood Platter. |
| t14 | — | — | 555 lists medium Pork Noodles at CA$19 outside the two-dish index. |
| t15 | Soos | 555 Boat Noodles | The index found a rice bowl and omitted Soos's rendang with rice. Le Lert's displayed alternatives did not offer beef with rice. |
| m01 | — | Mama Molinaro's | The 12-inch pepperoni qualified at CA$14.25. |
| m02 | — | Mama Molinaro's | The regular Caprese qualified at CA$11.99. |
| m03 | — | Udupi Madras Cafe | The index grounded the fritters in Medu Vada. |
| m04 | — | — | Udupi publishes Cheese Sada Dosa outside the two-dish index. |
| m05 | — | Kamen Ramen | Only the three-piece deep-fried option qualified. |
| m06 | — | — | The requested grilled six-piece portion is CA$15.50. |
| m07 | — | — | A provider-only hit did not identify Kamen's Fresh Tofu Ramen. |
| m08 | — | Phở Hưng | The CA$8 regular spring rolls contain both shrimp and pork. |
| m09 | — | Phở Hưng | The CA$18 large beef bowl qualified. |
| m10 | — | — | The provider returned a venue without verifying a mushroom pizza. |
| m11 | — | — | No grounded result. |
| m12 | — | — | No grounded result. |
| m13 | — | — | No grounded result in the requested area. |

Sources for the missed matches and lost alternatives include
[Le Lert](https://lelert.ca/menu.html),
[Soos](https://www.soostoronto.com/food),
[Kingsway Fish & Chips](https://kingswayfishandchips.com/fish-dinners/),
[555 Boat Noodles](https://555noodles.com/noodle-soup), and
[Udupi Madras Cafe](https://www.udupimadrascafe.ca/dosas).

### Release decision

The index had at least one verified result on every query where the current
path had one, but its early return hid verified alternatives on three
queries. Both paths also missed real menu items outside the reviewed index,
including Soos's chicken tacos and Kingsway's fish and chips. v0.2 therefore
ships the offline extractor, reviewed fixtures, and evaluation only. It does
not import the pilot into the database or enable index-first search in chat.
The next comparison should measure a merged result list and a stricter,
context-dependent rule for skipping Places.
