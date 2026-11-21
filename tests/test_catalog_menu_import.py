from datetime import date
from pathlib import Path
import json

import pytest
from sqlalchemy import create_engine, select

from backend.database import Base
from backend.models import CatalogDish, CatalogMenuCheck, CatalogRestaurant
from scripts.import_catalog_menus import REVIEWED, import_index, read_checks, read_reviewed
from scripts.import_restaurant_catalog import SNAPSHOT, read_catalog_rows, refresh_catalog


def test_reviewed_index_keeps_official_prices_with_their_portions():
    catalog = {row["id"]: row for row in read_catalog_rows(SNAPSHOT) if row["listed"]}
    reviewed = read_reviewed(REVIEWED, catalog)
    boat = reviewed["osm:node:1157114350"]
    assert len(boat) == 6
    assert sum(dish["family"] == "noodle soup" for dish in boat) == 2
    assert boat[0]["prices"] == [
        {"option": "Small", "amount_cents": 1500, "currency": "CAD"},
        {"option": "Medium", "amount_cents": 2000, "currency": "CAD"},
    ]


def test_menu_import_is_repeatable_and_a_missing_menu_keeps_the_listing(tmp_path: Path):
    dish_id, empty_id = "osm:node:1157114350", "osm:node:10050107272"
    catalog = {
        row["id"]: row for row in read_catalog_rows(SNAPSHOT) if row["id"] in {dish_id, empty_id}
    }
    complete = [
        {"restaurant_id": dish_id, "checked_on": "2026-11-21", "outcome": "candidates",
         "candidates": 6, "documents": {"text/html": 3}, "issues": {}},
        {"restaurant_id": empty_id, "checked_on": "2026-11-21", "outcome": "no_website",
         "candidates": 0, "documents": {}, "issues": {}},
    ]
    report = tmp_path / "checks.jsonl"
    report.write_text(json.dumps(complete[0]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 1 active"):
        read_checks(report, catalog)
    report.write_text("\n".join(map(json.dumps, complete)), encoding="utf-8")
    checks = read_checks(report, catalog)
    seed = json.loads(REVIEWED.read_text(encoding="utf-8"))
    seed["restaurants"] = [row for row in seed["restaurants"] if row["id"] == dish_id]
    seed_path = tmp_path / "reviewed.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    dishes = read_reviewed(seed_path, catalog)
    older = date(2026, 11, 20)
    stale_dishes = {dish_id: [dict(dishes[dish_id][0], checked_on=older, prices=[])]}
    stale_checks = [dict(check, checked_on=older) for check in checks]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        refresh_catalog(connection, list(catalog.values()))
        import_index(connection, checks, dishes)
        import_index(connection, checks, dishes)
        import_index(connection, stale_checks, stale_dishes)
        refresh_catalog(connection, list(catalog.values()))
        assert connection.scalars(select(CatalogMenuCheck.checked_on)).all() == [date(2026, 11, 21)] * 2
        assert len(connection.scalars(select(CatalogDish.name)).all()) == 6
        assert connection.scalar(select(CatalogRestaurant.listed).where(CatalogRestaurant.id == empty_id))
