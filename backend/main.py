import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import chat, feedback, favorites
from backend.config import get_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory for the CraveAI backend service."""
    settings = get_settings()
    settings.validate()
    logger.info("Launching CraveAI backend in %s environment.", settings.ENVIRONMENT)

    app = FastAPI(
        title="CraveAI Backend",
        version="0.1.0",
        description="API surface for the CraveAI conversational recommender.",
    )

    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router)
    app.include_router(feedback.router)
    app.include_router(favorites.router)

    return app


app = create_app()
