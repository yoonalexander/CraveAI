from __future__ import annotations

import asyncio

from backend.services import rag_pipeline
from backend.services.craving_intent import fallback_intent, normalize_intent
from backend.services.evidence_ranker import rank_evidence_candidates, score_candidate
from backend.services.menu_evidence import (
    _parse_html,
    _select_relevant_blocks,
    _validate_public_url,
)
from backend.services.recommendation_models import (
    CandidateAssessment,
    CravingIntent,
    EvidenceLink,
)
from backend.services.restaurant_retrieval import _merge_query_results


def spicy_soup_intent(*, spicy_strength: str = "strong") -> CravingIntent:
    return CravingIntent.model_validate(
        {
            "summary": "Spicy soup",
            "constraints": [
                {
                    "id": "c1",
                    "dimension": "taste",
                    "value": "spicy",
                    "polarity": "include",
                    "strength": spicy_strength,
                },
                {
                    "id": "c2",
                    "dimension": "dish_type",
                    "value": "soup",
                    "polarity": "include",
                    "strength": "preferred",
                },
            ],
            "candidate_dishes": ["hot and sour soup", "spicy ramen", "tom yum"],
            "search_queries": [
                {"text": "spicy soup", "constraint_ids": ["c1", "c2"]}
            ],
        }
    )


def evidence(
    evidence_id: str,
    label: str,
    *,
    detail: str = "",
    kind: str = "official_menu",
    quality: float = 1.0,
    declared: list[str] | None = None,
    rank: int | None = None,
) -> dict:
    return {
        "id": evidence_id,
        "kind": kind,
        "label": label,
        "detail": detail,
        "source_url": "https://example.com/menu" if kind.startswith("official") else None,
        "quality": quality,
        "declared_constraint_ids": declared or [],
        "retrieval_rank": rank,
    }


def candidate(place_id: str, name: str, evidence_items: list[dict], rating: float = 4.5) -> dict:
    return {
        "place_id": place_id,
        "name": name,
        "rating": rating,
        "address": "123 Test Street",
        "lat": 43.5,
        "lng": -79.7,
        "evidence": evidence_items,
    }


def assessment(place_id: str, *links: tuple[str, list[str], str]) -> CandidateAssessment:
    return CandidateAssessment(
        place_id=place_id,
        links=[
            EvidenceLink(evidence_id=item[0], constraint_ids=item[1], stance=item[2])
            for item in links
        ],
    )


def test_normalize_intent_preserves_maybe_as_preference_and_drops_inferred_trait():
    raw = CravingIntent.model_validate(
        {
            "summary": "Spicy soup",
            "constraints": [
                {
                    "id": "spice",
                    "dimension": "taste",
                    "value": "spicy",
                    "polarity": "include",
                    "strength": "required",
                },
                {
                    "id": "soup",
                    "dimension": "dish_type",
                    "value": "soup",
                    "polarity": "include",
                    "strength": "required",
                },
                {
                    "id": "invented",
                    "dimension": "texture",
                    "value": "brothy",
                    "polarity": "include",
                    "strength": "preferred",
                },
            ],
            "candidate_dishes": ["hot and sour soup"],
            "search_queries": [
                {"text": "spicy soup", "constraint_ids": ["spice", "soup"]}
            ],
        }
    )

    normalized = normalize_intent(
        raw,
        "im craving something spicy, maybe like a soup",
    )

    assert [(item.value, item.strength) for item in normalized.constraints] == [
        ("spicy", "strong"),
        ("soup", "preferred"),
    ]
    assert normalized.search_queries[0].constraint_ids == ["c1", "c2"]


def test_fallback_intent_distinguishes_hard_soft_and_excluded_constraints():
    intent = fallback_intent("I need soup, preferably spicy, but no pork")
    by_value = {item.value: item for item in intent.constraints}

    assert by_value["soup"].strength == "required"
    assert by_value["spicy"].strength == "preferred"
    assert by_value["pork"].polarity == "exclude"


def test_menu_parser_extracts_structured_menu_items_without_inventing_text():
    page = _parse_html(
        """
        <html><body><script type="application/ld+json">
        {"@type":"Menu","hasMenuItem":[
          {"@type":"MenuItem","name":"Hot & Sour Soup","description":"Spicy broth"},
          {"@type":"MenuItem","name":"French Onion Soup","description":"Cheesy toast"}
        ]}
        </script></body></html>
        """
    )

    assert page.menu_items == [
        ("Hot & Sour Soup", "Spicy broth"),
        ("French Onion Soup", "Cheesy toast"),
    ]


def test_visible_menu_evidence_does_not_fuse_adjacent_dishes():
    selected = _select_relevant_blocks(
        [
            ("Hot & Spicy Garlic Ribs", "https://example.com/menu"),
            ("Hunan Beef Soup", "https://example.com/menu"),
        ],
        spicy_soup_intent(),
    )

    assert {item[0] for item in selected} == {
        "Hot & Spicy Garlic Ribs",
        "Hunan Beef Soup",
    }
    assert all(" | " not in item[0] for item in selected)


def test_menu_fetch_guard_rejects_local_and_private_networks():
    for url in ("http://localhost/menu", "http://127.0.0.1/menu", "http://[::1]/menu"):
        try:
            asyncio.run(_validate_public_url(url))
        except ValueError:
            continue
        raise AssertionError(f"Expected {url} to be rejected")


def test_query_results_are_deduplicated_and_keep_each_query_as_evidence():
    first = candidate(
        "same",
        "Same Place",
        [evidence("pending", "spicy soup", kind="provider_query", quality=0.55, declared=["c1", "c2"], rank=1)],
    )
    first["retrieval_score"] = 1.0
    second = candidate(
        "same",
        "Same Place",
        [evidence("pending", "hot and sour soup", kind="provider_query", quality=0.55, declared=["c1", "c2"], rank=2)],
    )
    second["retrieval_score"] = 0.8

    merged = _merge_query_results([[first], [second]])

    assert list(merged) == ["same"]
    assert merged["same"]["retrieval_score"] == 1.8
    assert [item["label"] for item in merged["same"]["evidence"]] == [
        "spicy soup",
        "hot and sour soup",
    ]


def test_spicy_soup_requires_same_dish_overlap_and_filters_partial_matches():
    intent = spicy_soup_intent()
    places = [
        candidate(
            "axia",
            "Axia",
            [evidence("axia:e1", "Tom Yum Noodle Soup", detail="Tangy and spicy broth")],
            4.2,
        ),
        candidate(
            "franklin",
            "Franklin House",
            [
                evidence("franklin:e1", "French Onion Soup"),
                evidence("franklin:e2", "Spicy Buffalo Wings"),
            ],
            4.8,
        ),
        candidate(
            "brasas",
            "Brasas",
            [evidence("brasas:e1", "Spicy Piri-Piri Chicken")],
            4.9,
        ),
    ]
    assessments = [
        assessment("axia", ("axia:e1", ["c1", "c2"], "supports")),
        assessment(
            "franklin",
            ("franklin:e1", ["c2"], "supports"),
            ("franklin:e2", ["c1"], "supports"),
        ),
        assessment("brasas", ("brasas:e1", ["c1"], "supports")),
    ]

    result = rank_evidence_candidates(intent, places, assessments)

    assert [item["place_id"] for item in result["recommendations"]] == ["axia"]
    assert result["recommendations"][0]["matching_dishes"] == ["Tom Yum Noodle Soup"]
    assert "Tom Yum Noodle Soup" in result["recommendations"][0]["reason"]
    assert "French Onion" not in result["recommendations"][0]["reason"]


def test_combo_components_do_not_count_as_one_coherent_matching_dish():
    intent = spicy_soup_intent()
    place = candidate(
        "combo",
        "Combo Restaurant",
        [
            evidence(
                "combo:e1",
                "Roll Bento Box",
                detail="Spicy salmon roll, salad, and plain miso soup.",
            )
        ],
    )
    links = assessment("combo", ("combo:e1", ["c1", "c2"], "supports"))

    assert score_candidate(intent, place, links) is None


def test_explicit_required_constraint_rejects_provider_query_without_menu_proof():
    intent = spicy_soup_intent(spicy_strength="required")
    place = candidate(
        "provider-only",
        "Provider Only",
        [
            evidence(
                "provider-only:e1",
                "spicy soup",
                kind="provider_query",
                quality=0.55,
                declared=["c1", "c2"],
                rank=1,
            )
        ],
    )

    assert score_candidate(intent, place, assessment("provider-only")) is None


def test_provider_only_match_is_labeled_unverified_instead_of_hallucinating_dish():
    intent = spicy_soup_intent()
    place = candidate(
        "provider",
        "Provider Match",
        [
            evidence(
                "provider:e1",
                "spicy soup",
                kind="provider_query",
                quality=0.55,
                declared=["c1", "c2"],
                rank=1,
            )
        ],
        4.8,
    )

    result = score_candidate(intent, place, assessment("provider"))

    assert result is not None
    assert result["confidence"] == "medium"
    assert result["matching_dishes"] == []
    assert "Menu not verified" in result["reason"]


def test_named_official_site_menu_evidence_is_exposed_as_a_matching_dish():
    intent = spicy_soup_intent()
    place = candidate(
        "site-menu",
        "Site Menu",
        [
            evidence(
                "site-menu:e1",
                "Szechuan Mala Spicy Rice Noodle Soup",
                kind="official_website",
                quality=0.8,
            )
        ],
    )
    links = assessment("site-menu", ("site-menu:e1", ["c1", "c2"], "supports"))

    result = score_candidate(intent, place, links)

    assert result is not None
    assert result["matching_dishes"] == ["Szechuan Mala Spicy Rice Noodle Soup"]
    assert result["confidence"] == "medium"


def test_hard_exclusion_removes_violating_dish_but_can_keep_safe_dish():
    intent = CravingIntent.model_validate(
        {
            "summary": "Korean, not fried",
            "constraints": [
                {"id": "c1", "dimension": "cuisine", "value": "Korean", "polarity": "include", "strength": "strong"},
                {"id": "c2", "dimension": "texture", "value": "fried", "polarity": "exclude", "strength": "required"},
            ],
            "candidate_dishes": ["bibimbap", "jjigae"],
            "search_queries": [{"text": "Korean non-fried dishes", "constraint_ids": ["c1"]}],
        }
    )
    place = candidate(
        "korean",
        "Korean Kitchen",
        [
            evidence("korean:e1", "Korean Fried Chicken"),
            evidence("korean:e2", "Dolsot Bibimbap"),
        ],
    )
    links = assessment(
        "korean",
        ("korean:e1", ["c1"], "supports"),
        ("korean:e1", ["c2"], "violates"),
        ("korean:e2", ["c1"], "supports"),
    )

    result = score_candidate(intent, place, links)

    assert result is not None
    assert result["matching_dishes"][0] == "Dolsot Bibimbap"


def test_unknown_evidence_ids_cannot_appear_in_grounded_reason():
    intent = spicy_soup_intent()
    place = candidate(
        "known",
        "Known",
        [evidence("known:e1", "Hot & Sour Soup", detail="Spicy")],
    )
    links = assessment(
        "known",
        ("invented:e9", ["c1", "c2"], "supports"),
    )

    assert score_candidate(intent, place, links) is None


def test_pipeline_timeout_returns_no_ungrounded_rating_fallback(monkeypatch):
    async def slow_intent(_query):
        await asyncio.sleep(0.05)
        return spicy_soup_intent()

    monkeypatch.setattr(rag_pipeline, "extract_craving_intent", slow_intent)
    monkeypatch.setattr(rag_pipeline, "PIPELINE_TIMEOUT_SECONDS", 0.005)

    result = asyncio.run(
        rag_pipeline.generate_recommendations(
            "spicy soup",
            {"lat": 43.5, "lng": -79.7},
        )
    )

    assert result["recommendations"] == []
    assert "verify" in result["reply"].lower()
