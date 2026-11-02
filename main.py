"""FastAPI entry point for the Google Cloud-authenticated smart-home backend."""

from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.google_cloud import GoogleCloudService
from app.relay_manager import RelayManager
from app.routers import knowledge, livekit_mobile, media, sensors, speaker_test, voice
from app.media import DesktopMediaService
from app.state import SmartHomeState
from app.knowledge_base import CollegeKnowledgeBase
from xiaozhi_connect.mcp_server import router as xiaozhi_mcp_router
from xiaozhi_connect.outbound_bridge import XiaozhiOutboundBridge


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
knowledge_base = CollegeKnowledgeBase(settings, google_cloud)
desktop_media = DesktopMediaService(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configured, detail = google_cloud.validate_configuration()
    app.state.google_cloud_configured = configured
    app.state.google_cloud_detail = detail
    if configured:
        LOGGER.info("Google Cloud service-account credentials are configured for Vertex AI project %s.", google_cloud.project_id)
    else:
        LOGGER.warning("Google Cloud services are unavailable: %s", detail)
    bridge = XiaozhiOutboundBridge(app)
    app.state.xiaozhi_bridge = bridge
    bridge_task = asyncio.create_task(bridge.run(), name="xiaozhi-outbound-mcp")
    try:
        yield
    finally:
        await bridge.stop()
        bridge_task.cancel()
        try:
            await bridge_task
        except asyncio.CancelledError:
            pass


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
app.state.knowledge_base = knowledge_base
app.state.desktop_media = desktop_media
app.state.google_cloud_configured = False
app.state.google_cloud_detail = "Startup validation has not run."
app.state.xiaozhi_bridge = None

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
app.include_router(knowledge.router)
app.include_router(media.router)
app.include_router(livekit_mobile.router)
app.include_router(xiaozhi_mcp_router)


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
            "xiaozhi_mcp": "/xiaozhi/mcp",
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
        "relay_board_connected": await relay_manager.board_connected(),
        "knowledge_base": {
            "enabled": settings.knowledge_base_enabled,
            "chunks": knowledge_base.count(),
        },
        "xiaozhi_mcp_enabled": settings.xiaozhi_mcp_enabled,
        "livekit_mobile_voice": {"enabled": settings.livekit_enabled, "configured": settings.livekit_configured},
        "xiaozhi_outbound_bridge": (
            app.state.xiaozhi_bridge.status.public_dict()
            if app.state.xiaozhi_bridge is not None
            else {"configured": False, "connected": False, "last_event": "Startup pending."}
        ),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=not settings.is_production)
