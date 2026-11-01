"""Local phone-app API for explicit desktop YouTube actions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.media import DesktopMediaService, MediaUnavailableError
from app.schemas import MediaPlayRequest

router = APIRouter(prefix="/media", tags=["desktop-media"])


@router.post("/youtube/play")
async def play_youtube(body: MediaPlayRequest, request: Request) -> dict[str, object]:
    try:
        launch = await asyncio.to_thread(request.app.state.desktop_media.play, body.query)
    except MediaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "opened", "query": launch.query, "direct_video": launch.direct_video}


@router.post("/youtube/open")
async def open_youtube(request: Request) -> dict[str, str]:
    try:
        await asyncio.to_thread(request.app.state.desktop_media.open_youtube)
    except MediaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "opened"}
