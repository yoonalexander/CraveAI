from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["operations"])

StartupEventName = Literal[
    "first_api_response",
    "auth_me",
    "preferences",
    "geolocation",
    "maps_ready",
    "first_map_render",
]
StartupOutcome = Literal["success", "timeout", "error", "denied", "fallback"]

SLOW_THRESHOLDS_MS: dict[str, int] = {
    "first_api_response": 3_000,
    "auth_me": 3_000,
    "preferences": 3_000,
    "geolocation": 10_000,
    "maps_ready": 5_000,
    "first_map_render": 6_000,
}


class StartupEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StartupEventName
    duration_ms: int = Field(ge=0, le=300_000)
    outcome: StartupOutcome


class StartupReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[StartupEvent] = Field(min_length=1, max_length=8)


@router.post("/startup", status_code=status.HTTP_204_NO_CONTENT)
async def record_startup_report(payload: StartupReport) -> Response:
    for event in payload.events:
        log = (
            logger.warning
            if event.outcome in {"timeout", "error"}
            or event.duration_ms >= SLOW_THRESHOLDS_MS[event.name]
            else logger.info
        )
        log(
            "startup_timing event=%s duration_ms=%d outcome=%s",
            event.name,
            event.duration_ms,
            event.outcome,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
