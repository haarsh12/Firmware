"""Thread-to-async bridge for real-time Cloud Speech recognition.

Cloud Speech streaming is a blocking gRPC iterator. The FastAPI WebSocket stays
asynchronous, so this module runs the gRPC iterator in a single background
thread and relays interim/final transcript events safely to the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from google.cloud import speech

from app.google_cloud import GoogleCloudService


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SpeechStreamEvent:
    kind: Literal["partial", "final", "error", "completed"]
    text: str = ""
    stability: float = 0.0
    detail: str = ""


class StreamingSpeechSession:
    """One STT stream for one ESP32 voice turn."""

    def __init__(self, cloud: GoogleCloudService, loop: asyncio.AbstractEventLoop, session_id: str) -> None:
        self._cloud = cloud
        self._loop = loop
        self.session_id = session_id
        self._audio: queue.Queue[bytes | None] = queue.Queue(maxsize=240)
        self._events: asyncio.Queue[SpeechStreamEvent] = asyncio.Queue()
        self._thread: threading.Thread | None = None
        self._input_closed = False
        self._finished = threading.Event()
        self._started_at = perf_counter()
        self.received_bytes = 0
        self.received_frames = 0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Speech stream has already started.")
        self._thread = threading.Thread(
            target=self._run,
            name=f"cloud-speech-{self.session_id}",
            daemon=True,
        )
        self._thread.start()

    def push_audio(self, pcm_audio: bytes) -> bool:
        """Queue one real-time PCM frame without blocking the WebSocket loop."""

        if self._input_closed or not pcm_audio:
            return False
        # Cloud Speech accepts frames no larger than 25 KB. The firmware sends
        # 3.2 KB / 100 ms, well inside the service limit.
        if len(pcm_audio) > 25_000:
            self._emit(SpeechStreamEvent("error", detail="Audio frame exceeds the 25 KB Cloud Speech limit."))
            self.close_input()
            return False
        try:
            self._audio.put_nowait(pcm_audio)
        except queue.Full:
            self._emit(SpeechStreamEvent("error", detail="Speech stream fell behind incoming audio."))
            self.close_input()
            return False
        self.received_bytes += len(pcm_audio)
        self.received_frames += 1
        return True

    def close_input(self) -> None:
        """Half-close the gRPC input so Cloud Speech can return the final result."""

        if not self._input_closed:
            self._input_closed = True
            self._audio.put(None)

    async def next_event(self) -> SpeechStreamEvent:
        return await self._events.get()

    @property
    def is_finished(self) -> bool:
        return self._finished.is_set()

    @property
    def elapsed_seconds(self) -> float:
        return perf_counter() - self._started_at

    def _requests(self):
        while True:
            audio = self._audio.get()
            if audio is None:
                return
            yield speech.StreamingRecognizeRequest(audio_content=audio)

    def _emit(self, event: SpeechStreamEvent) -> None:
        self._loop.call_soon_threadsafe(self._events.put_nowait, event)

    def _run(self) -> None:
        final_segments: list[str] = []
        latest_interim = ""
        try:
            responses = self._cloud.speech_client.streaming_recognize(
                config=self._cloud.streaming_recognition_config(),
                requests=self._requests(),
            )
            for response in responses:
                for result in response.results:
                    if not result.alternatives:
                        continue
                    transcript = result.alternatives[0].transcript.strip()
                    if not transcript:
                        continue
                    if result.is_final:
                        if not final_segments or final_segments[-1] != transcript:
                            final_segments.append(transcript)
                            self._emit(SpeechStreamEvent("final", text=transcript))
                    elif transcript != latest_interim:
                        latest_interim = transcript
                        self._emit(
                            SpeechStreamEvent(
                                "partial",
                                text=transcript,
                                stability=float(result.stability or 0.0),
                            )
                        )
        except Exception as exc:
            LOGGER.exception("[%s] Cloud Speech streaming failed", self.session_id)
            self._emit(SpeechStreamEvent("error", detail=f"{type(exc).__name__}: {exc}"))
        finally:
            transcript = " ".join(final_segments).strip() or latest_interim
            self._finished.set()
            self._emit(SpeechStreamEvent("completed", text=transcript))
