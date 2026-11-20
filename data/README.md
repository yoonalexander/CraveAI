# Toronto and Mississauga restaurant catalog

`gta-restaurants.json` is a snapshot of named OpenStreetMap features tagged
`amenity=restaurant` whose coordinates fall inside the two municipal boundaries.
It contains 3,628 Toronto listings and 637 Mississauga listings. A record has an
OSM identifier, name, coordinates, and optional street address, cuisine and
website. Missing fields are empty. Counts describe the source snapshot, and can
include duplicate or outdated listings.

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
This snapshot is available under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The source is the [BBBike Toronto extract](https://download.bbbike.org/osm/bbbike/Toronto/),
retrieved on November 20, 2026.

To refresh, download the current Toronto PBF from BBBike. Install `osmium` and
`shapely` in a separate extraction environment, then regenerate and import the
snapshot. The running app and the import command do not need those packages.

```powershell
python -m scripts.build_restaurant_catalog Toronto.osm.pbf data/gta-restaurants.json --source-url https://download.bbbike.org/osm/bbbike/Toronto/Toronto.osm.pbf --retrieved-on YYYY-MM-DD
python -m scripts.import_restaurant_catalog
```
