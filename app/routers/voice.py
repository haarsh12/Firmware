"""Low-latency INMP441 voice WebSocket endpoint."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.assistant import build_prompt, fallback_assistant_reply, limit_reply
from app.command_parser import parse_relay_commands
from app.relay_manager import RelayManager, RelayUnavailableError
from app.state import SmartHomeState
from app.streaming_stt import SpeechStreamEvent, StreamingSpeechSession


LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])


async def _send_text(websocket: WebSocket, text: str, send_lock: asyncio.Lock) -> bool:
    """Serialize outgoing frames because STT and socket receive run concurrently."""

    try:
        async with send_lock:
            await websocket.send_text(text)
        return True
    except Exception:
        return False


async def _send_audio(websocket: WebSocket, pcm_audio: bytes, send_lock: asyncio.Lock) -> bool:
    """Send an optional TTS response as the existing raw-PCM wire protocol."""

    if not pcm_audio:
        return True
    if not await _send_text(websocket, "AUDIO_START", send_lock):
        return False
    if not await _send_text(websocket, str(len(pcm_audio)), send_lock):
        return False
    for offset in range(0, len(pcm_audio), 512):
        try:
            async with send_lock:
                await websocket.send_bytes(pcm_audio[offset : offset + 512])
        except Exception:
            return False
        await asyncio.sleep(0.002)
    await _send_text(websocket, "AUDIO_END", send_lock)
    return True


async def _finish_voice_turn(websocket: WebSocket, send_lock: asyncio.Lock) -> None:
    """Tell the firmware the conversation turn has fully completed."""

    await _send_text(websocket, "VOICE_DONE", send_lock)


async def _answer_final_transcript(
    websocket: WebSocket,
    transcript: str,
    session_id: str,
    stt_seconds: float,
    send_lock: asyncio.Lock,
    conversation_history: list[tuple[str, str]],
) -> None:
    """Run the LLM only after Cloud Speech produces a final turn transcript."""

    app_state = websocket.app.state
    settings = app_state.settings
    home_state: SmartHomeState = app_state.home_state
    cloud = app_state.google_cloud
    manager: RelayManager = app_state.relay_manager

    transcript = " ".join(transcript.split())
    if not transcript:
        LOGGER.warning("[%s] Speech stream ended without a transcript", session_id)
        await _send_text(websocket, "STATUS:No clear speech was detected", send_lock)
        await _send_text(websocket, "LCD:Mujhe awaaz samajh nahi aayi. Phir se boliye.", send_lock)
        await _finish_voice_turn(websocket, send_lock)
        return

    LOGGER.info("[%s] final transcript after %.2fs: %s", session_id, stt_seconds, transcript)
    await _send_text(websocket, f"TRANSCRIPT:{transcript}", send_lock)
    await _send_text(websocket, "STATUS:Thinking", send_lock)

    commands = parse_relay_commands(transcript)
    snapshot = await home_state.snapshot()
    sensors = snapshot["sensors"]
    relays = snapshot["relays"]
    assert isinstance(sensors, dict) and isinstance(relays, dict)

    generation_started = perf_counter()
    try:
        model_reply = await asyncio.to_thread(
            cloud.generate_assistant_reply,
            build_prompt(transcript, sensors, relays, commands, conversation_history),
        )
        reply = model_reply.display_text
        speech_reply = model_reply.speech_text
        LOGGER.info("[%s] Vertex reply completed in %.2fs", session_id, perf_counter() - generation_started)
    except Exception:
        LOGGER.exception("[%s] Vertex AI generation failed; using local response", session_id)
        model_reply = fallback_assistant_reply(commands)
        reply = model_reply.display_text
        speech_reply = model_reply.speech_text

    relay_errors: list[str] = []
    for command in commands:
        try:
            await manager.dispatch(command.device, command.state)
            LOGGER.info("[%s] relay command dispatched: %s=%s", session_id, command.device, command.state)
        except RelayUnavailableError:
            relay_errors.append(command.device)

    if relay_errors:
        reply = f"{', '.join(relay_errors)} relay board connected nahi hai."
        speech_reply = reply
    reply = limit_reply(reply, settings.max_assistant_words)
    conversation_history.append((transcript, reply))
    del conversation_history[:-6]

    await _send_text(websocket, f"REPLY:{reply}", send_lock)
    if not await _send_text(websocket, f"LCD:{reply}", send_lock):
        return

    # Keep ENABLE_CLOUD_TTS=true for the MAX98357A speaker firmware. A
    # microphone-only board may set it false to skip this cloud request.
    if settings.enable_cloud_tts:
        await _send_text(websocket, "STATUS:Generating audio reply", send_lock)
        try:
            LOGGER.info("[%s] Cloud TTS generating %s characters", session_id, len(speech_reply))
            pcm_reply = await asyncio.wait_for(
                asyncio.to_thread(cloud.synthesize_pcm, speech_reply),
                timeout=settings.tts_timeout_seconds,
            )
            LOGGER.info(
                "[%s] Cloud TTS generated %s PCM bytes in %.2fs",
                session_id,
                len(pcm_reply),
                perf_counter() - generation_started,
            )
            sent = await _send_audio(websocket, pcm_reply, send_lock)
            LOGGER.info("[%s] TTS audio sent=%s bytes=%s", session_id, sent, len(pcm_reply))
        except Exception:
            LOGGER.exception("[%s] Cloud TTS failed; the text reply was delivered", session_id)

    await _finish_voice_turn(websocket, send_lock)


async def _consume_speech_events(
    websocket: WebSocket,
    session: StreamingSpeechSession,
    send_lock: asyncio.Lock,
    conversation_history: list[tuple[str, str]],
) -> None:
    """Relay real-time STT events to the ESP32 and terminal."""

    while True:
        event: SpeechStreamEvent = await session.next_event()
        if event.kind == "partial":
            LOGGER.info(
                "[%s] partial (stability %.2f): %s",
                session.session_id,
                event.stability,
                event.text,
            )
            await _send_text(websocket, f"PARTIAL:{event.text}", send_lock)
        elif event.kind == "final":
            LOGGER.info("[%s] final segment: %s", session.session_id, event.text)
            await _send_text(websocket, f"FINAL:{event.text}", send_lock)
        elif event.kind == "error":
            LOGGER.error("[%s] streaming STT error: %s", session.session_id, event.detail)
            await _send_text(websocket, f"ERROR:Speech stream error: {event.detail}", send_lock)
        elif event.kind == "completed":
            await _answer_final_transcript(
                websocket,
                event.text,
                session.session_id,
                session.elapsed_seconds,
                send_lock,
                conversation_history,
            )
            return


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    """Receive a real-time 16-bit PCM stream from one INMP441 ESP32.

    ``START`` opens a Cloud Speech gRPC stream, binary frames flow immediately
    to it, and ``STOP`` half-closes it. Interim hypotheses are emitted as
    ``PARTIAL:`` while the user is still speaking.
    """

    await websocket.accept()
    settings = websocket.app.state.settings
    send_lock = asyncio.Lock()
    recording = False
    session: StreamingSpeechSession | None = None
    event_task: asyncio.Task[None] | None = None
    conversation_history: list[tuple[str, str]] = []
    LOGGER.info("Voice ESP32 connected from %s", websocket.client)

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            if text is not None:
                if text == "START":
                    if session is not None and session.is_finished:
                        session = None
                        event_task = None
                    if session is not None:
                        LOGGER.warning("Ignoring START while voice turn %s is active", session.session_id)
                        await _send_text(websocket, "STATUS:Finish the current voice turn first", send_lock)
                        continue
                    session_id = uuid4().hex[:8]
                    session = StreamingSpeechSession(websocket.app.state.google_cloud, asyncio.get_running_loop(), session_id)
                    session.start()
                    event_task = asyncio.create_task(
                        _consume_speech_events(websocket, session, send_lock, conversation_history)
                    )
                    recording = True
                    LOGGER.info("[%s] streaming voice turn started", session_id)
                    await _send_text(websocket, "STATUS:Streaming microphone to Cloud Speech", send_lock)
                    await _send_text(websocket, "LCD:Listening...", send_lock)
                elif text == "STOP" and recording and session is not None:
                    recording = False
                    session.close_input()
                    LOGGER.info(
                        "[%s] voice input closed: frames=%s bytes=%s duration=%.2fs",
                        session.session_id,
                        session.received_frames,
                        session.received_bytes,
                        session.elapsed_seconds,
                    )
                    await _send_text(websocket, "STATUS:Finalizing transcript", send_lock)
                    await _send_text(websocket, "LCD:Processing...", send_lock)
                elif text == "PING":
                    await _send_text(websocket, "PONG", send_lock)
                else:
                    LOGGER.debug("Ignoring voice text frame: %r", text[:120])
                continue

            data = message.get("bytes")
            if data is not None and recording and session is not None:
                if session.received_bytes + len(data) > settings.max_audio_bytes:
                    recording = False
                    session.close_input()
                    LOGGER.warning("[%s] voice turn reached configured audio limit", session.session_id)
                    await _send_text(websocket, "STATUS:Maximum voice length reached", send_lock)
                    await _send_text(websocket, "LCD:Voice message bahut lamba hai", send_lock)
                elif not session.push_audio(data):
                    recording = False
                    await _send_text(websocket, "STATUS:Audio stream is unavailable", send_lock)
                elif session.received_frames % settings.voice_debug_every_frames == 0:
                    LOGGER.info(
                        "[%s] streamed audio: frames=%s bytes=%s duration=%.2fs",
                        session.session_id,
                        session.received_frames,
                        session.received_bytes,
                        session.elapsed_seconds,
                    )
                    await _send_text(
                        websocket,
                        f"DEBUG:sent {session.received_frames} audio frames ({session.received_bytes} bytes)",
                        send_lock,
                    )
    except WebSocketDisconnect:
        pass
    finally:
        recording = False
        if session is not None:
            session.close_input()
        if event_task is not None:
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        LOGGER.info("Voice ESP32 disconnected")
