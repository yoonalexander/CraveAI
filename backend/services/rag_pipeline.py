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

from backend.config import get_settings
from backend.services.places import search_nearby_places

logger = logging.getLogger(__name__)

settings = get_settings()

OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_CHAT_MODEL = settings.MODEL_NAME
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
GOOGLE_PLACES_API_KEY = settings.GOOGLE_API_KEY
CHROMA_PATH = settings.CHROMA_PATH
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
        api_key=OPENAI_API_KEY or None,
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
        embeddings = OpenAIEmbeddings(
            model=OPENAI_EMBEDDING_MODEL,
            api_key=OPENAI_API_KEY or None,
        )
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
        return _placeholder_places(cuisines, location)

    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        logger.warning("Location payload missing 'lat'/'lng'; cannot query Places API.")
        return []

    return await search_nearby_places(
        cuisines,
        lat=lat,
        lng=lng,
        radius=location.get("radius"),
    )


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
            "Here are a few places that seem to fit - let me know what you think!"
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
                "lat": item.get("lat"),
                "lng": item.get("lng"),
            }
        )
    return cleaned



