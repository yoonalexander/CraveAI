# Toronto and Mississauga restaurant catalog roadmap

**The goal is to give every discoverable restaurant location in Toronto and
Mississauga its own CraveAI listing.** Keep the reliable information we can
collect for each place. A restaurant with a name and verified location should
be eligible for the map and search even if we never find a readable menu.
Add dishes and prices wherever the evidence supports them. Finish the two
cities and measure the remaining database space before expanding.

## What we have today

| Area | Current status |
| --- | --- |
| Restaurant listings | The hosted catalog has 7,856 browseable listings across Toronto and Mississauga. This includes seven branch-verified municipal listings. Six duplicate OSM records remain available to existing bookmarks and are hidden from new searches. |
| Menu dishes | Stage 3 adds a hosted index of 48 reviewed dishes across 12 locations, all with published prices. The first pass records a menu-source outcome for every browsable listing. |
| Chat search | Stage 4 merges nearby catalog matches with Google Places. The 34-query replay increased queries with menu-backed results from 6 to 15 and retained every baseline menu-backed venue. Chat continues to call Places for possible alternatives. |
| Storage | Hosted Postgres measured 16.35 MB after Stage 3, up from 13.30 MB before the catalog import. Stage 3's dish and source-check tables and indexes account for 1.26 MB. |

The restaurant catalog and dish index are two different parts of the same
project. We can finish the basic map and restaurant search while incrementally
adding dishes. [Menu index pilot results](menu-index-pilot.md) · [Current snapshot](../data/gta-restaurants.json)

**How to read the checkboxes.** A checked item is complete and verified at
the scope it describes. An unchecked item still needs work or verification.

## Stage 1 — Build the two-city restaurant list

The starting list contained 4,265 listings. The expanded base covers the
two municipal boundaries and includes named takeout locations. Count
physical branches separately and keep uncertain business status visible in
the review queue.

- [x] Build the starting OpenStreetMap snapshot with 4,265 listings across both cities.
- [x] Rebuild the latest available OpenStreetMap extract with restaurant and fast-food coverage.
- [x] Cross-check Toronto against DineSafe and city business licences. Group repeated inspections by premises.
- [x] Check Peel’s inspection portal for a reusable export. Use Mississauga's
  2025 Business Directory for the bulk comparison, since a Peel export wasn't found.
- [x] Match records by name, address, and coordinates. Document ambiguous
  matches and possible duplicate locations for follow-up.

**Stage 1 complete as a source reconciliation pass.** The base listing file,
municipal candidates, and review queue are ready for Stage 2. Remaining
coverage gaps are documented by city. [Coverage report and sources](../data/README.md)

**Done when** every eligible location identified by the approved sources has
one listing or a documented reason it needs follow-up. The report shows how
many locations each source added and where gaps remain. There is no
independent count of every operating restaurant, so measure coverage against
the sources we actually used. [OpenStreetMap data and attribution](https://www.openstreetmap.org/copyright) ·
[Toronto DineSafe](https://open.toronto.ca/dataset/dinesafe/) · [Peel Public Health food safety](https://peelregion.ca/health/protecting-your-health/food-safety)

## Stage 2 — Make the basic catalog work in the app

Keep the name and verified location together with any reliably available
address, cuisine, website, hours, contact information, and operating status.
Keep source and date information so stale details can be refreshed. Leave
unknown fields blank. A missing website or cuisine tag should never hide an
otherwise useful restaurant listing.

- [x] Build the catalog importer and connect the basic catalog lookup to the map.
- [x] Verify the hosted catalog before import. It had zero restaurant rows.
- [x] Preserve IDs during refresh. Update existing records in place and retain
  missing or duplicate IDs for saved-place lookup.
- [x] Load the refreshed two-city catalog into hosted Supabase.
- [x] Verify the municipal branches included in the release and review duplicate
  records before publishing. Seven municipal candidates passed branch checks.
  The remaining 3,386 candidates and uncertain duplicate matches stay in the
  source review data for further reconciliation.
- [x] Test the map, list, and name search with restaurant records, including
  local API lookups in both cities and a viewport crossing the eastern city edge.
  A Toronto listing without a website still appears in search and on the map.
- [x] Label local catalog coverage as partial and offer **Find more restaurants**
  to expand with Google Places. Name search uses the catalog in the selected
  area. The nearby search still falls back to Google Places when the catalog
  has no rows.

The Stage 2 import has 7,862 stored rows and 7,856 browseable listings.
Of those listings, 4,233 have a street address, 5,797 have a cuisine,
1,967 have a website, four have a verified phone number, and five have
published hours. Unknown values stay blank. [Verified branches and duplicate IDs](../data/gta-catalog-reviewed.json) ·
[Catalog importer](../scripts/import_restaurant_catalog.py)

| Hosted storage | Before import | After import |
| --- | ---: | ---: |
| Whole database | 13,298,835 bytes | 15,051,923 bytes |
| Catalog table and indexes | 24,576 bytes | 1,720,320 bytes |

The whole-database measurements use `pg_database_size`. The table measurements
use `pg_total_relation_size`. These are Postgres measurements taken on
November 21, 2026.

## Stage 3 — Add dishes and prices where we can

Process the catalog’s website links in batches. Start with official HTML
menus, text PDFs, and restaurant-linked ordering pages that permit reuse.
Use targeted checks for missed menus, including public menu data files and
readable photos or image PDFs. Prioritize the formats that recover the most
venues. Record whether a menu was found and why extraction failed so the next
pass can focus on the actual gaps.

- [x] Build and test a reader for HTML menus, text PDFs, and supported ordering pages.
- [x] Review 20 dishes across 10 restaurants, with source links and published prices.
- [x] Run the first pass across all 7,856 browsable listings. Check the 1,967
  listings with website links and record the 5,889 listings without one.
- [x] Limit the index to **10 dishes per restaurant** and at most **two per
  dish family**. Choose different dish families before retaining variations.
- [x] Load reviewed dishes with the catalog ID, source URL, check date,
  channel, and published CAD prices for the stated portions. The importer
  supports unpriced dishes and explicitly labeled pickup and delivery prices.
- [x] Keep listings with zero dishes available to nearby, cuisine, and name search.

| November 21, 2026 first pass | Listings |
| --- | ---: |
| Browsable catalog | 7,856 |
| Website URL in the catalog | 1,967 |
| Website yielded at least one automated candidate | 131 |
| Website yielded at least two automated candidates | 124 |
| Website yielded no readable dish and logged no fetch issue | 805 |
| No candidate and at least one source issue | 1,031 |
| No catalog website to check | 5,889 |
| At least one stored, reviewed dish | 12 |
| At least one stored, priced dish | 12 |

The first pass attempted 1,827 distinct starting URLs. Of the 131 listings with
candidates, 114 had readable HTML and 21 had readable PDFs. Four had both.
Candidates can come from a shared site and need branch and price review before
import. The source-issue log captures restrictions, timeouts, unsupported
documents, and other fetch failures. A listing with no catalog website has no
starting URL for this pass.

The reviewed index covers six Toronto and six Mississauga locations.
Targeted checks recovered distinct dishes from an official CSV, a text PDF,
an image PDF, and HTML menus the automatic reader missed. The import stores
selected dish facts and prices with links to the official menus. Menu copy,
PDFs, and photos are excluded. For example, the Kamen source ties the CA$8
price to three deep-fried gyoza and the CA$15.50 price to six grilled gyoza.
[Reviewed seed](../data/gta-menu-reviewed.json) ·
[Kamen menu, page two](https://www.ramenkamen.com/_files/ugd/6dfc81_a8dcec9484cf4b7caa5a6fac644598ff.pdf#page=2)

| Stage 3 hosted storage | Bytes |
| --- | ---: |
| Whole database just before the menu import | 15,060,115 |
| Whole database after the menu import | 16,346,259 |
| Restaurant catalog and indexes | 1,728,512 |
| Source check table and indexes | 1,179,648 |
| Dish table and indexes | 81,920 |

**Stage 3 complete for the first source pass and reviewed import.** Broader
dish coverage still depends on finding websites for missing listings and
reviewing the candidates. Chat integration starts in Stage 4.

## Stage 4 — Use the catalog and dishes in chat

Use the restaurant catalog for basic searches and add verified dish matches
to the existing search results. Merge and rank both sources so one indexed
dish cannot hide a better nearby option. Let a strict budget filter use only
a price verified for the requested item and portion. An unpriced dish can
still appear in a search without a strict budget.

Test the merged path on broad cravings, exact dishes, prices, and areas with
limited menu coverage. Check for correct locations, named dishes, and lost
alternatives. Enable it for a small pilot first and measure actual Places
calls. Skip Places only in the kinds of searches where the pilot shows that
doing so preserves useful results.

- [x] Run the offline 28-query comparison and document the alternatives missed by index-first search.
- [x] Merge verified menu matches with existing search results and check strict budget and portion matching.
- [x] Replay broad and narrow queries to check verified results and lost alternatives.
- [x] Enable a limited live pilot and measure actual Places calls before changing when they’re skipped.

The chat pilot searches the 48 reviewed dishes and explicit Toronto and
Mississauga catalog cuisine or venue tags for searches up to 5 km. It adds
at most four catalog-only venues per request and attaches dish evidence to a
provider result when the name and location identify the same branch.
Unpriced evidence is eligible for ordinary chat. An explicit CAD ceiling
requires an official price for the stated dish and requested portion,
preparation, or ordering channel. In this pilot the hosted index is the source
of those verified prices.

The offline replay covered the frozen 28-query holdout plus six cuisine,
geography, and portion cases. With the same recorded provider fixtures and
strict price rule in both arms, provider-only returned menu-backed results on
6 of 34 queries and the merged path returned them on 15 of 34. Every
menu-backed venue the baseline returned stayed in the merged top three.
Both arms replayed 34 provider lookups. This replay uses the prior reviewed
menu evidence fixture and lexical assessment, so it measures the effect of
adding the current index under controlled conditions.
[Replay script](../scripts/evaluate_chat_catalog.py)

The November 21 production pilot used the same chat pipeline as the streaming
UI. The JSON chat response reported outbound Google Places attempts.

| Live request | Catalog | Places attempts | Result |
| --- | --- | ---: | --- |
| Small spicy boat noodles under CA$16, Toronto | Control | 3 | No verified priced match |
| Small spicy boat noodles under CA$16, Toronto | Merged | 2 | 555 Boat Noodles, small at CA$15 |
| Six-piece grilled gyoza under CA$15, Mississauga | Merged | 3 | No verified priced match |
| Six-piece grilled gyoza under CA$16, Mississauga | Merged | 2 | Kamen, six grilled pieces at CA$15.50 |

The model generated different numbers of search queries for the Toronto pair.
Both requests ran their provider searches. The initial broad Thai search
exposed a cuisine classification bug that was fixed with a regression test.

**Stage 4 pilot complete.** Chat keeps the existing Places calls. The limited
live comparison and sparse menu coverage give no basis for skipping them.

## Stage 5 — Measure space and decide what to add next

Supabase’s free plan includes **500 MB of database size per project**. After
the two-city import and first enrichment pass, record the dashboard’s database
usage, the size of the catalog and menu tables including indexes, and the
space left for normal app growth. Compare those numbers with the readings
before import and after Stage 2. Use the measured increase to estimate the
cost of another city or richer coverage in the first two. [Supabase pricing](https://supabase.com/pricing) ·
[Understanding database size](https://supabase.com/docs/guides/platform/database-size)

- [x] Measure the snapshot files. The starting file was about 0.65 MB and the expanded file is about 1.17 MB.
- [x] Record hosted database usage before the refreshed import and after Stage 2.
- [x] Measure the catalog and menu tables with indexes after the first enrichment pass.
- [ ] Report remaining space and decide whether to expand or improve coverage in the two cities.

**Done when** there is a simple two-city report with the number of restaurants
in the app, basic field and dish coverage, database space used, and remaining
headroom. Use that report to decide whether to improve Toronto and
Mississauga further or add another city.
