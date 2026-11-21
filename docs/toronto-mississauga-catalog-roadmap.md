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
| Restaurant listings | Stage 1 expanded the OpenStreetMap base to 6,471 Toronto listings and 1,384 Mississauga listings, including named fast-food and takeout locations. The cross-check identified 3,393 additional municipal candidates and recorded unresolved leads separately. The refreshed catalog is local. |
| Menu dishes | v0.2 includes a menu reader and 20 reviewed dishes across 10 restaurants. The dishes are in an evaluation file. The app has no live dish index yet. |
| Chat search | In a 28-query replay, searching the dish index first increased queries with a verified result from 7 to 13 and reduced simulated Places calls from 28 to 18. It also hid valid alternatives on three queries whenever it stopped after finding a local match. |
| Storage | The expanded OSM snapshot is about 1.17 MB as a JSON file. Actual hosted usage includes database tables, indexes, and other CraveAI data, and still needs to be measured. |

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
- [ ] Verify which restaurant records are already loaded in the hosted database.
- [ ] Make refreshes preserve restaurant IDs so bookmarks and future dish
  records stay attached. The current importer replaces the snapshot.
- [ ] Load the refreshed two-city list into the hosted database.
- [ ] Confirm municipal candidates and review possible duplicates before adding them to the public catalog.
- [ ] Test the map, restaurant list, name search, location changes, and city
  edges with real records, including restaurants without menus.
- [ ] Fix the map’s coverage label so a few local results can show partial coverage.

One issue to fix during this stage is that the map currently labels an area
as completely covered once the catalog returns any rows. Return coverage
based on the area and the results actually available. A few local results
should still leave a path to find more. [Current map lookup](../backend/routers/places.py) ·
[Catalog importer](../scripts/import_restaurant_catalog.py)

**Done when** the app can find and open records in both cities, including
restaurants without menus, and accurately signals where coverage is partial.
Record the hosted database size at this point to isolate the cost of the
base catalog.

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
- [ ] Record hosted database usage before the refreshed import and after Stage 2.
- [ ] Measure the catalog and menu tables with indexes after the first enrichment pass.
- [ ] Report remaining space and decide whether to expand or improve coverage in the two cities.

**Done when** there is a simple two-city report with the number of restaurants
in the app, basic field and dish coverage, database space used, and remaining
headroom. Use that report to decide whether to improve Toronto and
Mississauga further or add another city.
