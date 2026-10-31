"""FastAPI entry point for the Google Cloud-authenticated smart-home backend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.google_cloud import GoogleCloudService
from app.relay_manager import RelayManager
from app.routers import sensors, speaker_test, voice
from app.state import SmartHomeState


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


_configure_logging()
LOGGER = logging.getLogger(__name__)
settings = get_settings()
home_state = SmartHomeState()
google_cloud = GoogleCloudService(settings)
relay_manager = RelayManager(settings, home_state)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configured, detail = google_cloud.validate_configuration()
    app.state.google_cloud_configured = configured
    app.state.google_cloud_detail = detail
    if configured:
        LOGGER.info("Google Cloud service-account credentials are configured for Vertex AI project %s.", google_cloud.project_id)
    else:
        LOGGER.warning("Google Cloud services are unavailable: %s", detail)
    yield


app = FastAPI(
    title="Smart Home Vertex AI Backend",
    version="2.0.0",
    description="ESP32 smart-home API using service-account credentials for Vertex AI and Google Cloud speech services.",
    lifespan=lifespan,
)
app.state.settings = settings
app.state.home_state = home_state
app.state.google_cloud = google_cloud
app.state.relay_manager = relay_manager
app.state.google_cloud_configured = False
app.state.google_cloud_detail = "Startup validation has not run."

origins = settings.allowed_origins
if settings.is_production and (not origins or "*" in origins):
    raise RuntimeError("CORS_ORIGINS must list explicit HTTPS origins in production.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-Id"],
)

app.include_router(sensors.router)
app.include_router(voice.router)
app.include_router(speaker_test.router)


@app.get("/", tags=["health"])
async def root() -> dict[str, object]:
    return {
        "status": "online",
        "service": "Smart Home Vertex AI Backend",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "sensors": "/api/sensor/data",
            "relay_control": "/api/device/control",
            "voice_ws": "/ws/voice",
            "relay_ws": "/ws/relay",
        },
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "backend": "online",
        "google_cloud_configured": app.state.google_cloud_configured,
        "google_cloud_detail": app.state.google_cloud_detail,
        "relay_board_connections": await relay_manager.connection_count(),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=not settings.is_production)
