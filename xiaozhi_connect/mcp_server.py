"""Small authenticated MCP server for Xiaozhi smart-home tool calls."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.knowledge_base import CollegeKnowledgeBase
from app.media import DesktopMediaService, MediaUnavailableError
from app.relay_manager import RelayManager, RelayUnavailableError
from app.state import SmartHomeState


LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["xiaozhi-mcp"])
_PROTOCOL_VERSION = "2025-03-26"
_TOOLS = [
    {"name": "set_light", "description": "Turn the home light relay on or off. Relay 1 is the light.", "inputSchema": {"type": "object", "properties": {"state": {"type": "boolean", "description": "true = on; false = off"}}, "required": ["state"], "additionalProperties": False}},
    {"name": "set_fan", "description": "Turn the home fan relay on or off. Relay 2 is the fan.", "inputSchema": {"type": "object", "properties": {"state": {"type": "boolean", "description": "true = on; false = off"}}, "required": ["state"], "additionalProperties": False}},
    {"name": "get_home_status", "description": "Read light, fan, relay-board connection, DHT11 temperature/humidity, and available MQ-2 gas sensor values. Never changes a device.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_project_identity", "description": "Get the exact verified identity of this SVPCET E&TC mini project: team members, technologies, and purpose. Use for questions such as who made you, your name, which AI model you use, or what project you are.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "search_college_knowledge", "description": "Search the backend's full local ChromaDB knowledge base for verified SVPCET college, E&TC department, faculty, laboratory, project, admission, or location information. Use before answering any such question, including spoken Hindi name variations.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "The user's complete question, preserving spoken name variations."}}, "required": ["query"], "additionalProperties": False}},
    {"name": "play_youtube", "description": "On the backend laptop, open the default browser directly on the best YouTube match and request autoplay. Use only for an explicit request to play a song, music, or video.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Song or video name to play on YouTube."}}, "required": ["query"], "additionalProperties": False}},
    {"name": "open_youtube", "description": "Open YouTube on the backend laptop. Use only when the user explicitly asks to open YouTube without naming a song or video.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

_IDENTITY_TEXT = (
    "This is the SVPCET E&TC Home-Automation Voice Assistant, an Electronics and "
    "Telecommunication Department mini project at St. Vincent Pallotti College of "
    "Engineering and Technology, Nagpur. It was developed by Harsh Sathawane, Hashir "
    "Khan, Vedant Bhaganagre, and Rishika Appa. It is a custom student-built system "
    "using Google Vertex AI Gemini, Google Speech-to-Text, and Google Text-to-Speech; "
    "the team did not train a foundation model from scratch."
)


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _authorized(request: Request) -> bool:
    settings = request.app.state.settings
    if settings.xiaozhi_mcp_allow_unauthenticated:
        return True
    expected = settings.xiaozhi_mcp_shared_secret.strip()
    # Headers are preferred. Query-key support is only for MCP portals that
    # cannot configure custom headers; it must still travel over HTTPS.
    supplied = request.headers.get("X-Xiaozhi-Key", "") or request.query_params.get("key", "")
    return bool(expected) and supplied == expected


async def call_home_tool(
    manager: RelayManager,
    home_state: SmartHomeState,
    knowledge_base: CollegeKnowledgeBase,
    desktop_media: DesktopMediaService,
    name: str,
    arguments: object,
) -> dict[str, Any]:
    """Execute safe home-control and read-only knowledge tools."""

    if name == "open_youtube":
        try:
            await asyncio.to_thread(desktop_media.open_youtube)
        except MediaUnavailableError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        return {"content": [{"type": "text", "text": "YouTube has been opened on the laptop."}]}

    if name == "play_youtube":
        if not isinstance(arguments, dict) or not isinstance(arguments.get("query"), str):
            return {"content": [{"type": "text", "text": "Argument query must be a song or video name."}], "isError": True}
        try:
            launch = await asyncio.to_thread(desktop_media.play, arguments["query"])
        except MediaUnavailableError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        text = f"Opening YouTube for {launch.query} on the laptop."
        if launch.direct_video:
            text += " The matched video was opened with autoplay requested."
        return {"content": [{"type": "text", "text": text}]}

    if name == "get_project_identity":
        LOGGER.info("Xiaozhi MCP tool get_project_identity")
        return {"content": [{"type": "text", "text": _IDENTITY_TEXT}]}

    if name == "search_college_knowledge":
        if not isinstance(arguments, dict) or not isinstance(arguments.get("query"), str):
            return {"content": [{"type": "text", "text": "Argument query must be a question string."}], "isError": True}
        query = arguments["query"].strip()
        if not query:
            return {"content": [{"type": "text", "text": "Please provide a non-empty query."}], "isError": True}
        hits = await asyncio.to_thread(knowledge_base.retrieve, query)
        if not hits:
            LOGGER.warning("Xiaozhi knowledge search returned no results: %s", query)
            return {"content": [{"type": "text", "text": "No verified local knowledge-base result was found."}], "isError": True}
        evidence = "\n\n".join(
            f"Source: {hit.title}\n{hit.text[:850]}" for hit in hits[:3]
        )
        LOGGER.info("Xiaozhi knowledge search: %r -> %s result(s)", query, len(hits))
        return {"content": [{"type": "text", "text": evidence}]}

    if name == "get_home_status":
        snapshot = await home_state.snapshot()
        snapshot["relay_board_connected"] = (await manager.connection_count()) > 0
        LOGGER.info("Xiaozhi MCP tool get_home_status -> %s", snapshot)
        return {"content": [{"type": "text", "text": str(snapshot)}]}
    device = {"set_light": "light", "set_fan": "fan"}.get(name)
    if device is None:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    if not isinstance(arguments, dict) or not isinstance(arguments.get("state"), bool):
        return {"content": [{"type": "text", "text": "Argument state must be true or false."}], "isError": True}
    relay_state = arguments["state"]
    LOGGER.info("Xiaozhi MCP command received: %s -> %s", device, "ON" if relay_state else "OFF")
    try:
        await manager.dispatch(device, relay_state)
    except RelayUnavailableError as exc:
        LOGGER.warning("Xiaozhi MCP command failed: %s", exc)
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    text = f"{device.title()} relay is now {'ON' if relay_state else 'OFF'}."
    LOGGER.info("Xiaozhi MCP command completed: %s", text)
    return {"content": [{"type": "text", "text": text}]}


async def _call_tool(request: Request, name: str, arguments: object) -> dict[str, Any]:
    return await call_home_tool(
        request.app.state.relay_manager,
        request.app.state.home_state,
        request.app.state.knowledge_base,
        request.app.state.desktop_media,
        name,
        arguments,
    )


@router.post("/xiaozhi/mcp")
async def xiaozhi_mcp(request: Request) -> dict[str, Any]:
    """HTTP MCP endpoint to expose this backend's tools to Xiaozhi."""
    settings = request.app.state.settings
    if not settings.xiaozhi_mcp_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xiaozhi MCP is disabled.")
    if not _authorized(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Xiaozhi MCP key.")
    try:
        message = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected JSON-RPC JSON.") from exc
    if not isinstance(message, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a JSON-RPC object.")
    request_id, method, params = message.get("id"), message.get("method"), message.get("params", {})
    if method == "initialize":
        return _response(request_id, {"protocolVersion": _PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "new-backend-home-automation", "version": "1.0.0"}})
    if method == "notifications/initialized":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": _TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict):
            return _error(request_id, -32602, "tools/call parameters must be an object.")
        return _response(request_id, await _call_tool(request, str(params.get("name", "")), params.get("arguments", {})))
    return _error(request_id, -32601, f"Unsupported MCP method: {method}")


@router.get("/xiaozhi/mcp")
async def xiaozhi_mcp_browser_status(request: Request) -> dict[str, object]:
    """Human-friendly check; real MCP traffic must use POST JSON-RPC."""
    settings = request.app.state.settings
    if not settings.xiaozhi_mcp_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Xiaozhi MCP is disabled.")
    if not _authorized(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Xiaozhi MCP key.")
    return {
        "status": "online",
        "service": "new_backend Xiaozhi MCP bridge",
        "transport": "POST JSON-RPC",
        "tools": [tool["name"] for tool in _TOOLS],
    }
