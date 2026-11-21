"""Compare current recommendation retrieval with a reviewed, local dish index."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unicodedata
from unittest.mock import patch

from backend.services import evidence_ranker, menu_evidence, rag_pipeline, restaurant_retrieval
from backend.services.recommendation_models import CravingIntent, EvidenceItem
from scripts.probe_menu_index import SNAPSHOT

DATA = Path(__file__).resolve().parents[1] / "evaluation" / "menu_index_pilot.json"
RADIUS_METRES = 3000


def normalize(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(ch)
    )


def intent_for(case: dict) -> CravingIntent:
    constraints = [
        {"id": f"c{index}", "dimension": "dish_type" if index == 0 else "ingredient",
         "value": term, "polarity": "include", "strength": "required"}
        for index, term in enumerate(case["terms"])
    ]
    if "under" in case:
        constraints.append({"id": "budget", "dimension": "price", "value": "published price below requested limit",
                            "polarity": "include", "strength": "required"})
    return CravingIntent(
        summary=case["query"], constraints=constraints, candidate_dishes=[case["terms"][0]],
        search_queries=[{"text": case["query"], "constraint_ids": [
            item["id"] for item in constraints if item["dimension"] != "price"
        ]}],
    )


def location_for(lat: float, lng: float) -> dict:
    south, west, north, east = restaurant_retrieval._bounding_box(lat, lng, RADIUS_METRES)
    return {"lat": lat, "lng": lng, "radius": RADIUS_METRES,
            "bounds": {"south": south, "west": west, "north": north, "east": east}}


def local_candidates(case: dict, intent: CravingIntent, nearby: list[dict]) -> tuple[list[dict], list[dict]]:
    candidates, price_evidence = [], []
    for restaurant in nearby:
        evidence = []
        for index, dish in enumerate(restaurant["dishes"]):
            text = normalize(f"{dish['name']} {dish['detail']}")
            if not all(normalize(term) in text for term in case["terms"]):
                continue
            prices = {option: amount for option, amount in dish["prices"].items()
                      if case.get("option") in (None, option) and amount < case.get("under", 0)}
            if "under" in case and not prices:
                continue
            if prices:
                price_evidence.append({"restaurant": restaurant["id"], "dish": dish["name"], "cad_cents": prices})
            evidence.append(EvidenceItem(
                id=f"{restaurant['id']}:pilot:{index}", kind="official_menu", label=dish["name"],
                detail=dish["detail"], source_url=dish["source"], quality=1,
                declared_constraint_ids=[constraint.id for constraint in intent.constraints],
            ).model_dump())
        if evidence:
            candidates.append({
                "place_id": restaurant["id"], "name": restaurant["name"], "address": restaurant["address"],
                "lat": restaurant["lat"], "lng": restaurant["lng"], "evidence": evidence,
            })
    return candidates, price_evidence


async def evaluate(data: dict) -> dict:
    catalog = {row["id"]: row for row in json.loads(SNAPSHOT.read_text(encoding="utf-8"))["restaurants"]}
    restaurants = [{**catalog[row["id"]], **row} for row in data["restaurants"]]
    assert len({row["id"] for row in restaurants}) == 10 and sum(len(r["dishes"]) for r in restaurants) == 20

    fetch_html = menu_evidence._safe_fetch_html
    fetched: dict = {}
    fetch_errors: set[str] = set()

    async def capture_html(client, url):
        if url not in fetched:
            try:
                fetched[url] = await fetch_html(client, url)
            except Exception as error:
                fetched[url] = error
                fetch_errors.add(url)
        result = fetched[url]
        if isinstance(result, Exception):
            raise result
        return result

    async def assess(intent, candidates):
        return evidence_ranker._lexical_assessments(intent, candidates)

    async def run_case(case: dict, index_first: bool) -> dict:
        intent = intent_for(case)
        center = case.get("center")
        if center is None:
            anchor = restaurants[case["near"]]
            center = (anchor["lat"], anchor["lng"])
        location = location_for(*center)
        nearby = [r for r in restaurants if restaurant_retrieval.is_coordinate_in_bounds(
            r["lat"], r["lng"], location["bounds"]
        )]
        calls = 0
        price_options = []
        used_index = False

        async def places_response(*args, **kwargs):
            nonlocal calls
            calls += 1
            return [
                {"id": r["id"], "displayName": {"text": r["name"]}, "formattedAddress": r["address"],
                 "location": {"latitude": r["lat"], "longitude": r["lng"]},
                 "types": ["restaurant"], "websiteUri": r["website"]}
                for r in nearby[:10]
            ]

        async def fallback(*args, **kwargs):
            nonlocal calls
            calls += 1
            return {}

        async def fixed_intent(*args):
            return intent

        async def retrieve(parsed, area, session_pool):
            nonlocal price_options, used_index
            if index_first:
                candidates, price_options = local_candidates(case, parsed, nearby)
                if candidates:
                    used_index = True
                    return candidates
            return await restaurant_retrieval.retrieve_candidate_restaurants(parsed, area, session_pool)

        with (
            patch.object(restaurant_retrieval, "get_settings", return_value=SimpleNamespace(GOOGLE_API_KEY="fixture")),
            patch.object(restaurant_retrieval, "_search_text", places_response),
            patch.object(restaurant_retrieval, "_legacy_provider_fallback", fallback),
            patch.object(rag_pipeline, "extract_craving_intent", fixed_intent),
            patch.object(rag_pipeline, "retrieve_candidate_restaurants", retrieve),
            patch.object(rag_pipeline, "assess_candidate_evidence", assess),
            patch.object(menu_evidence, "_safe_fetch_html", capture_html),
        ):
            result = await rag_pipeline.generate_recommendations(case["query"], location)

        if "search failed" in result["reply"] or "search timed out" in result["reply"]:
            raise RuntimeError(f"Pipeline did not complete for {case['id']}: {result['reply']}")
        top = result["recommendations"][:3]
        expected = {
            (restaurants[restaurant]["id"], normalize(restaurants[restaurant]["dishes"][dish]["name"]))
            for restaurant, dish in case.get("expected", [])
        } | {
            (restaurants[row["restaurant"]]["id"], normalize(row["dish"]))
            for row in case.get("fallback_expected", [])
        }
        returned = {(r["place_id"], normalize(dish)) for r in top for dish in r["matching_dishes"]}
        outcome = {
            "places_calls_replayed": calls,
            "used_index": used_index,
            "top3": [{"restaurant": r["name"], "dishes": r["matching_dishes"], "evidence": r["evidence"]}
                     for r in top],
            "verified_price_options": [
                row for row in price_options if (row["restaurant"], normalize(row["dish"])) in returned
            ],
        }
        if "expected" in case:
            outcome.update(
                verified_hit=bool(expected & returned),
                correct_abstention=bool(not expected and not top),
                unexpected_restaurants=[r["name"] for r in top if not any(
                    (r["place_id"], normalize(dish)) in expected for dish in r["matching_dishes"]
                )],
            )
        return outcome

    outcomes = [
        {"id": case["id"], "query": case["query"],
         "current": await run_case(case, False), "index_first": await run_case(case, True)}
        for case in data["cases"]
    ]
    scored = all("expected" in case for case in data["cases"])
    metrics = {}
    for mode in ("current", "index_first"):
        rows = [row[mode] for row in outcomes]
        metrics[mode] = {
            "places_calls_replayed": sum(row["places_calls_replayed"] for row in rows),
            "queries_with_results": sum(bool(row["top3"]) for row in rows),
        }
        if scored:
            metrics[mode].update(
                verified_hits=sum(row["verified_hit"] for row in rows),
                correct_abstentions=sum(row["correct_abstention"] for row in rows),
                unverified_recommendations=sum(len(row["unexpected_restaurants"]) for row in rows),
            )
    return {
        "cases": outcomes, "unique_menu_urls_attempted": len(fetched), "menu_url_errors": len(fetch_errors),
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, help="Use a separate JSON query set.")
    parser.add_argument("--verbose", action="store_true", help="Include pipeline log messages on stderr.")
    args = parser.parse_args()
    if not args.verbose:
        rag_pipeline.logger.setLevel(logging.WARNING)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if args.queries:
        data["cases"] = json.loads(args.queries.read_text(encoding="utf-8"))
    print(json.dumps(asyncio.run(evaluate(data)), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
