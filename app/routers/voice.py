"""INMP441 voice WebSocket endpoint."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.assistant import build_prompt, fallback_reply, limit_reply
from app.command_parser import parse_relay_commands
from app.google_cloud import GoogleCloudService
from app.relay_manager import RelayManager, RelayUnavailableError
from app.state import SmartHomeState


LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])


async def _send_text(websocket: WebSocket, text: str) -> bool:
    try:
        await websocket.send_text(text)
        return True
    except Exception:
        return False


async def _send_audio(websocket: WebSocket, pcm_audio: bytes) -> bool:
    if not pcm_audio:
        return True
    if not await _send_text(websocket, "AUDIO_START"):
        return False
    if not await _send_text(websocket, str(len(pcm_audio))):
        return False
    for offset in range(0, len(pcm_audio), 512):
        try:
            await websocket.send_bytes(pcm_audio[offset : offset + 512])
        except Exception:
            return False
        await asyncio.sleep(0.002)
    return True


async def _finish_voice_turn(websocket: WebSocket) -> None:
    """Tell the ESP32 it may accept another button press.

    This marker follows the optional binary TTS frames, so the same protocol
    works for microphone-only boards and boards with an I2S speaker.
    """

    await _send_text(websocket, "VOICE_DONE")


async def _process_voice_turn(websocket: WebSocket, pcm_audio: bytes) -> None:
    app_state = websocket.app.state
    settings = app_state.settings
    home_state: SmartHomeState = app_state.home_state
    cloud: GoogleCloudService = app_state.google_cloud
    manager: RelayManager = app_state.relay_manager

    if len(pcm_audio) < settings.voice_sample_rate // 4:
        await _send_text(websocket, "LCD:Audio bahut chhota hai")
        await _finish_voice_turn(websocket)
        return

    try:
        transcript = await asyncio.to_thread(cloud.transcribe_pcm, pcm_audio)
    except Exception:
        LOGGER.exception("Google Cloud Speech transcription failed")
        await _send_text(websocket, "LCD:Speech service abhi available nahi hai")
        await _finish_voice_turn(websocket)
        return
    if not transcript:
        await _send_text(websocket, "LCD:Samajh nahi aaya, phir se boliye")
        await _finish_voice_turn(websocket)
        return

    commands = parse_relay_commands(transcript)
    snapshot = await home_state.snapshot()
    sensors = snapshot["sensors"]
    relays = snapshot["relays"]
    assert isinstance(sensors, dict) and isinstance(relays, dict)

    try:
        reply = await asyncio.to_thread(
            cloud.generate_assistant_reply,
            build_prompt(transcript, sensors, relays, commands),
        )
    except Exception:
        LOGGER.exception("Vertex AI generation failed; using local response")
        reply = fallback_reply(commands)

    relay_errors: list[str] = []
    for command in commands:
        try:
            await manager.dispatch(command.device, command.state)
        except RelayUnavailableError:
            relay_errors.append(command.device)

    if relay_errors:
        reply = f"{', '.join(relay_errors)} relay board connected nahi hai."
    reply = limit_reply(reply, settings.max_assistant_words)

    await _send_text(websocket, f"TRANSCRIPT:{transcript}")
    if not await _send_text(websocket, f"LCD:{reply}"):
        return

    if settings.enable_cloud_tts:
        try:
            pcm_reply = await asyncio.to_thread(cloud.synthesize_pcm, reply)
            await _send_audio(websocket, pcm_reply)
        except Exception:
            LOGGER.exception("Google Cloud TTS failed; text response was still delivered")

    await _finish_voice_turn(websocket)


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    """Receive START/raw PCM/STOP frames from the INMP441 voice ESP32."""

    await websocket.accept()
    settings = websocket.app.state.settings
    recording = False
    audio_buffer = bytearray()

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            if text is not None:
                if text == "START":
                    recording = True
                    audio_buffer.clear()
                    await _send_text(websocket, "LCD:Listening...")
                elif text == "STOP" and recording:
                    recording = False
                    await _send_text(websocket, "LCD:Processing...")
                    await _process_voice_turn(websocket, bytes(audio_buffer))
                    audio_buffer.clear()
                elif text == "PING":
                    await _send_text(websocket, "PONG")
                continue

            data = message.get("bytes")
            if data is not None and recording:
                if len(audio_buffer) + len(data) > settings.max_audio_bytes:
                    recording = False
                    audio_buffer.clear()
                    await _send_text(websocket, "LCD:Recording bahut lambi hai")
                    await _finish_voice_turn(websocket)
                else:
                    audio_buffer.extend(data)
    except WebSocketDisconnect:
        pass
    finally:
        LOGGER.info("Voice ESP32 disconnected")
