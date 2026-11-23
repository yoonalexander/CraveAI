# Toronto and Mississauga municipal candidate review

**November 23, 2026.** The 3,386-candidate queue is closed. The final import
added 882 Toronto and 284 Mississauga listings using the saved city exports.
Toronto additions used active licences and recent passing inspections.
Mississauga additions used the city's 2025 food-service directory, so those
records reflect the survey and may have changed. The final pass excluded 102
out-of-scope candidates and set aside 808 with unresolved eligibility or
location conflicts. It made zero Google Places requests.

Supabase confirmed all 1,166 new rows and **10,111 active listings** overall.
The restaurant table uses **2.28 MB** with indexes, up by about **0.25 MB**.

**November 21, 2026.** Reconciled all **3,386** municipal candidates from the
Stage 2 queue. The active catalog used for comparison has **7,856** listings,
and its full set of IDs matches the hosted catalog.

| Outcome | Toronto | Mississauga | Total |
| --- | ---: | ---: | ---: |
| Supported addition | 485 | 14 | 499 |
| Matched to a catalog listing | 1 | 1 | 2 |
| Duplicate of another candidate | 0 | 1 | 1 |
| Clearly outside restaurant scope | 12 | 3 | 15 |
| Inactive municipal record | 2 | 0 | 2 |
| Possible match to a catalog listing | 84 | 96 | 180 |
| Needs more evidence | 2,179 | 508 | 2,687 |
| **Total reviewed** | **2,763** | **623** | **3,386** |

The [candidate ledger](../data/gta-municipal-candidate-review.csv) has one row
per candidate, with the location, disposition, reason, source record, and any
linked catalog or candidate ID. Filter `outcome` to `supported_addition`
for the proposed import batch. These are review outcomes for the remaining
queue. The seven municipal branches previously admitted are outside its scope.

## Evidence behind the decisions

- **Toronto.** The 485 supported candidates have an uncancelled
  eating/drinking licence, a matching inspection within one year, a
  restaurant-identifying operating name, and no unresolved nearby match
  found by the branch checks. The review used the November 21 city exports.
  The latest inspection in that export is November 20. These are bulk
  municipal matches. A licence or historical inspection alone does not
  establish current opening hours. The two inactive records have
  cancelled licences. [Toronto business licences](https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/) ·
  [DineSafe](https://open.toronto.ca/dataset/dinesafe/)
- **Mississauga.** The city directory is a voluntary 2025 snapshot. The 14
  supported candidates have corroborating public branch evidence, including
  operator pages for Miga Korean BBQ, Mermaid Fish & Grill House, and
  Soranno's. A directory-linked check examined 267 website leads across
  213 hostnames for a matching structured address and a menu or hours. It
  returned one strict match, which was checked against the visible operator
  page. The other supported additions came from targeted source checks.
  [City directory](https://www.arcgis.com/home/item.html?id=073787e3977e4e2e9c68ff13093b6d9e) ·
  [Miga](https://migabbq.com/contact) · [Mermaid](https://mermaidfishhouse.com/contact) ·
  [Soranno's](https://www.sorannosrestaurant.com/)
- **Identity and conflicts.** Tenach and the existing Tenoch pin represent
  the same address. The restaurant site uses both spellings and the pins
  are eight metres apart. Two Mount Sinai directory records refer to the
  same unit. Blackstone remains unresolved because the operator lists
  6435 Erin Mills Parkway and the directory says 6415. Other unresolved
  rows include stale inspections, mixed-use businesses, directory-only
  branches, and cases where the name, unit, or operator needs more evidence.
  [Tenach](https://www.tenachto.ca/about-us) · [Blackstone](https://www.blackstonesteakhouse.ca/locations)

The review checked the existing catalog and nearby names without merging
separate units. A missing menu played no role in the decision. No Google
Places calls were used. The 499 supported candidates are a proposed import
batch. The first pass left **2,867** candidates for branch or eligibility confirmation.
The larger review queue from Stage 1 is tracked separately in the original
coverage data.

## Independent branch check

The [verifier](../scripts/corroborate_municipal_candidates.py) found support
for **132 of 2,867** candidates (4.6%). It combined the pinned November 18
Overture release, Toronto city records, and exact operator branch pages.
The original Overture rule required the `open` flag, which was blank for many
otherwise usable restaurant matches. The revised rule uses a passing Toronto
inspection within a year and an uncancelled licence as evidence of recent
activity. Overture supplies branch and venue-type evidence. The check still
requires a matching street and any recorded unit. A name match that drops a
cuisine suffix must be within 50 metres. All other name matches must be
within 125 metres. Explicit closures, conflicting units, and possible catalog
duplicates stay on hold. [Overture release](https://docs.overturemaps.org/blog/2026/11/18/release-notes/) ·
[Places taxonomy](https://docs.overturemaps.org/guides/places/taxonomy/)

| Result | Toronto | Mississauga | Total |
| --- | ---: | ---: | ---: |
| Recent inspection and matching restaurant | 115 | 0 | 115 |
| Operator branch page supplied the missing evidence | 0 | 13 | 13 |
| Restaurant corroborated by Overture's open status | 2 | 2 | 4 |
| Matching restaurant, activity evidence insufficient | 50 | 26 | 76 |
| Matching branch, restaurant category unconfirmed | 501 | 50 | 551 |
| Unit missing or different | 179 | 76 | 255 |
| Possible catalog duplicate | 84 | 96 | 180 |
| Known source conflict | 0 | 3 | 3 |
| Multiple outside matches | 1 | 0 | 1 |
| No branch match | 1,331 | 338 | 1,669 |
| **Total** | **2,263** | **604** | **2,867** |

The [corroboration ledger](../data/gta-municipal-corroboration.csv) records
the evidence and disposition for every candidate. All 117 supported Toronto
rows were checked against the raw licence and latest inspection exports.
The [operator checks](../data/gta-municipal-operator-checks.json) record the
reviewed branch, source page, and service evidence. Thirteen Mississauga
pages supplied hours, ordering, or reservations for the matching address.
Three Toronto operator checks also support branches already counted in the
inspection group. The 132 are proposed additions and 2,735 remain unresolved.
No catalog entries were written. [K&B Sushi](https://kbsushi.com/contacts/) ·
[Shanghai Taste](https://shanghaitaste.ca/location/) ·
[Pizza Nostra](https://www.pizzanostrainc.com/)

To rerun, install DuckDB's `httpfs` extension and export the area below as
newline-delimited JSON. This extracts 176,462 address-bearing points from
the pinned release. [Overture's DuckDB guide](https://docs.overturemaps.org/getting-data/duckdb/)

```sql
LOAD httpfs;
COPY (
    SELECT id, names.primary AS name, basic_category,
           taxonomy.hierarchy AS category_path, taxonomy.primary AS primary_category,
           confidence, operating_status,
           addresses, websites, sources, bbox.ymin AS latitude, bbox.xmin AS longitude
    FROM read_parquet('s3://overturemaps-us-west-2/release/2026-11-18.0/theme=places/type=place/*')
    WHERE bbox.xmin BETWEEN -79.85 AND -79.10
      AND bbox.ymin BETWEEN 43.45 AND 43.87
      AND len(addresses) > 0 AND confidence >= 0.5
) TO 'gta-overture-places.jsonl' (FORMAT JSON);
```

```powershell
python -m scripts.corroborate_municipal_candidates --places gta-overture-places.jsonl --release 2026-11-18.0 --checked-on 2026-11-21 --operator-evidence data/gta-municipal-operator-checks.json --output data/gta-municipal-corroboration.csv
```

## Reproduce the ledger

The reviewer uses the existing repository snapshots and
[branch evidence](../data/gta-municipal-branch-evidence.json). The three
source exports can be retrieved from the city endpoints below. The
Mississauga query selects the four restaurant NAICS codes and requires
unpaginated results.

- [Toronto licence CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/57b2285f-4f80-45fb-ae3e-41a02c3a137f/resource/54bddc5e-92d9-4102-89c1-43e82f8f4d2d/download/business-licences-data.csv)
- [DineSafe CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/b6b4f3fb-2e2c-47e7-931d-b87d22806948/resource/af0f5b8a-4b73-4a50-8781-65e949792b40/download/dinesafe.csv)
- [Mississauga directory query](https://services6.arcgis.com/hM5ymMLbxIyWTjn2/ArcGIS/rest/services/2025_Mississauga_Business_Directory/FeatureServer/0/query?where=NAICSCode%20IN%20%28722511%2C722512%2C722513%2C722514%29&outFields=OBJECTID%2CBusinessName%2CStreetAddress%2CUnitNo%2CNAICSCode%2CWebAddress&outSR=4326&f=json)

```powershell
python -m scripts.review_municipal_candidates --licences business-licences-data.csv --inspections dinesafe.csv --directory mississauga-food-services.json --reviewed-on 2026-11-21 --output data/gta-municipal-candidate-review.csv
```

## Toronto category recovery and coverage

The current DineSafe export has a legacy establishment ID but lacks the venue
category found in the 2023 archive. The [archive reviewer](../scripts/review_dinesafe_history.py)
links those IDs and checks the operating name, street, unit, and proximity. A
proposal also requires a recent passing inspection, an uncancelled licence
with an eating/drinking endorsement, and a historical restaurant or takeout
classification. Ambiguous venue types and newer conflicting evidence stay on
hold. For example, Famiglia Baldassarre's inspection record remains current
and its own site says its public lunch counter closed. [Toronto DineSafe](https://open.toronto.ca/dataset/dinesafe/) ·
[Famiglia Baldassarre](https://famigliabaldassarre.com/pages/lunch)

The [updated review ledger](../data/gta-municipal-dinesafe-review.csv) adds
157 Toronto proposals and 31 exclusions supported by matching non-restaurant
categories in DineSafe and Overture. The combined position on the original
3,386 candidates is **788 proposed additions, 51 other resolved records,
and 2,547 unresolved**. The 788 include the 499 from the initial review.
An archived category and a passing inspection support a proposal. An
operator check can still establish a closure, move, or change in service.
The remaining queue includes 1,523 candidates with no matching branch in
Overture and insufficient evidence from the archive to resolve them.

For complete queue coverage, every candidate needs a recorded outcome of
eligible, duplicate, inactive, or out of scope, with evidence attached.
Completeness across both cities also depends on discovering eligible
restaurants absent from this queue. Menu items remain optional.

Download the [official historical archive](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/b6b4f3fb-2e2c-47e7-931d-b87d22806948/resource/c0a5f6b0-534a-47c3-867d-d4b5cc84a656/download/dinesafe-historical-data.zip)
alongside the current DineSafe and licence CSVs above, then run the archive
reviewer on the two earlier ledgers.

```powershell
python -m scripts.review_dinesafe_history --ledger data/gta-municipal-candidate-review.csv --prior data/gta-municipal-corroboration.csv --current dinesafe.csv --historical dinesafe-historical-data.zip --licences business-licences-data.csv --conflicts data/gta-municipal-dinesafe-conflicts.json --checked-on 2026-11-21 --output data/gta-municipal-dinesafe-review.csv
```

## Published catalog and remaining decisions

The [disposition ledger](../data/gta-municipal-dispositions.csv) covers all
3,386 candidate IDs. The first batch added **588 Toronto and 29 Mississauga**
branches. All 617 rows matched the hosted catalog. A replay added zero rows,
and the active catalog IDs match the durable snapshot with the
[admissions manifest](../data/gta-municipal-admissions.json). Hosted search
with a viewport returned a newly admitted branch in each city and reported
zero Google Places calls. A second batch resolved four Toronto unit-format
discrepancies. A third batch used [operator branch pages](../data/gta-municipal-operator-followup.json)
to publish 22 more branches. A replay inserted zero rows and hosted viewport
checks returned Café Landwer and Khatta Meetha. The Khatta Meetha operator
page also supplied its unit number. [Duplicate follow-up](../data/gta-municipal-duplicate-followup.json)
identified seven existing pins, which keep their catalog IDs. The CaféTO
follow-up added 16 Toronto listings backed by current branch pages and
confirmed one inactive branch. The next batch published 40 more branches
and linked nine candidates to existing pins. The website and retail review
published nine more branches and resolved 27 retail or institutional
candidates. The next website batch published 19 more branches. Exact hosted
row checks confirmed all 19 and a replay inserted zero rows. The named
viewport checks returned Karkumi Cafe in Toronto and ChickQueen in
Mississauga with zero Places requests. The phone follow-up identified seven
additional candidates already listed under their existing map IDs.
The Peel inspection pilot supplied the missing unit evidence for Abbey Road
Pub & Patio, which was published and verified separately. The next review
published 13 branches with service and unit evidence and resolved eight
retail, bakery, or catering records outside the restaurant scope. Four
additional St. Lawrence Market vendors passed staging and publication.
A shared-address review published ten Wellington Market counters, one
St. Lawrence Market counter, and three Dixie Park Centre counters.
It also linked eight candidates to existing Erin Mills pins and resolved
three Wellington Market or Erin Mills records as inactive or out of scope.
The downtown PATH review published 11 counters at Commerce Court,
Richmond–Adelaide, and Exchange Tower. Two more Toronto branches passed
the next publication. The branch review linked six candidates to
existing pins and resolved six Mississauga records as out of scope.
The chain review matched 22 candidates to existing pins and added two
Little Caesars branches. Branch pages supplied storefront coordinates
and, where applicable, unit or phone evidence. A CaféTO follow-up added
15 Toronto venues with current public meal service. The subsequent service
reviews published 20 Toronto branches and nine Mississauga branches, and
resolved one Toronto confectionery shop as out of scope. Both import replays
inserted zero rows. Brasa Peruvian Kitchen and Jung Thai Restaurant appeared
in hosted viewport search with zero Google Places calls.
The next unit review published Omni Noodle at York University and verified
it in hosted viewport search with zero Google Places calls. Bingz at the
Eaton Centre and Chente’s Taqueria were linked to their existing live IDs.
The retail review resolved 20 Toronto records using branch locators,
product listings, and municipal premises history. The review covers named
retail or private premises. It keeps separately identified food counters
eligible for their own review.
The mixed-use follow-up published seven Toronto and two Mississauga
restaurants with current public meal service. It also resolved two Toronto
shops as out of scope. The hosted database matched all nine imported
records and the replay inserted zero rows. Hot Pork and Cosimo’s Cheese
and Deli appeared in hosted viewport search with zero Google Places calls.
The inspection-date follow-up used branch pages and menus to publish
six more Toronto branches and resolve three dessert or drink shops as
out of scope. Tonic Bar at The Well appeared under its public service name
in hosted viewport search with zero Google Places calls. The replay
inserted zero rows.
The branch-identity review linked 17 additional candidates to active
catalog IDs, two in Toronto and 15 in Mississauga. The checks used operator
addresses and branch phone numbers, mall plans, and existing map points.
The published catalog’s active IDs were verified before recording the
links. Address matching now treats PKY and PKWY as the same abbreviation.
The next two batches published seven verified Toronto restaurants and
resolved one ice cream shop as out of scope. Hosted searches returned
both Canton tenants, Miders Kitchen and Bar, and Burrito Houz with zero
Google Places calls. Both replays inserted zero rows.
The property-directory review published seven public campus counters
at UTM and Lili Foods at The Well. It linked Colman Commons to its
existing point and excluded five retail or contractor records. Lili
Foods and North Side Bistro appeared in hosted viewport search with
zero Google Places calls. The replay inserted zero rows.
The market and food court review published six Toronto and five
Mississauga restaurants, linked the Commerce Court Chop Hop to its
existing ID, and resolved four market retailers as out of scope.
The hosted search returned Carousel Bakery with its public stall number
and Banh Mi Tan Dinh with zero Google Places calls. The replay inserted
zero rows.
The operating-evidence review added 16 Toronto and six Mississauga
restaurants. Hosted viewport search returned Casa Morales, Myungdong
Noodle Shabu Shabu, Privilege T.O., and La Flota Takerias with zero Google
Places calls. Both import replays inserted zero rows. Two candidates
were confirmed inactive. Harvey’s at the former Triple O’s address is a
citywide discovery lead outside the original candidate list.
[Patrician Grill](https://patriciangrill.com/contact-us/) ·
[Harvey’s branch locator](https://www.harveys.ca/en/locations/on/mississauga/1520-courtney-park-dr)

Three candidates in the weak operating evidence group remain, all in
Toronto. Mr. Bento and Piazza Manna still need clearer evidence of current
public service. Spade Bar & Lounge has conflicting sources.
[Spade directory status](https://www.restaurantji.com/on/scarborough/spade-bar-and-lounge-/)

Kensington Jerk & Pasta was published at its 61 Kensington Avenue takeout
counter. Rasta Pasta kept its existing catalog ID and moved to Unit 9 at
50 Brant Street. The pin uses the DineSafe restaurant coordinates for
Waterworks, where the inspection lists the Richmond Street side of the
building. Both restaurants appeared in their respective hosted viewports
and Rasta Pasta no longer appeared in the old one. These checks used
zero Google Places calls, and the import replay inserted zero rows.
[Kensington Jerk & Pasta](https://jerkandpasta.com/) ·
[Waterworks vendor directory](https://www.waterworksfoodhall.com/restaurants/rasta-pasta) ·
[Toronto DineSafe](https://open.toronto.ca/dataset/dinesafe/)

An exact-address review of mixed retail candidates excluded Ambal Trading,
Danforth Market and Price War as retail businesses. Banahaw Foodmart
remains pending. It has been reported to operate a Filipino takeout
kitchen alongside its grocery shop, so its grocery classification alone
is insufficient to exclude it. The kitchen needs a current service check.
[Toronto community food report](https://www.toronto.ca/legdocs/mmis/2021/ec/bgrd/backgroundfile-168287.pdf) ·
[Danforth Market records](https://fraud.ca/on/toronto/danforth-market) ·
[Price War business profile](https://www.bbb.org/ca/on/toronto/profile/discount-stores/price-war-0107-1236156) ·
[Banahaw kitchen reporting](https://torontofoodblog.com/2020/04/01/banahaw-foodmart/)

The café chain batch published four Dark Horse Espresso Bar, two
Dineen, and four Second Cup branches in Toronto, plus six Tim Hortons
branches in Mississauga. The landlord directory confirmed Dark Horse's
Unit 135, and Unity Health confirmed visitor access to Second Cup at
St. Joseph's. Tim Hortons lists separate addresses and phone numbers
for its adjacent 780 and 800 Bancroft Drive counters. Hosted
verification matched all 16 imported records. All appeared in viewport
search with zero Google Places calls, including both Bancroft listings
in the same search. The import replay inserted zero rows.
[Dark Horse locations](https://darkhorseespresso.com/pages/locations) ·
[401 Richmond directory](https://401richmond.com/tenant_category/cafe/) ·
[Dineen locations](https://dineencoffee.com/store.php) ·
[Unity Health visitor services](https://unityhealth.to/patients-and-visitors/at-your-hospital/) ·
[Tim Hortons Mississauga locations](https://locations.timhortons.ca/en/locations-list/on/mississauga/)

The next café batch added 12 Toronto and six Mississauga branches.
Operator, landlord, ordering, and exact-address business records covered
locations such as the DoubleTree lobby, Unit 1 at 5029 Hurontario, and
the WaterPark Place Aroma. All 18 hosted records matched staging, the
replay inserted zero rows, and six representative viewport searches
returned the right addresses with zero Google Places calls.
The Starbucks branch history and the confirmed opening of Shelby's at
5960 Dixie Road resolved that Starbucks candidate as inactive. Shelby's
at that address is a discovery lead outside the original candidate queue.
[Jimmy's locations](https://www.jimmyscoffee.ca/locations) ·
[DoubleTree dining directory](https://www.hilton.com/en/hotels/ytoapdt-doubletree-toronto-airport/dining/) ·
[Peel branch history](https://www.starbuckseverywhere.net/PeelRegion.htm) ·
[Shelby's opening at 5960 Dixie](https://deepakanandmpp.ca/gems-of-mississauga-malton-shelbys-legendary-shawarma/)

The dessert and café batch added 13 Toronto and five Mississauga
branches. The Danforth Starbucks licence and DineSafe inspection used
the same store number with different punctuation. The staging matcher
now accepts that formatting difference when the rest of the name,
address and location checks pass. Hosted verification matched all 18
records, the replay inserted zero, and seven viewport samples returned
the expected addresses with zero Google Places calls. Baskin-Robbins
at 1 Dundas Street West remains pending while current public service
is checked.
[Eva's branch menu](https://www.originalchimneys.com/our-menu) ·
[Dairy Queen Annagem locator](https://www.dairyqueen.com/en-ca/locations/on/mississauga/90-annagem-blvd/12295/) ·
[Studio.89 menu and unit](https://studio89.org/menu/)

The Starbucks follow-up added three Toronto and ten Mississauga
branches. The hosted catalog matched all 13 staged records and the
import replay inserted zero rows. Seven viewport checks returned the
expected branches with zero Google Places calls. The former 350 Bay
Street branch was marked inactive after a reported closure and a
posted notice. The 2965 Argentia Road candidate was dropped for
insufficient evidence. RBC lists its bank at that address, while the
municipal and ordering records identify Starbucks at 2963 Argentia.
[Bay Street closure](https://6ixretail.com/2026/09/starbucks-closes-locations-september-2026/) ·
[RBC branch locator](https://maps.rbcroyalbank.com/ON-MISSISSAUGA-branch-9987) ·
[Starbucks ordering locations](https://www.doordash.com/city/mississauga-on/b/starbucks-11139432/)

The next batch added 21 Chatime and Gong Cha counters and the Starbucks
at 1016 Eglinton Avenue East. The original Starbucks candidate lists
1010. City planning records and the contractor's portfolio link both
addresses to the same development, and ordering confirms 1016. The
public listing uses 1016 and retains the municipal point, about 13
metres from the matched storefront point. Staging checks the reviewed
street number, unit, source links and distance, and searches for
duplicates at both addresses. The hosted catalog matched all 22
records, seven viewport checks passed with zero Google Places calls,
and the import replay inserted zero rows.
[Mississauga permits](https://www7.mississauga.ca/documents/business/2016/New_Industrial_and_Commercial_Building_Permits.pdf) ·
[Contractor portfolio](https://www.stethan.ca/wp-content/uploads/2025/06/Stethan-Corporate-Brochure-Portfolio-2024.pdf) ·
[Gong Cha branch locator](https://gong-cha.ca/locations-2/) ·
[Chatime store directory](https://order.chatime.ca/)

The parallel review pilot matched all 2,196 pending records against the
local catalog snapshot and municipal exports and indexed existing source
leads. 2,028 passed the current municipal checks, 871 had cached leads,
and 68 had a nearby same-name listing. Zero passed the exact catalog
name, address and unit duplicate check.

Three Luna workers reviewed 20 candidates each in bubble tea, bakeries
and pizza. All 60 draft decisions were saved within about four minutes
of generating the input files. The workers proposed 43 additions. The
coordinator published 32 (14 bubble tea, nine bakery, nine pizza) and
held 11 for further review. Seven of those had nearby catalog matches
or an existing linked listing. The other 17 candidates were deferred by
the workers. The coordinator corrected source links and standardized
three service signals before staging. The hosted catalog matched all
32 records, six map samples returned the expected addresses with zero
Google Places calls, and the import replay inserted zero rows.
[Eglinton Square tenant plan](https://mallmaverick.imgix.net/web/property_managers/8/properties/9/galleries/20250401170749/Eglinton_Square_Site_Plan_March_2025.pdf) ·
[Hennick Humber Hospital visitor dining](https://www.hrh.ca/patients-visitors/visitor-information/)

The low-effort Luna pilot reviewed a separate set of 60 candidates.
The workers proposed 20 additions. Eighteen passed coordinator review.
Mad Batter Bakers stayed pending because the operator says the storefront
has no set hours, and Mucho Burrito was marked inactive after Tahini's
confirmed it now serves customers in the same unit. The coordinator
found sufficient evidence for 20 of the 40 entries the workers deferred,
including 10 tea shops. Final results were 38 additions, one inactive,
and 21 pending. Results across the two pilots reflect different cohorts.
The hosted catalog matched all 38 additions, seven sampled branches
appeared in viewport search with zero Google Places calls, and replaying
the import inserted zero rows.
[Mad Batter Bakers](https://madbatterbakers.com/contact-us) ·
[Tahini's Argentia locator](https://tahinis.com/locations/on/mississauga-argentia-rd-winston-churchill/) ·
[Kung Fu Tea Ontario ordering directory](https://www.kungfuteaontario.com/order-online)

The 600-candidate medium-effort Luna run assigned 200 candidates each to
three workers, with ten candidates per saved checkpoint. All 60 checkpoint
files were present within about two and a half minutes of generating the
inputs. The final saved files contained 160 proposed additions, 44
proposed exclusions or closures, and 396 deferrals. Much of this was
triage based on cached leads. The coordinator reviewed public branch
evidence, published 49 additions, and retained the other 551 candidates
in the pending queue. Cached addresses, generic closure text, and inferred
business types still need candidate-specific service or exclusion evidence.
Hosted verification matched all 49 records, seven viewport samples had
zero Google Places calls, and the import replay inserted zero rows.

The hosted catalog now has 8,945 active listings and the six previously
retired IDs.

| Disposition | Toronto | Mississauga | Total |
| --- | ---: | ---: | ---: |
| Added | 916 | 173 | 1,089 |
| Already listed or duplicate | 29 | 54 | 83 |
| Inactive | 6 | 4 | 10 |
| Out of scope | 115 | 12 | 127 |
| Dropped for insufficient evidence | 0 | 1 | 1 |
| Pending | 1,697 | 379 | 2,076 |
| **Total** | **2,763** | **623** | **3,386** |

Among the pending candidates, 114 with historical inspection categories
still need a current public-service check. Three original proposals remain
pending. Jankie’s has current bar evidence and inconclusive meal evidence.
The Victoria Terrace Popeyes requires confirmation of the existing
map pin. Siempre’s municipal address differs from its published addresses.
The [staging command](../scripts/stage_municipal_admissions.py) rechecks new
batches with fresh exports, checks branch claims, and tests repeated imports
and named geographic lookup in an isolated database. Its output is a staging
ledger. Record additions in the disposition ledger after hosted verification.

## CaféTO and chain-locator follow-up

The [CaféTO check](../scripts/review_cafeto_leads.py) joined the city’s
1,378 patio rows to candidates by name, address, and unit within 100 metres.
It identified [186 candidate leads in 196 patio records](../data/gta-municipal-cafeto-leads.csv).
The published 16 all also had current operator service information. PLANTA's
Yorkville branch remained on the patio export even after its May closure.
The [inactive decision](../data/gta-municipal-negative-followup.json) records
the dated closure evidence. [Official CaféTO data](https://open.toronto.ca/dataset/cafeto-curb-lane-parklet-cafe-locations) ·
[PLANTA closure report](https://retail-insider.com/retail-insider/2026/05/planta-closes-toronto-restaurants-in-yorkville-and-queen-west/)

The [chain-locator check](../scripts/review_chain_location_leads.py) compared
five public All the Places extracts with the queue. It identified
[52 branch leads](../data/gta-municipal-chain-leads.csv), including 40 with
matching recorded unit information and 12 that need a unit check. The
results guide direct branch verification and duplicate review. The Tim
Hortons feed includes July 2026 check dates despite the newer overall run.
[All the Places API](https://github.com/alltheplaces/alltheplaces/blob/master/API.md)

The [Tim Hortons verifier](../scripts/review_tim_hortons_locator.py) used the
operator’s city directories to find branch pages. It checked 50 pages and
confirmed 40 exact addresses with published hours and coordinates within
100 metres of the municipal points. Toronto contributed 13 and Mississauga
27. The hosted replay inserted zero rows. The duplicate pass used current
map records for the 173 previously flagged candidates, matching seven
through branch phone or address evidence and two Subway branches through
their exact units and operator coordinates. [Tim Hortons locations](https://locations.timhortons.ca/en/locations-list/on/mississauga/) ·
[Subway at 925 Rathburn](https://restaurants.subway.com/canada/on/mississauga/925-rathburn-road-east)

The [publication command](../scripts/municipal_catalog_publication.py)
generates the guarded additive SQL from the staged manifest. Record the
batch only after the hosted query confirms its row values and active IDs.

## Website checks and omitted map categories

The [website pilot](../scripts/review_operator_websites.py) checked 90
starting URLs covering 97 candidates. It found one exact structured
restaurant record with hours, 31 pages with a visible address, and two
pages with closure text requiring a branch-specific check. Address text
alone can describe another branch, a store, or a former operator. The
structured match at 61 Kensington Avenue remains under review because
the current operator and the former restaurant's catalog pin differ.
[Kensington Jerk & Pasta](https://jerkandpasta.com/) ·
[Reporting on the change at 61 Kensington](https://streetsoftoronto.com/food/this-popular-kensington-market-restaurant-closed-overnight-its-co-founder-just-brought-it-back/)

Nine separately verified branches passed staging and hosted publication.
The [out-of-scope decisions](../data/gta-municipal-negative-followup.json)
cover 27 retail, wholesale, and institutional premises whose exact
branch records have compatible historical DineSafe and Overture types.
These decisions apply to the named premises and do not exclude separately
identified food counters at the same street address.

The [expanded map check](../scripts/review_osm_venue_leads.py) found
[313 candidate leads](../data/gta-municipal-osm-venue-leads.csv) across 314
matches tagged as cafés, bars, or pubs. Eighty-nine matched the street
address and unit information and had an operator website. These are leads
for checking public meal service. [OpenStreetMap extract](https://download.bbbike.org/osm/bbbike/Toronto/)

A separate retail pilot matched 95 candidates by exact normalized name,
street address, recorded unit, and proximity within 100 metres. Independent
checks have resolved 18 of those candidates, including eight additions
with regular meal service. The other 77 remain leads. The map classified Jimmy’s Coffee
at 806 Queen Street East as a butcher, illustrating why retail tags need
independent verification. The Costco warehouse at 42 Overlea is outside
scope. Costco’s separate food court is a citywide discovery lead and needs
its own eligibility and catalog check. [Negative follow-up evidence](../data/gta-municipal-negative-followup.json) ·
[Costco location and departments](https://www.costco.ca/w/-/on/thorncliffe-park/1316)

The November 22 Toronto inspection mirror lists all 20,751 locations
under the generic Food Premises category. A join on official establishment
IDs found 17 pending candidates with newer inspection dates than the cached
city export. Those dates are leads for checking the official records and
public meal service. The refreshed November 22 city export did not
corroborate the 17 newer dates, so the stage used the official dates and
current branch evidence. The official refresh separately found newer
passing inspections for New Jazeera Café and Miders Kitchen and Bar.
The mirror’s public downloads exclude Peel, and the
former Peel Food Check ArcGIS layer is marked deprecated. [Inspection downloads](https://localhealthinspections.com/data) ·
[Toronto DineSafe](https://open.toronto.ca/dataset/dinesafe/) ·
[Former Peel Food Check layer](https://services3.arcgis.com/rl7ACuZkiFsmDA2g/arcgis/rest/services/Region_of_Peel/FeatureServer/1)

The branch-identity checks also found why the existing Canton Kitchen
pin cannot resolve Canton Noodle’s candidate. September 2026 city
inspections place each restaurant in its own Chartwell Shopping Centre
unit, 133 and 134. Canton Kitchen’s pin is only four metres from the
municipal point for Canton Noodle. Staging now accepts a separately
reviewed Toronto unit when the official inspections and supporting
branch evidence confirm its identity. Canton Noodle was published
with its unit and the building-level municipal coordinates.
[DineSafe](https://open.toronto.ca/dataset/dinesafe/) ·
[Chartwell Shopping Centre plan](https://fcr.propertycapsule.com/property/output/document/view/id%3A68713)

UTM’s current dining pages give service hours and building names for
public counters at the shared 3359 Mississauga Road address. The seven
new entries include those building names and use the city’s campus point.
The candidate for Starbucks remains pending because the university lists
two branches and the municipal record gives the shared campus address.
The remaining campus candidates need branch or meal-service evidence.
RioCan’s plan identifies Lili Foods at WM14, the unit recorded on its
licence. DineSafe uses a different stall number. [UTM Dining](https://www.utm.utoronto.ca/hospitality/Food) ·
[Davis Food Court hours](https://www.utm.utoronto.ca/hospitality/davis-food-court-hours-operation) ·
[The Well site plan](https://riocan.propertycapsule.com/property/output/document/view/id%3A140043)

At St. Lawrence Market, the vendor’s phone linked Carousel Bakery’s
public stall 42 to the city inspection under unit code 3738. The hosted
listing uses the directory’s public stall number. The other two market
additions were Ukrainian Store Dnister and Yianni’s Kitchen, whose
market pages describe public takeout meals. Five High Point Mall
counters at 3415 Dixie Road passed branch checks using ordering,
inspection, permit or operator evidence. [Carousel Bakery](https://www.stlawrencemarket.com/vendors/vendor_detail/56) ·
[St. Lawrence Market directory](https://www.stlawrencemarket.com/directory) ·
[Mississauga permit report](https://www.mississauga.ca/wp-content/uploads/2024/06/27104155/May-2024-detailed-building-permit-report.pdf)

The [bulk website run and pilot](../data/gta-municipal-operator-scan.csv)
covered 921 unique candidates. They found
11 exact structured matches, 321 pages with a visible address, and eight
with closure language that requires a branch-specific check. The remaining
pages were unreachable or lacked exact evidence. The verified additions are
recorded in the [operator follow-up](../data/gta-municipal-operator-followup.json).

The [branch phone review](../scripts/review_osm_branch_phones.py) found
[30 shared-phone leads](../data/gta-municipal-osm-phone-leads.csv) by comparing
municipal public business numbers to active OpenStreetMap pins. The seven
confirmed Mississauga matches also had a branch or ordering page matching the
municipal street address. Other leads include unit conflicts and possible
changes of operator. The phone match alone establishes neither.

The [Peel public inspection search](https://www.peelregion.ca/health/inspections-monitoring/health-inspections)
returned four records across six test searches. Two matched the target
branch and unit. For Abbey Road Pub & Patio, the May 15, 2026 inspection
identified unit 9 and the operator published service hours.
[Peel inspection record](https://rmop.hedgerowsoftware.com/Portal/Facility/Details/fdf9da29-4d74-4aab-a94c-167c31220bd1) ·
[Operator hours](https://abbeyroadpub.ca/contact-us/)

The Alf Hana result confirmed unit 5 at 6550 Meadowvale Town Centre Circle.
Its similarly named catalog pin is about 262 metres from the municipal
point, so the candidate stays open while the pin is checked. The Apna Pind
result was on Telford Way, a different address from the candidate. A
street-only search for 3359 Mississauga Road returned a child-care facility
at the campus, so it cannot establish the kiosk's status. Two searches
returned no results, including the verified ChickQueen branch. A search
miss gives no basis for closure.
[Alf Hana inspection](https://rmop.hedgerowsoftware.com/Portal/Facility/Details/9c66ea0f-767a-490a-8a98-b3d88cadb3c3) ·
[Apna Pind inspection](https://rmop.hedgerowsoftware.com/Portal/Facility/Details/397e37f9-d4b8-4504-9923-fa767b183bef)

The larger Peel search timed out repeatedly and was stopped. No final
dispositions came from those timeouts. Branch pages, commercial pickup
listings, and market directories supplied the evidence for the next batch.
At St. Lawrence Market, the vendor directory supplies exact stalls,
public service and hours. The licence and DineSafe records for European
Delight agree on the branch name, street and phone. The market and operator
identify the accessible stall as B6, which is the public address used in
the catalog.
[St. Lawrence Market directory](https://www.stlawrencemarket.com/directory) ·
[European Delight stall](https://www.stlawrencemarket.com/vendors/vendor_detail/65)

At Wellington Market, the landlord’s floor plan supplied stall numbers.
The staging review records the exact inspection address for a documented
alias and still requires a matching licence, premises and operating
evidence. At Erin Mills Town Centre, the landlord’s directory and floor
plan identified the existing food-court pins and showed Dickey’s occupying
the former Teriyaki Experience stall. The catalog's only Dickey's listing
is elsewhere, so the Erin Mills branch is a confirmed discovery gap
outside the 3,386-candidate queue.
[The Well floor plan](https://thewelltoronto.com/wp-content/uploads/2026/02/The-Well-Leasing-Brochure-February-24-2026.pdf) ·
[Erin Mills directory](https://erinmills.ca/stores/) ·
[Dickey's opening announcement](https://www.dickeys.com/press/press-releases/dickey-s-barbecue-pit-now-open-in-mississauga-as-brand-accelerates-canada-expansion)

The Eaton Centre businesses can have different city-licence and visitor
street addresses. The landlord plan and current branch pages linked the
licences to existing pins without creating duplicates. At Pearson, four
directory records at 6905 Dixie Road identify concessions that the airport
places beyond passenger security. This disposition applies to the named
concessions. The terminal directory also identifies venues before security.
[Eaton Centre concourse plan](https://assets.cadillacfairview.com/m/43273f2554bf438e/original/TECON20_LEASINGPLAN.pdf) ·
[Pearson dining directory](https://www.torontopearson.com/en/shop-dine-relax)

The chain review used public locator coordinates where the catalog map
record omitted a street address. The storefront point reconciled a
Burger King listing at 1490 Dixie Road that the first distance match
missed. At two Subway branches, shared public phone numbers reconciled
unit differences. Records whose location sources still disagree stay
pending.
[Subway store directory](https://restaurants.subway.com/canada/on/mississauga) ·
[Pizza Pizza store directory](https://www.pizzapizza.ca/restaurant-locator/ontario/mississauga/) ·
[Burger King franchise operator](https://redberry.ca/locations)

Municipal records, maps and branch locators establish restaurant
identity and service. Catalog-only suggestions return a null customer
rating. The live Google Places path supplies ratings when it is used.

Contains information licensed under the Open Government Licence – Toronto
and data from the City of Mississauga's 2025 Business Directory. Catalog
matching uses OpenStreetMap data. [Toronto licence](https://open.toronto.ca/open-data-license/) ·
[Mississauga terms](https://mississauga.maps.arcgis.com/sharing/rest/content/items/961c790805c14d8da258ec91bf4117e3/data) ·
[OpenStreetMap attribution](https://www.openstreetmap.org/copyright)
