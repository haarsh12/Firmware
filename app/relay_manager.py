"""Relay-board WebSocket connection management and HTTP compatibility fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

import httpx
from fastapi import WebSocket

from app.config import Settings
from app.state import SmartHomeState


LOGGER = logging.getLogger(__name__)


class RelayUnavailableError(RuntimeError):
    """Raised when no relay board can receive a requested command."""


class RelayManager:
    def __init__(self, settings: Settings, state: SmartHomeState) -> None:
        self._settings = settings
        self._state = state
        self._connections: list[WebSocket] = []
        self._connections_lock = asyncio.Lock()
        self._pending_http_commands: deque[dict[str, object]] = deque()
        self._pending_commands_lock = asyncio.Lock()
        self._last_http_heartbeat = 0.0

    async def note_http_heartbeat(self) -> None:
        """Record a sensor POST from the relay board.

        Some ESP32 networks permit normal HTTP while dropping a persistent
        WebSocket upgrade.  A recent heartbeat is enough to use the board's
        command-poll fallback safely.
        """

        self._last_http_heartbeat = time.monotonic()

    async def http_board_connected(self) -> bool:
        return (time.monotonic() - self._last_http_heartbeat) < 15.0

    async def board_connected(self) -> bool:
        return (await self.connection_count()) > 0 or await self.http_board_connected()

    async def next_http_command(self) -> dict[str, object] | None:
        """Return one queued command to a polling relay board, if available."""

        async with self._pending_commands_lock:
            return self._pending_http_commands.popleft() if self._pending_http_commands else None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._connections_lock:
            self._connections.append(websocket)
        LOGGER.info("Relay ESP32 connected; active connections=%s", await self.connection_count())

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._connections_lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        LOGGER.info("Relay ESP32 disconnected; active connections=%s", await self.connection_count())

    async def connection_count(self) -> int:
        async with self._connections_lock:
            return len(self._connections)

    async def apply_board_status(self, payload: dict[str, object]) -> None:
        """Use physical-board status updates to keep the app state accurate."""

        values = {
            device: bool(payload[device])
            for device in ("light", "fan")
            if device in payload
        }
        if values:
            await self._state.update_relays(values)

    async def dispatch(self, device: str, state: bool) -> None:
        """Send a command to a connected board, then persist its requested state."""

        if device not in {"light", "fan"}:
            raise ValueError(f"Unsupported relay device: {device}")

        payload = {"type": "relay_command", "device": device, "state": state}
        delivered = await self._send_to_websocket_clients(payload)
        if not delivered:
            if await self.http_board_connected():
                async with self._pending_commands_lock:
                    # Preserve command order; this project has a single board.
                    self._pending_http_commands.append(payload)
                LOGGER.info("Queued %s=%s for relay ESP32 HTTP poll fallback", device, state)
            else:
                await self._send_http_fallback(device, state)
        await self._state.set_relay(device, state)

    async def _send_to_websocket_clients(self, payload: dict[str, object]) -> bool:
        async with self._connections_lock:
            clients = list(self._connections)

        delivered = False
        failed: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(payload)
                delivered = True
            except Exception:  # WebSocket close errors differ by ASGI server.
                failed.append(client)

        for client in failed:
            await self.disconnect(client)
        return delivered

    async def _send_http_fallback(self, device: str, state: bool) -> None:
        base_url = self._settings.esp32_http_base_url.strip().rstrip("/")
        if not base_url:
            raise RelayUnavailableError("Relay board is not connected to /ws/relay.")

        state_name = "on" if state else "off"
        url = f"{base_url}/{device}/{state_name}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RelayUnavailableError(f"Relay board did not accept {device} {state_name}.") from exc
