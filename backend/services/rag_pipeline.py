from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

try:
    from langchain_community.vectorstores import Chroma
except ImportError:  # pragma: no cover - optional dependency during scaffolding
    Chroma = None  # type: ignore

logger = logging.getLogger(__name__)

# TODO: Wire these configuration values through a dedicated settings module.
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_API_KEY", "")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma_db")
DEFAULT_SEARCH_RADIUS_METERS = int(os.getenv("GOOGLE_SEARCH_RADIUS", "5000"))
MAX_CUISINES = 5
MAX_PLACES_PER_CUISINE = 5

INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an intent parser for a food recommendation assistant. "
                "Extract core craving details and respond with compact JSON following this schema:\n"
                '{"mood": ["<mood>"], "cravings": ["<craving>"], "diet": ["<restriction>"]}. '
                "Use empty arrays if a field is not present. Keep the response valid JSON with double quotes."
            ),
        ),
        (
            "human",
            "User query: {user_query}\n"
            "Return only the JSON object.",
        ),
    ]
)

RANKING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a culinary recommendation expert. Given the user craving and candidate restaurants, "
                "select the three best matches, craft a conversational summary, and output JSON with:\n"
                '{"reply": "<assistant summary>", "recommendations": ['
                '{"name": "...", "rating": <float or null>, "address": "...", "reason": "..."}'
                "]}. Keep the tone warm and concise."
            ),
        ),
        (
            "human",
            "User craving: {user_query}\n"
            "Candidates (JSON):\n"
            "{candidates}\n"
            "Respond with the specified JSON schema only.",
        ),
    ]
)

_json_parser = StrOutputParser()


async def generate_recommendations(user_query: str, location: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orchestrate the RAG pipeline for restaurant recommendations.

    Args:
        user_query: Natural language craving, mood, and dietary request.
        location: Dictionary containing at least 'lat' and 'lng' values.

    Returns:
        Dict containing a reply string and ranked recommendations.
    """
    llm = _build_chat_model()
    intent = await _parse_intent(llm, user_query)
    cuisines = await _retrieve_similar_cuisines(intent)
    places = await _fetch_candidate_places(cuisines, location)
    ranking = await _rank_candidates(llm, user_query, places)
    return ranking


def _build_chat_model() -> ChatOpenAI:
    """Instantiate the OpenAI chat model used across the pipeline."""
    # TODO: Configure API key management via environment or secret manager.
    return ChatOpenAI(
        model=OPENAI_CHAT_MODEL,
        temperature=0.2,
        max_tokens=500,
    )


async def _parse_intent(llm: ChatOpenAI, user_query: str) -> Dict[str, List[str]]:
    """Call the LLM to extract structured intent from the user's craving."""
    chain = INTENT_PROMPT | llm | _json_parser
    try:
        raw_response = await chain.ainvoke({"user_query": user_query})
        parsed = json.loads(raw_response)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Intent parsing failed (%s); falling back to heuristic extraction.", exc)
        parsed = _heuristic_intent(user_query)
    return {
        "mood": _normalize_list(parsed.get("mood")),
        "cravings": _normalize_list(parsed.get("cravings")),
        "diet": _normalize_list(parsed.get("diet")),
    }


def _normalize_list(value: Optional[Iterable[str]]) -> List[str]:
    """Ensure the field is a list of unique lowercase strings."""
    if not value:
        return []
    seen: set[str] = set()
    normalized: List[str] = []
    for item in value:
        if not item:
            continue
        token = str(item).strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered not in seen:
            seen.add(lowered)
            normalized.append(lowered)
    return normalized


def _heuristic_intent(user_query: str) -> Dict[str, List[str]]:
    """Lightweight fallback intent extraction using keyword matching."""
    tokens = user_query.lower().split()
    moods = [word for word in tokens if word in {"spicy", "cozy", "light", "hearty", "romantic"}]
    diets = [word for word in tokens if word in {"vegan", "vegetarian", "keto", "halal", "gluten-free"}]
    cravings = [word for word in tokens if word.endswith(("ian", "ese", "ish", "an")) or word in {"ramen", "pho", "tacos"}]
    return {"mood": moods, "cravings": cravings, "diet": diets}


async def _retrieve_similar_cuisines(intent: Dict[str, List[str]]) -> List[str]:
    """Use the cuisine embedding store to surface related cuisines."""
    query_terms = intent.get("cravings") or intent.get("mood") or []
    if not query_terms:
        return []

    if Chroma is None:
        logger.info("Chroma is not installed; returning intent terms as fallback cuisines.")
        return query_terms[:MAX_CUISINES]

    try:
        embeddings = OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
        vector_store = await asyncio.to_thread(
            Chroma,
            persist_directory=CHROMA_PATH,
            embedding_function=embeddings,
        )
        combined_query = " ".join(query_terms)
        docs = await asyncio.to_thread(
            vector_store.similarity_search,
            combined_query,
            MAX_CUISINES,
        )
        cuisines: List[str] = []
        for doc in docs:
            cuisine = doc.metadata.get("cuisine") if isinstance(doc.metadata, dict) else None
            cuisine = cuisine or doc.page_content
            if cuisine and cuisine not in cuisines:
                cuisines.append(cuisine)
        if not cuisines:
            cuisines = query_terms[:MAX_CUISINES]
        return cuisines[:MAX_CUISINES]
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Cuisine retrieval failed (%s); using intent terms instead.", exc)
        return query_terms[:MAX_CUISINES]


async def _fetch_candidate_places(
    cuisines: Sequence[str], location: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Query the Google Places API for each cuisine candidate."""
    if not cuisines:
        logger.info("No cuisines identified; skipping Places API lookup.")
        return []

    if not GOOGLE_PLACES_API_KEY:
        logger.info("Google Places API key not configured; returning placeholder venues.")
        return _placeholder_places(cuisines)

    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        logger.warning("Location payload missing 'lat'/'lng'; cannot query Places API.")
        return []

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        tasks = [
            _query_places_api(client, cuisine, lat=lat, lng=lng, radius=location.get("radius"))
            for cuisine in cuisines
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    merged: Dict[str, Dict[str, Any]] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Error during Places API lookup: %s", result)
            continue
        for place in result:
            place_id = place.get("place_id") or f"{place['name']}::{place.get('address')}"
            if place_id not in merged:
                merged[place_id] = place
    return list(merged.values())


async def _query_places_api(
    client: httpx.AsyncClient,
    cuisine: str,
    *,
    lat: float,
    lng: float,
    radius: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch nearby restaurants for a single cuisine keyword."""
    params = {
        "key": GOOGLE_PLACES_API_KEY,
        "location": f"{lat},{lng}",
        "radius": radius or DEFAULT_SEARCH_RADIUS_METERS,
        "type": "restaurant",
        "keyword": cuisine,
    }
    response = await client.get(
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
        params=params,
    )
    response.raise_for_status()
    payload = response.json()
    candidates: List[Dict[str, Any]] = []
    for item in payload.get("results", [])[:MAX_PLACES_PER_CUISINE]:
        candidates.append(
            {
                "name": item.get("name"),
                "rating": item.get("rating"),
                "address": item.get("vicinity"),
                "reason": f"Matches cuisine query '{cuisine}'",
                "place_id": item.get("place_id"),
            }
        )
    return candidates


async def _rank_candidates(
    llm: ChatOpenAI, user_query: str, places: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """Use GPT to rank results and craft the assistant-facing summary."""
    if not places:
        reply = (
            "I'm still training my taste buds and couldn't find matching spots yet. "
            "Try refining your craving or share a location to explore together!"
        )
        return {"reply": reply, "recommendations": []}

    candidates_json = json.dumps(list(places), ensure_ascii=False)
    chain = RANKING_PROMPT | llm | _json_parser
    try:
        raw = await chain.ainvoke(
            {
                "user_query": user_query,
                "candidates": candidates_json,
            }
        )
        parsed = json.loads(raw)
        parsed["recommendations"] = _sanitize_recommendations(parsed.get("recommendations", []))
        parsed["reply"] = parsed.get("reply") or (
            "Here are a few places that seem to fit—let me know what you think!"
        )
        return parsed
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Ranking prompt failed (%s); returning top candidates as-is.", exc)
        return {
            "reply": (
                "Here are some nearby spots that match what you're craving. "
                "I'll refine the reasoning once the ranking model is ready."
            ),
            "recommendations": _sanitize_recommendations(places[:3]),
        }


def _sanitize_recommendations(raw_items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize recommendation entries to the expected output schema."""
    cleaned: List[Dict[str, Any]] = []
    for item in raw_items:
        cleaned.append(
            {
                "name": item.get("name"),
                "rating": item.get("rating"),
                "address": item.get("address"),
                "reason": item.get("reason") or "",
            }
        )
    return cleaned


def _placeholder_places(cuisines: Sequence[str]) -> List[Dict[str, Any]]:
    """Fallback data used when the external API is not reachable."""
    placeholders: List[Dict[str, Any]] = []
    for cuisine in cuisines[:3]:
        placeholders.append(
            {
                "name": f"Placeholder {cuisine.title()} Spot",
                "rating": 4.5,
                "address": f"{cuisine.title()} District, Sample City",
                "reason": f"Sample recommendation for {cuisine}",
            }
        )
    return placeholders

