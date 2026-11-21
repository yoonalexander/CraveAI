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
| Menu dishes | v0.2 includes a menu reader and 20 reviewed dishes across 10 restaurants. The dishes are in an evaluation file. The app has no live dish index yet. |
| Chat search | In a 28-query replay, searching the dish index first increased queries with a verified result from 7 to 13 and reduced simulated Places calls from 28 to 18. It also hid valid alternatives on three queries whenever it stopped after finding a local match. |
| Storage | Hosted Postgres measured 15.05 MB after the import, up from 13.30 MB. The catalog table and indexes account for 1.72 MB. |

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
- [ ] Run a first pass across the two-city catalog and log which sources worked.
- [ ] Aim for **one or two useful dishes** when a menu is hard to read. Keep up
  to **10 distinct dishes** when we have good coverage. Usually keep one
  representative per dish family before adding a second variant.
- [ ] Store the verified dishes with the exact restaurant location, source, and check date.
  Add a price only when the menu ties it to that item and portion. Label
  pickup or delivery prices when applicable. Unknown prices can stay blank.
- [ ] Keep the restaurant visible when we get zero dishes. Use its known details
  for nearby, cuisine, and name searches.

**Done when** every catalog listing has gone through the available source
checks, and we can report separately how many have a website, a dish, and a
priced dish. Menu coverage can improve after launch.

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
- [ ] Merge verified menu matches with existing search results and check strict budget and portion matching.
- [ ] Replay broad and narrow queries to check verified results and lost alternatives.
- [ ] Enable a limited live pilot and measure actual Places calls before changing when they’re skipped.

**Done when** chat can use both sources, restaurants with partial information
still surface appropriately, and the pilot shows where we can safely save
provider calls.

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
- [ ] Measure the catalog and menu tables with indexes after the first enrichment pass.
- [ ] Report remaining space and decide whether to expand or improve coverage in the two cities.

**Done when** there is a simple two-city report with the number of restaurants
in the app, basic field and dish coverage, database space used, and remaining
headroom. Use that report to decide whether to improve Toronto and
Mississauga further or add another city.
