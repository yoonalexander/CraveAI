"""Import reviewed menu facts and a complete first-pass source report."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import get_engine
from backend.models import CatalogDish, CatalogMenuCheck, CatalogRestaurant
from backend.services.menu_index import MAX_DISHES_PER_FAMILY, MAX_DISHES_PER_RESTAURANT, _dish_family, _dish_key
from scripts.import_restaurant_catalog import REFRESH_LOCK, SNAPSHOT, read_catalog_rows

REVIEWED = SNAPSHOT.with_name("gta-menu-reviewed.json")
OUTCOMES = {"no_website", "source_issue", "no_readable_dishes", "candidates"}
CHANNELS = {"published_menu", "dine_in", "pickup", "delivery"}


def read_checks(path: Path, catalog: dict[str, dict]) -> list[dict]:
    checks = {}
    with path.open(encoding="utf-8") as report:
        for line in report:
            entry = json.loads(line)
            restaurant_id = entry["restaurant_id"]
            outcome = entry["outcome"]
            count = entry["candidates"]
            if (restaurant_id in checks or restaurant_id not in catalog or outcome not in OUTCOMES
                    or not isinstance(count, int) or not 0 <= count <= MAX_DISHES_PER_RESTAURANT
                    or (outcome == "candidates") != (count > 0)
                    or (outcome == "no_website") != (not catalog[restaurant_id]["website"])):
                raise ValueError(f"Invalid menu check for {restaurant_id}")
            checks[restaurant_id] = {
                "restaurant_id": restaurant_id, "outcome": outcome, "candidates": count,
                "checked_on": date.fromisoformat(entry["checked_on"]),
                "documents": entry["documents"], "issues": entry["issues"],
            }
    if checks.keys() != catalog.keys():
        raise ValueError(f"Source report is missing {len(catalog.keys() - checks.keys())} active catalog IDs.")
    return list(checks.values())


def read_reviewed(path: Path, catalog: dict[str, dict]) -> dict[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    checked_on = date.fromisoformat(data["checked_on"])
    reviewed = {}
    for listing in data["restaurants"]:
        restaurant_id = listing["id"]
        dishes = listing["dishes"]
        if restaurant_id in reviewed or restaurant_id not in catalog or not 1 <= len(dishes) <= MAX_DISHES_PER_RESTAURANT:
            raise ValueError(f"Invalid reviewed listing {restaurant_id}")
        rows = []
        families = Counter()
        keys = set()
        for slot, dish in enumerate(dishes, start=1):
            name = dish["name"].strip()
            key = _dish_key(name)
            family = _dish_key(dish["family"]) if "family" in dish else _dish_family(key)
            url = dish["source_url"]
            parsed = urlsplit(url)
            channel = dish["channel"]
            if (not key or key in keys or len(name) > 160 or len(key) > 160 or not 1 <= len(family) <= 160
                    or parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or len(url) > 500 or channel not in CHANNELS):
                raise ValueError(f"Invalid reviewed dish for {restaurant_id}: {name}")
            keys.add(key)
            families[family] += 1
            if families[family] > MAX_DISHES_PER_FAMILY:
                raise ValueError(f"Too many dishes in the {family} family for {restaurant_id}")
            amounts = dish.get("prices", {})
            if not isinstance(amounts, dict) or any(
                type(amount) is not int or not 0 < amount <= 1_000_000 or len(option) > 80
                for option, amount in amounts.items()
            ):
                raise ValueError(f"Invalid price for {restaurant_id}: {name}")
            prices = [
                {"option": option or None, "amount_cents": amount, "currency": "CAD"}
                for option, amount in amounts.items()
            ]
            rows.append({
                "restaurant_id": restaurant_id, "slot": slot, "dish_key": key, "name": name,
                "family": family, "source_url": url, "checked_on": checked_on,
                "channel": channel, "prices": prices,
            })
        reviewed[restaurant_id] = rows
    return reviewed


def import_index(connection, checks: list[dict], reviewed: dict[str, list[dict]]) -> None:
    check_table = CatalogMenuCheck.__table__
    dishes = CatalogDish.__table__
    if connection.dialect.name == "postgresql":
        connection.execute(text(REFRESH_LOCK))
        upsert = postgres_insert(check_table)
    elif connection.dialect.name == "sqlite":
        upsert = sqlite_insert(check_table)
    else:
        raise ValueError("Use PostgreSQL or SQLite to import the catalog menu index.")

    active = set(connection.scalars(select(CatalogRestaurant.id).where(CatalogRestaurant.listed.is_(True))))
    if active != {row["restaurant_id"] for row in checks}:
        raise ValueError("The destination catalog differs from the menu check report.")
    upsert = upsert.on_conflict_do_update(
        index_elements=[check_table.c.restaurant_id],
        set_={col.name: upsert.excluded[col.name] for col in check_table.columns if not col.primary_key},
        where=check_table.c.checked_on <= upsert.excluded.checked_on,
    )
    for start in range(0, len(checks), 500):
        connection.execute(upsert, checks[start:start + 500])
    dates = defaultdict(list)
    for restaurant_id, rows in reviewed.items():
        dates[rows[0]["checked_on"]].append(restaurant_id)
    for checked_on, ids in dates.items():
        newer = set(connection.scalars(select(dishes.c.restaurant_id).where(
            dishes.c.restaurant_id.in_(ids), dishes.c.checked_on > checked_on,
        )))
        replace = [restaurant_id for restaurant_id in ids if restaurant_id not in newer]
        if replace:
            connection.execute(delete(dishes).where(dishes.c.restaurant_id.in_(replace)))
            connection.execute(dishes.insert(), [row for restaurant_id in replace for row in reviewed[restaurant_id]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--reviewed", type=Path, default=REVIEWED)
    args = parser.parse_args()
    catalog = {row["id"]: row for row in read_catalog_rows(SNAPSHOT) if row["listed"]}
    checks = read_checks(args.checks, catalog)
    reviewed = read_reviewed(args.reviewed, catalog)
    with get_engine().begin() as connection:
        import_index(connection, checks, reviewed)
    print(f"Imported {len(checks):,} source checks and {sum(map(len, reviewed.values())):,} reviewed dishes.")


if __name__ == "__main__":
    main()
