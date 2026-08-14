from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Sequence

from backend.config import get_settings
from backend.services.craving_intent import extract_craving_intent, fallback_intent
from backend.services.evidence_ranker import (
    assess_candidate_evidence,
    rank_evidence_candidates,
)
from backend.services.menu_evidence import enrich_candidates_with_menu_evidence
from backend.services.restaurant_retrieval import retrieve_candidate_restaurants

logger = logging.getLogger(__name__)
if not logger.handlers:
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(_log_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

settings = get_settings()
PIPELINE_TIMEOUT_SECONDS = settings.CHAT_PIPELINE_TIMEOUT_SECONDS


async def generate_recommendations(
    user_query: str,
    location: dict[str, Any],
    candidate_places: Sequence[dict[str, Any]] | None = None,
    on_stage: Callable[[str, str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Run the evidence-grounded, dish-oriented recommendation pipeline."""
    total_started = time.perf_counter()
    stage = "intent"
    candidate_count = 0
    try:
        async with asyncio.timeout(PIPELINE_TIMEOUT_SECONDS):
            started = time.perf_counter()
            await _emit_stage(on_stage, "understanding", "Understanding your craving")
            intent = await extract_craving_intent(user_query)
            _log_stage("intent", started, constraints=len(intent.constraints))

            stage = "retrieval"
            started = time.perf_counter()
            await _emit_stage(on_stage, "retrieval", "Searching restaurants in the confirmed area")
            candidates = await retrieve_candidate_restaurants(
                intent,
                location,
                candidate_places or (),
            )
            candidate_count = len(candidates)
            _log_stage("retrieval", started, candidates=candidate_count)
            if not candidates:
                return _empty_response(intent.model_dump(), "no evidence-backed candidates")

            stage = "menu_evidence"
            started = time.perf_counter()
            await _emit_stage(on_stage, "evidence", "Checking attributable menu evidence")
            candidates = await enrich_candidates_with_menu_evidence(candidates, intent)
            menu_evidence_count = sum(
                evidence.get("kind") in {"official_menu", "official_website"}
                for candidate in candidates
                for evidence in candidate.get("evidence") or []
            )
            _log_stage(
                "menu_evidence",
                started,
                candidates=candidate_count,
                evidence=menu_evidence_count,
            )

            stage = "assessment"
            started = time.perf_counter()
            await _emit_stage(on_stage, "assessment", "Comparing evidence with your constraints")
            assessments = await assess_candidate_evidence(intent, candidates)
            _log_stage("assessment", started, candidates=len(assessments))

            stage = "scoring"
            started = time.perf_counter()
            await _emit_stage(on_stage, "ranking", "Ranking the verified nearby matches")
            result = rank_evidence_candidates(intent, candidates, assessments)
            _log_stage(
                "scoring",
                started,
                candidates=len(result.get("recommendations") or []),
            )
            return result
    except TimeoutError:
        logger.warning(
            "recommendation_pipeline stage=%s outcome=timeout candidates=%d",
            stage,
            candidate_count,
        )
        intent = fallback_intent(user_query)
        return _empty_response(intent.model_dump(), "the search timed out")
    except Exception as exc:
        logger.error(
            "recommendation_pipeline stage=%s outcome=error error_type=%s",
            stage,
            type(exc).__name__,
        )
        intent = fallback_intent(user_query)
        return _empty_response(intent.model_dump(), "the evidence search failed")
    finally:
        logger.info(
            "recommendation_pipeline stage=total duration_ms=%.1f candidates=%d",
            (time.perf_counter() - total_started) * 1000,
            candidate_count,
        )


async def _emit_stage(
    callback: Callable[[str, str], Awaitable[None]] | None,
    stage: str,
    message: str,
) -> None:
    if callback is not None:
        await callback(stage, message)


def extract_search_terms(user_query: str) -> list[str]:
    """Backward-compatible local helper used by diagnostics and older clients."""
    return [item.text for item in fallback_intent(user_query).search_queries]


def _empty_response(intent: dict[str, Any], outcome: str) -> dict[str, Any]:
    return {
        "reply": (
            "I couldn't verify a strong nearby match from the available menu evidence "
            f"because {outcome}. Try widening the search area or relaxing one preference."
        ),
        "recommendations": [],
        "intent": intent,
    }


def _log_stage(
    stage: str,
    started: float,
    *,
    candidates: int = 0,
    constraints: int = 0,
    evidence: int = 0,
) -> None:
    logger.info(
        (
            "recommendation_pipeline stage=%s duration_ms=%.1f "
            "candidates=%d constraints=%d evidence=%d"
        ),
        stage,
        (time.perf_counter() - started) * 1000,
        candidates,
        constraints,
        evidence,
    )


def _normalize_query(user_query: str) -> str:
    """Retained for compatibility with existing diagnostics."""
    normalized = re.sub(r"[^\w\s-]", " ", user_query.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()
