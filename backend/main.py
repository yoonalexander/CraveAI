from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.routers import account, auth, chat, feedback, favorites, places
from backend.services.storage import init_storage

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate()
    if settings.AUTO_CREATE_SCHEMA:
        init_storage()

    app = FastAPI(
        title="CraveAI Backend",
        version="1.0.0",
        description="Secure API for the CraveAI conversational recommender.",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-CraveAI-Anonymous-Token",
            "Retry-After",
            "X-Request-ID",
        ],
        max_age=600,
    )

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):
        request_id = request.headers.get("x-request-id", "")[:64] or str(uuid.uuid4())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > settings.REQUEST_BODY_LIMIT_BYTES
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": {"code": "request_body_too_large"}},
                    headers={"X-Request-ID": request_id},
                )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body = await request.body()
            if len(body) > settings.REQUEST_BODY_LIMIT_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": {"code": "request_body_too_large"}},
                    headers={"X-Request-ID": request_id},
                )

        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        logger.info(
            "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%d",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            int((time.monotonic() - started) * 1000),
        )
        return response

    api_routers = (auth.router, account.router, chat.router, places.router, favorites.router, feedback.router)
    for router in api_routers:
        app.include_router(router, prefix="/api")

    # Temporary compatibility aliases for the pre-account public demo. They use
    # the exact same quota and security dependencies as the canonical routes.
    app.include_router(chat.router)
    app.include_router(places.router)

    return app


app = create_app()
