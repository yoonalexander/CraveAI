from fastapi import FastAPI

from backend.routers import chat, feedback, favorites


def create_app() -> FastAPI:
    """Application factory for the CraveAI backend service."""
    app = FastAPI(
        title="CraveAI Backend",
        version="0.1.0",
        description="API surface for the CraveAI conversational recommender.",
    )

    app.include_router(chat.router)
    app.include_router(feedback.router)
    app.include_router(favorites.router)

    return app


app = create_app()

