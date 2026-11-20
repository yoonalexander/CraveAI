"""Load the versioned GTA restaurant snapshot into the configured database."""
import argparse
import json
from pathlib import Path

from sqlalchemy import delete, insert

from backend.database import get_engine
from backend.models import CatalogRestaurant

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "gta-restaurants.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    rows = snapshot["restaurants"]
    counts = snapshot["counts"]
    if set(counts) != {"Toronto", "Mississauga"} or not all(counts.values()) or sum(counts.values()) != len(rows):
        parser.error("The snapshot must contain a complete import for both pilot cities.")

    # Replace the snapshot transactionally so a failed import preserves the
    # previous catalog and readers never see a partially loaded city.
    with get_engine().begin() as connection:
        connection.execute(delete(CatalogRestaurant))
        connection.execute(insert(CatalogRestaurant), rows)
    print(f"Imported {len(rows):,} restaurants: {counts}")


if __name__ == "__main__":
    main()
