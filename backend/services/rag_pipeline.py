from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Sequence

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from backend.config import get_settings
from backend.services.places import _placeholder_places, search_nearby_places

logger = logging.getLogger(__name__)

settings = get_settings()

OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_CHAT_MODEL = settings.MODEL_NAME
GOOGLE_PLACES_API_KEY = settings.GOOGLE_API_KEY
PIPELINE_TIMEOUT_SECONDS = settings.CHAT_PIPELINE_TIMEOUT_SECONDS
RANKING_TIMEOUT_SECONDS = settings.CHAT_RANKING_TIMEOUT_SECONDS
MAX_SEARCH_TERMS = 3
MAX_RECOMMENDATIONS = 3

CUISINE_ALIASES = {
    "pizza": ("pizza", "pizzeria"),
    "ramen": ("ramen",),
    "indian": ("indian", "curry"),
    "italian": ("italian", "pasta", "trattoria", "ristorante"),
    "chinese": ("chinese", "dim sum"),
    "japanese": ("japanese", "izakaya"),
    "korean": ("korean",),
    "thai": ("thai",),
    "vietnamese": ("vietnamese", "pho"),
    "mexican": ("mexican", "taco", "tacos", "taqueria", "burrito"),
    "greek": ("greek",),
    "mediterranean": ("mediterranean",),
    "middle eastern": ("middle eastern", "shawarma", "kebab"),
    "sushi": ("sushi",),
    "seafood": ("seafood", "fish"),
    "barbecue": ("barbecue", "bbq"),
    "burgers": ("burger", "burgers"),
    "cafe": ("cafe", "coffee"),
    "bakery": ("bakery", "pastry", "pastries"),
}

DIET_ALIASES = {
    "vegan": ("vegan",),
    "vegetarian": ("vegetarian", "meatless"),
    "halal": ("halal",),
    "kosher": ("kosher",),
    "gluten-free": ("gluten-free", "gluten free"),
    "keto": ("keto", "low carb", "low-carb"),
}

RANKING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Rank the supplied restaurants for the user's craving. Select at most "
                "three candidates and return compact JSON with this exact shape: "
                '{{"reply": "<brief friendly summary>", "recommendations": ['
                '{{"name": "...", "reason": "<specific short reason>"}}]}}. '
                "Only select restaurants present in the candidate list."
            ),
        ),
        (
            "human",
            "User craving: {user_query}\nCandidates:\n{candidates}\nReturn JSON only.",
        ),
    ]
)

_json_parser = StrOutputParser()


async def generate_recommendations(
    user_query: str,
    location: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the bounded hybrid recommendation pipeline."""
    total_started = time.perf_counter()
    places: List[Dict[str, Any]] = []
    outcome = "success"

    try:
        async with asyncio.timeout(PIPELINE_TIMEOUT_SECONDS):
            extraction_started = time.perf_counter()
            search_terms = extract_search_terms(user_query)
            _log_stage(
                "extract",
                extraction_started,
                outcome="success",
                search_terms=len(search_terms),
            )

            places_started = time.perf_counter()
            try:
                places = await _fetch_candidate_places(search_terms, location)
                _log_stage(
                    "places",
                    places_started,
                    outcome="success",
                    candidates=len(places),
                )
            except Exception as exc:
                outcome = "places_error"
                logger.warning("chat_pipeline stage=places outcome=error error=%r", exc)
                _log_stage("places", places_started, outcome="error", candidates=0)
                return _deterministic_response([], reason=outcome)

            if not places:
                outcome = "no_candidates"
                return _deterministic_response([], reason=outcome)

            ranking_started = time.perf_counter()
            try:
                async with asyncio.timeout(RANKING_TIMEOUT_SECONDS):
                    result = await _rank_candidates(user_query, places)
                _log_stage(
                    "ranking",
                    ranking_started,
                    outcome="success",
                    candidates=len(places),
                )
                return result
            except TimeoutError:
                outcome = "ranking_timeout"
                _log_stage(
                    "ranking",
                    ranking_started,
                    outcome="timeout",
                    candidates=len(places),
                )
                return _deterministic_response(places, reason=outcome)
            except Exception as exc:
                outcome = "ranking_error"
                logger.warning("chat_pipeline stage=ranking outcome=error error=%r", exc)
                _log_stage(
                    "ranking",
                    ranking_started,
                    outcome="error",
                    candidates=len(places),
                )
                return _deterministic_response(places, reason=outcome)
    except TimeoutError:
        outcome = "pipeline_timeout"
        return _deterministic_response(places, reason=outcome)
    finally:
        _log_stage(
            "total",
            total_started,
            outcome=outcome,
            candidates=len(places),
        )


def extract_search_terms(user_query: str) -> List[str]:
    """Extract up to three useful Google Places keyword searches locally."""
    normalized = _normalize_query(user_query)
    cuisines = _match_aliases(normalized, CUISINE_ALIASES)
    diets = _match_aliases(normalized, DIET_ALIASES)

    if cuisines:
        diet_prefix = diets[0] if diets else ""
        return [
            " ".join(part for part in (diet_prefix, cuisine) if part)
            for cuisine in cuisines[:MAX_SEARCH_TERMS]
        ]

    fallback = normalized[:80].strip()
    if fallback:
        return [fallback]
    return ["restaurants"]


def _normalize_query(user_query: str) -> str:
    normalized = re.sub(r"[^\w\s-]", " ", user_query.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _match_aliases(
    normalized_query: str,
    aliases_by_label: Dict[str, Sequence[str]],
) -> List[str]:
    matches: List[str] = []
    for label, aliases in aliases_by_label.items():
        if any(
            re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_query)
            for alias in aliases
        ):
            matches.append(label)
    return matches


def _build_chat_model() -> ChatOpenAI:
    """Build the single bounded model client used for final ranking."""
    return ChatOpenAI(
        model=OPENAI_CHAT_MODEL,
        max_completion_tokens=500,
        reasoning_effort="minimal",
        verbosity="low",
        model_kwargs={"response_format": {"type": "json_object"}},
        timeout=RANKING_TIMEOUT_SECONDS,
        max_retries=0,
        api_key=OPENAI_API_KEY or None,
    )


async def _fetch_candidate_places(
    search_terms: Sequence[str],
    location: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Query Google Places for the locally extracted search terms."""
    if not search_terms:
        return []

    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        logger.warning("chat_pipeline stage=places outcome=missing_location")
        return []

    if not GOOGLE_PLACES_API_KEY:
        logger.info("chat_pipeline stage=places outcome=placeholder")
        return _placeholder_places(list(search_terms), lat, lng)

    return await search_nearby_places(
        list(search_terms),
        lat=lat,
        lng=lng,
        radius=location.get("radius"),
    )


async def _rank_candidates(
    user_query: str,
    places: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Use one model call to rank candidates and write the short response."""
    candidates_json = json.dumps(list(places), ensure_ascii=False)
    chain = RANKING_PROMPT | _build_chat_model() | _json_parser
    raw = await chain.ainvoke(
        {
            "user_query": user_query,
            "candidates": candidates_json,
        }
    )
    parsed = json.loads(raw)
    raw_recommendations = parsed.get("recommendations")
    if not isinstance(raw_recommendations, list):
        raise ValueError("Ranking response did not include a recommendations list.")

    recommendations = _merge_ranked_recommendations(raw_recommendations, places)
    if not recommendations:
        raise ValueError("Ranking response did not select known candidates.")

    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        reply = "Here are the nearby spots that best match what you're craving."
    return {
        "reply": reply.strip(),
        "recommendations": recommendations,
    }


def _merge_ranked_recommendations(
    ranked_items: Sequence[Dict[str, Any]],
    source_places: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sources_by_name = {
        str(place.get("name", "")).strip().casefold(): place
        for place in source_places
        if place.get("name")
    }
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for ranked in ranked_items:
        name_key = str(ranked.get("name", "")).strip().casefold()
        source = sources_by_name.get(name_key)
        if not source or name_key in seen:
            continue
        seen.add(name_key)
        combined = dict(source)
        if ranked.get("reason"):
            combined["reason"] = ranked["reason"]
        merged.append(_sanitize_recommendation(combined))
        if len(merged) >= MAX_RECOMMENDATIONS:
            break
    return merged


def _deterministic_response(
    places: Sequence[Dict[str, Any]],
    *,
    reason: str,
) -> Dict[str, Any]:
    if not places:
        return {
            "reply": (
                "I couldn't find matching nearby restaurants in time. "
                "Try a more specific cuisine or search again in a moment."
            ),
            "recommendations": [],
        }

    ranked = sorted(
        places,
        key=lambda place: (
            _number(place.get("rating")),
            _number(place.get("user_ratings_total")),
        ),
        reverse=True,
    )
    logger.info(
        "chat_pipeline stage=fallback outcome=%s candidates=%d",
        reason,
        len(places),
    )
    return {
        "reply": (
            "Here are the strongest nearby matches I found. "
            "I ranked them using their ratings and review counts."
        ),
        "recommendations": [
            _sanitize_recommendation(place)
            for place in ranked[:MAX_RECOMMENDATIONS]
        ],
    }


def _sanitize_recommendation(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": item.get("name"),
        "rating": item.get("rating"),
        "address": item.get("address"),
        "reason": item.get("reason") or "",
        "lat": item.get("lat"),
        "lng": item.get("lng"),
    }


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _log_stage(
    stage: str,
    started: float,
    *,
    outcome: str,
    candidates: int = 0,
    search_terms: int = 0,
) -> None:
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        (
            "chat_pipeline stage=%s duration_ms=%.1f outcome=%s "
            "candidates=%d search_terms=%d"
        ),
        stage,
        duration_ms,
        outcome,
        candidates,
        search_terms,
    )
