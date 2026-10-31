"""Minimal WebSocket endpoint for testing a MAX98357A speaker board."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["speaker-test"])


async def _send_audio(websocket: WebSocket, pcm_audio: bytes) -> None:
    await websocket.send_text("AUDIO_START")
    await websocket.send_text(str(len(pcm_audio)))
    for offset in range(0, len(pcm_audio), 512):
        await websocket.send_bytes(pcm_audio[offset : offset + 512])
        await asyncio.sleep(0.002)
    await websocket.send_text("AUDIO_END")


@router.websocket("/ws/speaker-test")
async def speaker_test_websocket(websocket: WebSocket) -> None:
    """Synthesize a short requested phrase without requiring a microphone."""

    await websocket.accept()
    await websocket.send_text("STATUS:Connected. Send SPEAK:<text>")
    try:
        while True:
            message = await websocket.receive_text()
            if message == "PING":
                await websocket.send_text("PONG")
                continue
            if not message.startswith("SPEAK:"):
                await websocket.send_text("ERROR:Send text as SPEAK:Hello world")
                continue
            text = " ".join(message.removeprefix("SPEAK:").split())[:180]
            if not text:
                await websocket.send_text("ERROR:Speech text is empty")
                continue
            LOGGER.info("Speaker test requested: %s", text)
            await websocket.send_text("STATUS:Generating Cloud TTS")
            try:
                started = perf_counter()
                pcm_audio = await asyncio.wait_for(
                    asyncio.to_thread(websocket.app.state.google_cloud.synthesize_pcm, text),
                    timeout=websocket.app.state.settings.tts_timeout_seconds,
                )
                if not pcm_audio:
                    raise RuntimeError("Cloud TTS is disabled. Set ENABLE_CLOUD_TTS=true.")
                LOGGER.info("Speaker test TTS generated %s PCM bytes in %.2fs", len(pcm_audio), perf_counter() - started)
                await _send_audio(websocket, pcm_audio)
            except Exception:
                LOGGER.exception("Speaker-test TTS failed")
                await websocket.send_text("ERROR:TTS generation failed; see backend terminal")
    except WebSocketDisconnect:
        LOGGER.info("Speaker-test ESP32 disconnected")
