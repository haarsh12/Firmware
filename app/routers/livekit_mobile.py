"""Short-lived LiveKit tokens for the trusted Flutter mobile application."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from livekit import api
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/livekit", tags=["livekit-mobile-voice"])


class MobileVoiceTokenRequest(BaseModel):
    participant_name: str = Field(default="Mobile user", min_length=1, max_length=64)


@router.post("/token")
async def issue_mobile_voice_token(body: MobileVoiceTokenRequest, request: Request) -> dict[str, str]:
    """Issue one room token; the LiveKit worker is dispatched server-side."""

    settings = request.app.state.settings
    if not settings.livekit_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit mobile voice is not configured. Set its server credentials in .env.",
        )
    identity = f"mobile-{uuid4().hex}"
    room_name = f"svpcet-mobile-{uuid4().hex[:16]}"
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(body.participant_name.strip())
        .with_ttl(timedelta(minutes=settings.livekit_token_ttl_minutes))
        .with_attributes({"language": "hi-IN", "client": "svpcet-flutter"})
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=settings.livekit_agent_name)]
            )
        )
        .to_jwt()
    )
    return {"server_url": settings.livekit_url, "participant_token": token, "room_name": room_name}
