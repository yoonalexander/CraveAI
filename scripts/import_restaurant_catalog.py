"""Load the versioned GTA restaurant snapshot into the configured database."""
import argparse
from datetime import date
import json
from pathlib import Path

from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection

from backend.database import get_engine
from backend.models import CatalogRestaurant

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "gta-restaurants.json"
REFRESH_LOCK = "SELECT pg_advisory_xact_lock(482207106)"
TABLE = CatalogRestaurant.__table__
UPDATE_FIELDS = [column.name for column in TABLE.columns if column.name != "id"]


def read_catalog_rows(snapshot_path: Path) -> list[dict]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = snapshot["restaurants"]
    counts = snapshot["counts"]
    if set(counts) != {"Toronto", "Mississauga"} or not all(counts.values()) or sum(counts.values()) != len(rows):
        raise ValueError("The snapshot must contain a complete import for both pilot cities.")
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("The snapshot contains repeated restaurant IDs.")
    timestamp = snapshot.get("data_timestamp") or snapshot.get("retrieved_on")
    checked_on = date.fromisoformat(timestamp[:10]) if timestamp else None
    for row in rows:
        row.update(listed=True, checked_on=checked_on, phone=None, hours=None)
    if snapshot_path.resolve() != SNAPSHOT.resolve():
        return rows

    reviewed = json.loads(SNAPSHOT.with_name("gta-catalog-reviewed.json").read_text(encoding="utf-8"))
    duplicates = reviewed["osm_duplicate_ids"]
    for duplicate, canonical in duplicates.items():
        if canonical not in by_id or canonical in duplicates or duplicate not in by_id:
            raise ValueError(f"Invalid duplicate mapping for {duplicate}")
        by_id[duplicate]["listed"] = False
    coverage = json.loads(SNAPSHOT.with_name("gta-restaurant-coverage.json").read_text(encoding="utf-8"))
    candidates = {row["id"]: row for city in coverage["cities"].values() for row in city["additions"]}
    for listing in reviewed["municipal_listings"]:
        candidate = candidates[listing["id"]]
        rows.append({
            **{field: candidate[field] for field in ("id", "lat", "lng", "address")},
            "name": listing["name"],
            "cuisine": listing.get("cuisine", ""),
            "website": listing["website"],
            "phone": listing.get("phone"),
            "hours": listing.get("hours"),
            "listed": True,
            "checked_on": date.fromisoformat(reviewed["checked_on"]),
        })
    return rows


def refresh_catalog(connection: Connection, rows: list[dict]) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text(REFRESH_LOCK))
        upsert = postgres_insert(TABLE)
    elif connection.dialect.name == "sqlite":
        upsert = sqlite_insert(TABLE)
    else:
        raise ValueError(f"Unsupported catalog database: {connection.dialect.name}")
    connection.execute(update(TABLE).where(TABLE.c.listed.is_(True)).values(listed=False))
    upsert = upsert.on_conflict_do_update(
        index_elements=[TABLE.c.id], set_={field: upsert.excluded[field] for field in UPDATE_FIELDS},
    )
    for start in range(0, len(rows), 500):
        connection.execute(upsert, rows[start:start + 500])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    rows = read_catalog_rows(args.snapshot)
    with get_engine().begin() as connection:
        refresh_catalog(connection, rows)
    print(f"Refreshed {sum(row['listed'] for row in rows):,} active listings from {len(rows):,} source rows.")


if __name__ == "__main__":
    main()
