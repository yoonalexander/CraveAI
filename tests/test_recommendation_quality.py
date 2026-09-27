from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.services import evidence_ranker, rag_pipeline
from backend.services.craving_intent import fallback_intent, normalize_intent
from backend.services.evidence_ranker import rank_evidence_candidates, score_candidate
from backend.services.menu_evidence import (
    _parse_html,
    _select_relevant_blocks,
    _validate_public_url,
)
from backend.services.recommendation_models import (
    AssessmentBatch,
    CandidateAssessment,
    CravingIntent,
    EvidenceLink,
)
from backend.services import restaurant_retrieval
from backend.services.restaurant_retrieval import _merge_query_results
from backend.services.venue_constraints import candidate_matches_venue_constraints


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


def test_retrieval_never_returns_candidates_outside_confirmed_bounds(monkeypatch):
    intent = spicy_soup_intent()

    async def fake_fallback(_intent, _location):
        return {
            "inside": {
                "place_id": "inside",
                "name": "Inside Soup",
                "lat": 43.7,
                "lng": -79.4,
                "rating": 4.5,
                "retrieval_score": 0.4,
                "evidence": [],
            },
            "outside": {
                "place_id": "outside",
                "name": "Outside Soup",
                "lat": 43.8,
                "lng": -79.4,
                "rating": 4.9,
                "retrieval_score": 0.9,
                "evidence": [],
            },
        }

    monkeypatch.setattr(
        restaurant_retrieval,
        "get_settings",
        lambda: SimpleNamespace(GOOGLE_API_KEY=""),
    )
    monkeypatch.setattr(restaurant_retrieval, "_legacy_provider_fallback", fake_fallback)

    results = asyncio.run(
        restaurant_retrieval.retrieve_candidate_restaurants(
            intent,
            {
                "lat": 43.7,
                "lng": -79.4,
                "radius": 7500,
                "bounds": {
                    "north": 43.75,
                    "south": 43.65,
                    "east": -79.34,
                    "west": -79.46,
                },
            },
        )
    )

    assert [item["place_id"] for item in results] == ["inside"]


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


def test_fallback_intent_treats_pub_as_a_strong_venue_constraint():
    intent = fallback_intent("I want some nice pub food")

    assert [
        (item.dimension, item.value, item.strength) for item in intent.constraints
    ] == [("venue", "pub", "strong")]


def test_normalize_intent_repairs_pub_food_to_a_venue_constraint():
    raw = CravingIntent.model_validate(
        {
            "summary": "Pub food",
            "constraints": [
                {
                    "id": "pub-food",
                    "dimension": "meal",
                    "value": "pub food",
                    "polarity": "include",
                    "strength": "strong",
                }
            ],
            "candidate_dishes": [],
            "search_queries": [
                {"text": "pub food", "constraint_ids": ["pub-food"]}
            ],
        }
    )

    normalized = normalize_intent(raw, "I want some nice pub food")

    assert normalized.constraints[0].dimension == "venue"
    assert normalized.constraints[0].value == "pub"
    assert normalized.search_queries[0].constraint_ids == ["c1"]


def test_pub_constraint_rejects_non_pubs_and_accepts_explicit_pub_metadata():
    intent = fallback_intent("I want some nice pub food")

    assert not candidate_matches_venue_constraints(
        intent,
        {"name": "Axia Restaurant", "tags": ["Chinese Restaurant"]},
    )
    assert not candidate_matches_venue_constraints(
        intent,
        {"name": "WingsUp! Mississauga", "tags": ["Chicken Restaurant"]},
    )
    assert candidate_matches_venue_constraints(
        intent,
        {"name": "Cuchulainn's Irish Pub", "tags": ["Bar"]},
    )


def test_final_scorer_rejects_non_pub_returned_by_pub_text_search():
    intent = fallback_intent("I want some nice pub food")
    place = candidate(
        "axia",
        "Axia Restaurant",
        [
            evidence(
                "axia:e1",
                "pub",
                kind="provider_query",
                quality=0.55,
                declared=["c1"],
                rank=1,
            )
        ],
    )
    place["tags"] = ["Chinese Restaurant"]

    assert score_candidate(intent, place, assessment("axia")) is None


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


def malformed_evidence() -> list:
    return [
        {"id": "bad:missing", "label": "Spicy noodles"},
        evidence("bad:kind", "Spicy noodles", kind="unknown"),
        evidence("bad:quality", "Spicy noodles", quality=2.0),
        evidence("bad:rank", "Spicy noodles", rank=0),
        None,
        "Spicy noodles",
    ]


@pytest.mark.parametrize("semantic_mode", ["disabled", "success", "failure", "client_failure"])
def test_assessment_skips_bad_evidence_and_computes_lexical_fallback_once(
    monkeypatch, semantic_mode, caplog,
):
    intent = fallback_intent("im craving something spicy")
    places = [
        candidate("mixed", "Mixed", malformed_evidence() + [
            evidence("mixed:good", "Spicy noodles"),
            evidence("mixed:semantic", "Hot & Sour Soup"),
        ]),
        candidate("invalid", "Invalid", malformed_evidence()),
    ]
    monkeypatch.setattr(evidence_ranker, "get_settings", lambda: SimpleNamespace(
        OPENAI_API_KEY="" if semantic_mode == "disabled" else "test-openai",
        CHAT_RANKING_TIMEOUT_SECONDS=10,
        MODEL_NAME="test-model",
    ))
    lexical_calls = 0
    payloads = []
    original_lexical = evidence_ranker._lexical_assessments

    def count_lexical(*args):
        nonlocal lexical_calls
        lexical_calls += 1
        return original_lexical(*args)

    async def fake_parse(**kwargs):
        payloads.append(json.loads(kwargs["messages"][1]["content"]))
        if semantic_mode == "failure":
            raise RuntimeError("Provider unavailable")
        batch = AssessmentBatch(candidates=[
            assessment("mixed",
                       ("mixed:semantic", ["c1"], "supports"),
                       ("bad:quality", ["c1"], "supports")),
            assessment("invalid", ("bad:quality", ["c1"], "supports")),
        ])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=batch))])

    def fake_client(**_kwargs):
        if semantic_mode == "client_failure":
            raise RuntimeError("Client unavailable")
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=fake_parse)))

    monkeypatch.setattr(evidence_ranker, "_lexical_assessments", count_lexical)
    monkeypatch.setattr(evidence_ranker, "AsyncOpenAI", fake_client)
    assessments = asyncio.run(evidence_ranker.assess_candidate_evidence(intent, places))
    by_id = {item.place_id: item for item in assessments}

    assert lexical_calls == 1
    expected_ids = {"mixed:good"}
    if semantic_mode == "success":
        expected_ids.add("mixed:semantic")
    assert {item.evidence_id for item in by_id["mixed"].links} == expected_ids
    assert by_id["invalid"].links == []
    if semantic_mode in {"success", "failure"}:
        assert len(payloads) == 1
        assert [item["id"] for item in payloads[0]["candidates"][0]["evidence"]] == [
            "mixed:good", "mixed:semantic",
        ]
        assert payloads[0]["candidates"][1]["evidence"] == []
    else:
        assert payloads == []
    assert ("outcome=lexical_fallback" in caplog.text) == (semantic_mode in {"failure", "client_failure"})
    result = rank_evidence_candidates(intent, places, assessments)
    assert [item["place_id"] for item in result["recommendations"]] == ["mixed"]
    assert "outcome=skipped" in caplog.text


@pytest.mark.parametrize("raw_evidence", [malformed_evidence(), {"id": "bad"}, "bad", 42])
def test_scoring_discards_invalid_evidence_without_losing_other_candidates(raw_evidence):
    intent = fallback_intent("im craving something spicy")
    places = [
        candidate("invalid", "Invalid", raw_evidence),
        candidate("good", "Good", [evidence("good:e1", "Spicy noodles")]),
    ]
    result = rank_evidence_candidates(intent, places, [
        assessment("invalid", ("bad:quality", ["c1"], "supports")),
        assessment("good", ("good:e1", ["c1"], "supports")),
    ])
    assert [item["place_id"] for item in result["recommendations"]] == ["good"]


@pytest.mark.parametrize("has_valid_evidence", [True, False])
def test_spicy_pipeline_survives_malformed_retrieved_and_menu_evidence(monkeypatch, has_valid_evidence):
    async def fake_intent(query):
        return fallback_intent(query)

    async def fake_retrieve(*_args):
        valid = [evidence("mixed:good", "Spicy noodles")] if has_valid_evidence else []
        return [candidate("mixed", "Mixed", malformed_evidence() + valid)]

    async def fake_enrich(places, _intent):
        # Raw retrieval evidence must be safe before menu enrichment uses it.
        assert all(item["id"] == "mixed:good" for item in places[0]["evidence"])
        places[0]["evidence"].extend(malformed_evidence())
        return places

    monkeypatch.setattr(rag_pipeline, "extract_craving_intent", fake_intent)
    monkeypatch.setattr(rag_pipeline, "retrieve_candidate_restaurants", fake_retrieve)
    monkeypatch.setattr(rag_pipeline, "enrich_candidates_with_menu_evidence", fake_enrich)
    monkeypatch.setattr(evidence_ranker, "get_settings", lambda: SimpleNamespace(OPENAI_API_KEY=""))
    result = asyncio.run(rag_pipeline.generate_recommendations(
        "im craving something spicy", {"lat": 43.5, "lng": -79.7},
    ))

    assert result["intent"]["constraints"][0]["value"] == "spicy"
    assert result["intent"]["constraints"][0]["strength"] == "strong"
    assert "the evidence search failed" not in result["reply"]
    assert [item["place_id"] for item in result["recommendations"]] == (["mixed"] if has_valid_evidence else [])


def test_pipeline_error_logs_traceback_without_raw_exception_values(monkeypatch, caplog):
    private_message = "sensitive-provider-payload"

    async def fail_intent(_query):
        try:
            raise ValueError(private_message)
        except ValueError as cause:
            raise RuntimeError(private_message) from cause

    monkeypatch.setattr(rag_pipeline, "extract_craving_intent", fail_intent)
    monkeypatch.setattr(rag_pipeline.logger, "handlers", [caplog.handler])
    result = asyncio.run(rag_pipeline.generate_recommendations(
        "im craving something spicy", {"lat": 43.5, "lng": -79.7},
    ))
    logs = caplog.text

    assert result["recommendations"] == []
    assert "the evidence search failed" in result["reply"]
    assert "stage=intent outcome=error error_type=RuntimeError" in logs
    assert "Traceback (most recent call last)" in logs
    assert "in fail_intent" in logs
    assert "Exception details omitted." in logs
    assert "NoneType: None" not in logs
    assert "sensitive-provider-payload" not in logs
