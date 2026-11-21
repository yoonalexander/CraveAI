"""Replay the chat catalog pilot against the frozen menu-index holdout."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import CatalogDish, CatalogRestaurant
from backend.services import chat_catalog, evidence_ranker, rag_pipeline, restaurant_retrieval
from backend.services.places import is_coordinate_in_bounds
from backend.services.recommendation_models import CravingIntent, EvidenceItem
from scripts.evaluate_menu_index_pilot import DATA, intent_for, location_for
from scripts.import_catalog_menus import REVIEWED, read_reviewed
from scripts.import_restaurant_catalog import SNAPSHOT, read_catalog_rows


def verified_venues(recommendations: list[dict]) -> set[str]:
    return {item["name"] for item in recommendations if item["matching_dishes"] and any(
        evidence["type"] == "official_menu" for evidence in item["evidence"]
    )}


async def evaluate() -> dict:
    catalog = {item["id"]: item for item in read_catalog_rows(SNAPSHOT) if item["listed"]}
    reviewed = read_reviewed(REVIEWED, catalog)
    fixture = json.loads(DATA.read_text(encoding="utf-8"))
    provider_rows = {f"provider-{row['id']}": {**catalog[row["id"]], **row} for row in fixture["restaurants"]}
    cases = json.loads(Path(DATA.with_name("menu_index_holdout.json")).read_text(encoding="utf-8"))
    cases += [
        {"id": "b01", "query": "Thai restaurants nearby", "center": [43.662, -79.382], "terms": ["Thai"], "cuisine": True},
        {"id": "b02", "query": "Italian restaurants near Port Credit", "center": [43.553, -79.588], "terms": ["Italian"], "cuisine": True},
        {"id": "b03", "query": "Boat noodles near Ottawa", "center": [45.42, -75.70], "terms": ["boat noodles"]},
        {"id": "p01", "query": "Three-piece deep-fried gyoza under $9", "center": [43.578, -79.652], "terms": ["gyoza"]},
        {"id": "p02", "query": "16-inch pepperoni pizza under $15", "center": [43.581, -79.575], "terms": ["pepperoni pizza"]},
        {"id": "p03", "query": "12-inch pepperoni pizza at most $14.25", "center": [43.581, -79.575], "terms": ["pepperoni pizza"]},
    ]

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(CatalogRestaurant.__table__.insert(), list(catalog.values()))
        connection.execute(CatalogDish.__table__.insert(), [dish for rows in reviewed.values() for dish in rows])

    async def replay(case: dict, use_catalog: bool) -> dict:
        intent = intent_for(case)
        if case.get("cuisine"):
            intent = intent.model_copy(update={"constraints": [
                intent.constraints[0].model_copy(update={"dimension": "cuisine"})
            ]})
        location = location_for(*case["center"])
        calls = 0

        async def retrieve(_intent, area, _pool, **_options):
            nonlocal calls
            calls += 1
            return [
                {"place_id": provider_id, **{key: row[key] for key in ("name", "address", "lat", "lng")}, "evidence": []}
                for provider_id, row in provider_rows.items()
                if is_coordinate_in_bounds(row["lat"], row["lng"], area["bounds"])
            ]

        async def enrich(places: list[dict], _intent: CravingIntent):
            for place in places:
                row = provider_rows.get(place["place_id"], {})
                for number, dish in enumerate(row.get("dishes", []), start=1):
                    place["evidence"].append(EvidenceItem(
                        id=f"{place['place_id']}:fixture:{number}", kind="official_menu",
                        label=dish["name"], detail=dish["detail"], source_url=dish["source"], quality=1,
                    ).model_dump())
            return places

        async def extract(_query):
            return intent

        async def assess(parsed, candidates):
            return evidence_ranker._lexical_assessments(parsed, candidates)

        with (
            patch.object(chat_catalog, "get_session_factory", return_value=sessionmaker(engine)),
            patch.object(rag_pipeline, "extract_craving_intent", extract),
            patch.object(rag_pipeline, "retrieve_candidate_restaurants", retrieve),
            patch.object(rag_pipeline, "enrich_candidates_with_menu_evidence", enrich),
            patch.object(rag_pipeline, "assess_candidate_evidence", assess),
        ):
            result = await rag_pipeline.generate_recommendations(case["query"], location, use_catalog=use_catalog)
        if "timed out" in result["reply"] or "search failed" in result["reply"]:
            raise RuntimeError(result["reply"])
        return {
            "places_replays": calls, "catalog_candidates": result["catalog_candidates"],
            "recommendations": result["recommendations"],
        }

    results = []
    for case in cases:
        baseline = await replay(case, False)
        merged = await replay(case, True)
        lost = verified_venues(baseline["recommendations"]) - verified_venues(merged["recommendations"])
        results.append({"id": case["id"], "query": case["query"], "baseline": baseline,
                        "merged": merged, "verified_venues_displaced": sorted(lost)})
    report = {
        "cases": results,
        "summary": {
            mode: {
                "places_replays": sum(row[mode]["places_replays"] for row in results),
                "queries_with_recommendations": sum(bool(row[mode]["recommendations"]) for row in results),
                "queries_with_menu_evidence": sum(bool(verified_venues(row[mode]["recommendations"])) for row in results),
            }
            for mode in ("baseline", "merged")
        },
        "queries_with_verified_venues_displaced": [row["id"] for row in results if row["verified_venues_displaced"]],
    }
    engine.dispose()
    return report


if __name__ == "__main__":
    rag_pipeline.logger.setLevel(logging.WARNING)
    print(json.dumps(asyncio.run(evaluate()), indent=2))
