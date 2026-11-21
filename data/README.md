# Toronto and Mississauga restaurant catalog

`gta-restaurants.json` is the base snapshot for the existing importer. It
includes named OpenStreetMap restaurants and fast-food or takeout locations
inside the two municipal boundaries. Records keep their OSM identifier, name,
coordinates, and any available street address, cuisine, and website.

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
This snapshot is available under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The [BBBike Toronto extract](https://download.bbbike.org/osm/bbbike/Toronto/)
was retrieved November 21, 2026. Its PBF header is dated November 14, 2026
UTC. Rebuilding with the old filter reproduced the original 4,265 records
exactly. The broader filter preserved all of those records and added 3,590
named fast-food or takeout records.

## Stage 1 coverage

| Count | Toronto | Mississauga |
| --- | ---: | ---: |
| OSM base listings | 6,471 | 1,384 |
| OSM listings with a website | 1,584 | 379 |
| Municipal source records compared | 15,731 | 1,376 |
| Municipal source records linked to existing OSM listings | 2,110 | 335 |
| Additional municipal candidates that passed automated checks | 2,766 | 627 |
| Municipal records needing review | 10,855 | 414 |
| Possible duplicate pairs within OSM | 22 | 1 |

`gta-restaurant-coverage.json` holds matched source IDs, separate sets of
municipal candidate records, and a review queue with reasons. Matched source
records may point to the same OSM listing. The additional candidates have
source coordinates inside the city and passed conservative identity checks.
Their sources can still be stale or misclassified. Keep unreviewed municipal
records in the coverage data for follow-up. The queue is not
a count of missing restaurants. It includes ambiguous addresses, possible
duplicates, unaffirmed licences, and businesses that may fall outside scope.

- **Toronto** uses uncancelled food-licence records with a public operating
  name. The current DineSafe CSV has 128,326 inspection rows, grouped into
  20,324 premises. For newer records, a matching public name and street
  address ties a licence to inspection coordinates. The latest inspection
  date is November 19, 2026. The comparison also queues recent unmatched
  DineSafe names that resemble restaurants. Licensing categories include
  retail food and other premises, and 85 licence records lacked a public
  operating name. Contains information licensed under the Open Government
  Licence – Toronto. [Business licences](https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/) ·
  [DineSafe](https://open.toronto.ca/dataset/dinesafe/) · [Toronto licence](https://open.toronto.ca/open-data-license/)
- **Mississauga** uses the City's 2025 Business Directory, a voluntary
  survey with mapped businesses. The food-service query returned 1,450
  rows. Of those, 1,376 had restaurant or limited-service codes and went
  through the comparison. Peel Public Health publishes inspection lookups,
  but no reusable bulk export was found for this pass. The City directory
  fills part of that gap. [Business Directory](https://www.mississauga.ca/services-and-programs/business/employment-survey/) ·
  [Feature layer](https://www.arcgis.com/home/item.html?id=073787e3977e4e2e9c68ff13093b6d9e) ·
  [City terms of use](https://mississauga.maps.arcgis.com/sharing/rest/content/items/961c790805c14d8da258ec91bf4117e3/data) ·
  [Peel inspection information](https://peelregion.ca/health/protecting-your-health/food-safety)

One or more OSM features can represent the same place. Stage 1 records
possible duplicate pairs while preserving existing OSM IDs. Both cities
have gaps beyond the sources we could compare.

## Rebuild locally

To refresh, download the current Toronto PBF from BBBike. Install `osmium` and
`shapely` in an extraction environment. For the cross-check, use the newest
CSV resources from the two Toronto datasets above. Query layer 0 of the
city directory for `NAICSCode LIKE '722%'` with geometry in WGS84
(`outSR=4326`). The running app and the import command do not need these
extraction packages.

```powershell
python -m scripts.build_restaurant_catalog Toronto.osm.pbf data/gta-restaurants.json --source-url https://download.bbbike.org/osm/bbbike/Toronto/Toronto.osm.pbf --retrieved-on YYYY-MM-DD --boundaries-output gta-boundaries.json
python -m scripts.reconcile_restaurant_catalog --osm data/gta-restaurants.json --boundaries gta-boundaries.json --toronto-licences business-licences-data.csv --dinesafe dinesafe.csv --mississauga mississauga-food-services.json --output data/gta-restaurant-coverage.json --checked YYYY-MM-DD
```

Apply the Alembic migrations to the Postgres database first, then run
`python -m scripts.import_restaurant_catalog`. The importer includes the
branch-verified municipal listings and OSM duplicate decisions in
[gta-catalog-reviewed.json](gta-catalog-reviewed.json). Before the next
refresh, recheck those decisions against the updated source files as IDs
may have changed. The importer validates that reviewed IDs exist in the
inputs. Past IDs stay resolvable for saved places even if they leave the
browseable catalog.

See the [Stage 2 roadmap](../docs/toronto-mississauga-catalog-roadmap.md#stage-2--make-the-basic-catalog-work-in-the-app)
for the hosted import counts and storage measurements.

## Menu source checks and dish import

The source pass checks catalog website URLs in batches and records a status
for every active catalog ID. It reads public pages with a bounded site crawl,
respects robots restrictions, and makes zero calls to Google Places or an AI
model. Install `pdftotext` for the text-PDF pass. Restarting with the same
report continues from the IDs already checked.

```powershell
python -m scripts.check_catalog_menus --output catalog-menu-checks.jsonl --checked-on YYYY-MM-DD
python -m alembic upgrade head
python -m scripts.import_catalog_menus --checks catalog-menu-checks.jsonl
```

The importer requires a report for the current active catalog. It stores the
source check outcomes and loads dishes from [the reviewed seed](gta-menu-reviewed.json).
The approved seed records menu facts and portion prices keyed to the catalog
branch. Automated extraction counts help prioritize review. Refreshes of the
restaurant catalog preserve these branch IDs. The new tables are available
through the server database connection.
