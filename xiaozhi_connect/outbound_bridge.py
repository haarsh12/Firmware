"""Persistent outbound MCP WebSocket bridge for Xiaozhi Cloud.

Xiaozhi's portal displays a generated `wss://api.xiaozhi.me/mcp/?token=...`
address.  The local bridge connects *outward* to that address, advertises safe
tools, and receives JSON-RPC tool calls from the agent.  It is deliberately
independent of the existing Google Vertex voice workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import websockets
from fastapi import FastAPI

from xiaozhi_connect.mcp_server import _TOOLS, call_home_tool


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class XiaozhiBridgeStatus:
    configured: bool = False
    connected: bool = False
    reconnect_attempts: int = 0
    messages_received: int = 0
    tool_calls: int = 0
    last_event: str = "Not configured"

    def public_dict(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "connected": self.connected,
            "reconnect_attempts": self.reconnect_attempts,
            "messages_received": self.messages_received,
            "tool_calls": self.tool_calls,
            "last_event": self.last_event,
        }


class XiaozhiOutboundBridge:
    """Reconnectable server-side MCP implementation for one Xiaozhi agent."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self.status = XiaozhiBridgeStatus()
        self._stop = asyncio.Event()

    async def run(self) -> None:
        settings = self._app.state.settings
        endpoint = settings.xiaozhi_cloud_mcp_url.strip()
        self.status.configured = bool(endpoint) and settings.xiaozhi_mcp_enabled
        if not self.status.configured:
            self.status.last_event = "Set XIAOZHI_CLOUD_MCP_URL in .env to enable the outbound bridge."
            LOGGER.info("Xiaozhi outbound bridge is not configured.")
            return

        delay = 1
        while not self._stop.is_set():
            try:
                self.status.last_event = "Connecting to Xiaozhi Cloud"
                # Never log the endpoint: its query string is a bearer token.
                LOGGER.info("Xiaozhi MCP bridge connecting to Xiaozhi Cloud.")
                async with websockets.connect(
                    endpoint,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=1_000_000,
                ) as socket:
                    self.status.connected = True
                    self.status.reconnect_attempts = 0
                    self.status.last_event = "Connected; waiting for Xiaozhi MCP requests."
                    LOGGER.info("Xiaozhi MCP bridge CONNECTED. Portal status should become Connected.")
                    delay = 1
                    await self._serve(socket)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status.connected = False
                self.status.reconnect_attempts += 1
                self.status.last_event = f"Disconnected; retrying in {delay}s ({type(exc).__name__})."
                LOGGER.warning(
                    "Xiaozhi MCP bridge disconnected (%s); retrying in %ss.", type(exc).__name__, delay
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, settings.xiaozhi_mcp_reconnect_max_seconds)
            finally:
                self.status.connected = False

    async def stop(self) -> None:
        self._stop.set()

    async def _serve(self, socket: Any) -> None:
        async for raw_message in socket:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8", errors="replace")
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                LOGGER.warning("Xiaozhi MCP bridge ignored malformed JSON message.")
                continue
            if not isinstance(message, dict):
                continue
            self.status.messages_received += 1
            response = await self._handle_message(message)
            if response is not None:
                await socket.send(json.dumps(response, ensure_ascii=False))

    async def _handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            return None
        params = message.get("params", {})
        if method == "initialize":
            negotiated_version = "2024-11-05"
            if isinstance(params, dict) and isinstance(params.get("protocolVersion"), str):
                negotiated_version = params["protocolVersion"]
            LOGGER.info("Xiaozhi MCP initialize received.")
            return self._result(request_id, {
                "protocolVersion": negotiated_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ghar-sathi-home-automation", "version": "1.0.0"},
            })
        if method == "notifications/initialized":
            LOGGER.info("Xiaozhi MCP session initialized; tools are ready.")
            return None
        if method == "tools/list":
            LOGGER.info("Xiaozhi MCP tool discovery requested; advertising light, fan, and status only.")
            return self._result(request_id, {"tools": _TOOLS})
        if method == "tools/call":
            if not isinstance(params, dict):
                return self._error(request_id, -32602, "tools/call parameters must be an object.")
            tool_name = str(params.get("name", ""))
            self.status.tool_calls += 1
            LOGGER.info("Xiaozhi MCP tools/call received: %s", tool_name)
            result = await call_home_tool(
                self._app.state.relay_manager,
                self._app.state.home_state,
                tool_name,
                params.get("arguments", {}),
            )
            return self._result(request_id, result)
        if method == "ping":
            return self._result(request_id, {})
        if request_id is not None:
            return self._error(request_id, -32601, f"Unsupported MCP method: {method}")
        return None

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
