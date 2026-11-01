"""Streaming Hindi LiveKit home-automation assistant.

It deliberately calls the existing FastAPI backend for relay state, YouTube,
and ChromaDB. Xiaozhi and ESP32 voice services remain untouched.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from google.genai.types import HttpOptions
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, function_tool
from livekit.plugins import google

from app.config import get_settings
from app.google_cloud import GoogleCloudService

LOGGER = logging.getLogger("livekit_mobile.agent")
server = AgentServer()


def _instructions() -> str:
    return """You are Ghar Sathi, the SVPCET E&TC Home Automation Assistant.
Speak naturally in Hindi or simple Hinglish. Keep answers brief, warm, and useful.
For light or fan actions, always call the corresponding tool before saying it worked.
For temperature, humidity, gas, relay connection, or current device state, call get_home_status.
For SVPCET, E&TC, faculty, director, principal, labs, or project questions, call search_college_knowledge first and use only its verified results.
For an explicit request to play a song/video on the laptop, use play_youtube. Do not claim success if a tool reports an error.
"""


class MobileHomeAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=_instructions())

    @property
    def _base_url(self) -> str:
        return get_settings().livekit_local_backend_url.rstrip("/")

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(f"{self._base_url}{path}", json=payload)
            data = response.json()
            if response.is_error:
                raise RuntimeError(str(data.get("detail", f"Backend returned {response.status_code}")))
            return data

    @function_tool()
    async def set_light(self, state: bool) -> dict[str, Any]:
        """Turn relay 1 light on (true) or off (false)."""
        try:
            return await self._post("/app/relay", {"device": "light", "state": state})
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @function_tool()
    async def set_fan(self, state: bool) -> dict[str, Any]:
        """Turn relay 2 fan on (true) or off (false)."""
        try:
            return await self._post("/app/relay", {"device": "fan", "state": state})
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @function_tool()
    async def get_home_status(self) -> dict[str, Any]:
        """Read relay connection, light/fan state, temperature, humidity, gas, and light sensor."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                health, sensors = await asyncio.gather(
                    client.get(f"{self._base_url}/health"), client.get(f"{self._base_url}/app/sensors")
                )
            return {"health": health.json(), "home": sensors.json()}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @function_tool()
    async def search_college_knowledge(self, query: str) -> dict[str, Any]:
        """Search the backend ChromaDB for verified SVPCET, E&TC, faculty, lab, or project information."""
        try:
            async with httpx.AsyncClient(timeout=18.0) as client:
                response = await client.get(f"{self._base_url}/knowledge/search", params={"query": query})
            return response.json()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @function_tool()
    async def play_youtube(self, query: str) -> dict[str, Any]:
        """Open and play an explicitly requested song or video in YouTube on the backend laptop."""
        try:
            return await self._post("/media/youtube/play", {"query": query})
        except Exception as exc:
            return {"ok": False, "message": str(exc)}


def _providers() -> tuple[google.STT, google.LLM, google.TTS]:
    settings = get_settings()
    cloud = GoogleCloudService(settings)
    configured, detail = cloud.validate_configuration()
    if not configured:
        raise RuntimeError(detail)
    credentials_file = str(settings.google_credentials_path)
    stt = google.STT(
        languages=["hi-IN"], model=settings.speech_model, location="global",
        detect_language=False, punctuate=True, credentials_file=credentials_file,
    )
    llm = google.LLM(
        model=settings.vertex_gemini_model, vertexai=True, project=cloud.project_id,
        location=settings.vertex_ai_location, credentials=cloud.credentials,
        temperature=0.3, http_options=HttpOptions(api_version="v1"),
    )
    tts = google.TTS(
        language="hi-IN", voice_name=settings.tts_voice_name or "hi-IN-Chirp3-HD-Kore",
        model_name="chirp_3", credentials_file=credentials_file, use_streaming=True,
    )
    return stt, llm, tts


@server.rtc_session(agent_name=get_settings().livekit_agent_name)
async def mobile_voice_agent(ctx: JobContext) -> None:
    settings = get_settings()
    if not settings.livekit_configured:
        raise RuntimeError("LiveKit is not configured in .env")
    participant = await ctx.wait_for_participant()
    LOGGER.info("Mobile voice participant joined: %s", participant.identity)
    stt, llm, tts = _providers()
    session = AgentSession(stt=stt, llm=llm, tts=tts)
    await session.start(agent=MobileHomeAgent(), room=ctx.room)
    await session.generate_reply(instructions="नमस्ते, मैं घर साथी हूँ। बताइए, मैं आपकी क्या मदद कर सकता हूँ?")


if __name__ == "__main__":
    cli.run_app(server)
