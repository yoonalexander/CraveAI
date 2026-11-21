"""Build the GTA seed from a regional OSM PBF (requires osmium and shapely)."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import osmium
from shapely import Point, from_wkb
from shapely.errors import GEOSException
from shapely.geometry import mapping

CITIES = ("Toronto", "Mississauga")
FOOD_AMENITIES = {"restaurant", "fast_food"}
FACTORY = osmium.geom.WKBFactory()


def coordinates(geometry):
    point = geometry.representative_point()
    return round(point.y, 6), round(point.x, 6)


def website(tags):
    value = tags.get("website", tags.get("contact:website", "")).strip()
    try:
        parsed = urlsplit(value)
        if len(value) <= 500 and parsed.scheme in {"https", "http"} and parsed.hostname:
            return value
    except ValueError:
        pass
    return ""


class Extractor(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.boundaries = {}
        self.restaurants = {}

    def add(self, kind, id, tags, lat, lng):
        street = " ".join(part for key in ("addr:housenumber", "addr:street")
                          if (part := tags.get(key)))
        row_id = f"osm:{kind}:{id}"
        self.restaurants[row_id] = {
            "id": row_id, "name": tags["name"].strip()[:200], "lat": lat, "lng": lng,
            "address": street[:300], "cuisine": tags.get("cuisine", "")[:250], "website": website(tags),
        }

    def node(self, node):
        if node.tags.get("amenity") in FOOD_AMENITIES and node.tags.get("name") and node.location.valid():
            self.add("node", node.id, node.tags, round(node.lat, 6), round(node.lon, 6))

    def area(self, area):
        tags = area.tags
        name = tags.get("name")
        boundary = tags.get("boundary") == "administrative" and name in CITIES
        restaurant = tags.get("amenity") in FOOD_AMENITIES and name
        if not boundary and not restaurant:
            return
        try:
            geometry = from_wkb(bytes.fromhex(FACTORY.create_multipolygon(area)))
        except (RuntimeError, GEOSException):
            return
        if boundary:
            if geometry.is_valid and not geometry.is_empty:
                self.boundaries[name] = geometry
        elif not geometry.is_empty:
            kind = "way" if area.from_way() else "relation"
            self.add(kind, area.orig_id(), tags, *coordinates(geometry))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-on", required=True)
    parser.add_argument("--boundaries-output", type=Path)
    args = parser.parse_args()
    extractor = Extractor()
    extractor.apply_file(args.pbf, locations=True, idx="flex_mem")
    if set(extractor.boundaries) != set(CITIES):
        parser.error("The extract must contain both complete municipal boundaries.")
    counts = dict.fromkeys(CITIES, 0)
    rows = []
    for row in sorted(extractor.restaurants.values(), key=lambda row: row["id"]):
        if not row["name"]:
            continue
        point = Point(row["lng"], row["lat"])
        for city, boundary in extractor.boundaries.items():
            if boundary.covers(point):
                counts[city] += 1
                rows.append(row)
                break
    if not all(counts.values()):
        parser.error("The extract did not produce listings for both municipalities.")
    with osmium.io.Reader(str(args.pbf)) as reader:
        data_timestamp = reader.header().get("osmosis_replication_timestamp")
    snapshot = {"source": args.source_url, "retrieved_on": args.retrieved_on,
                "data_timestamp": data_timestamp or None, "license": "ODbL-1.0",
                "counts": counts, "restaurants": rows}
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(snapshot, output, ensure_ascii=False, separators=(",", ":"))
        output.write("\n")
    if args.boundaries_output:
        args.boundaries_output.write_text(json.dumps({
            city: mapping(extractor.boundaries[city]) for city in CITIES
        }), encoding="utf-8")
    print(counts)


if __name__ == "__main__":
    main()
