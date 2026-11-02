"""
FastAPI application entry point.

Run locally:   uv run uvicorn app.main:app --reload
Run in Docker: see apps/api/Dockerfile

`app` is the object uvicorn serves. Settings are loaded once here, so a
missing or invalid secret stops the server at startup instead of failing
on the first request.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import getSettings
from app.routers import analyze


def createApp() -> FastAPI:
    """Build the app. A factory function makes it easy to create fresh apps in tests."""
    settings = getSettings()

    # Interactive docs are handy in development but expose the full API
    # surface, so they are turned off in production.
    isProduction = settings.appEnv == "production"

    newApp = FastAPI(
        title="Rental Scam Detector API",
        version="0.1.0",
        docs_url=None if isProduction else "/docs",
        redoc_url=None,
        openapi_url=None if isProduction else "/openapi.json",
    )

    # CORS: browsers block web pages from calling an API on another
    # domain unless the API allows it. Only our own frontend origins are
    # allowed, and only the methods and headers we actually use.
    newApp.add_middleware(
        CORSMiddleware,
        allow_origins=settings.corsAllowedOrigins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=False,
    )

    @newApp.get("/health", tags=["system"])
    def checkHealth() -> dict[str, str]:
        """Used by Cloud Run and uptime checks to confirm the server is alive."""
        return {"status": "ok"}

    newApp.include_router(analyze.router)
    return newApp


app = createApp()
