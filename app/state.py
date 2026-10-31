"""Concurrency-safe in-memory state for a single smart-home installation."""

from __future__ import annotations

import asyncio
from copy import deepcopy

from app.schemas import SensorData


class SmartHomeState:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sensors = SensorData()
        self._relays: dict[str, bool] = {"light": False, "fan": False}

    async def set_sensors(self, sensors: SensorData) -> None:
        async with self._lock:
            self._sensors = sensors

    async def sensors(self) -> dict[str, int | float]:
        async with self._lock:
            return self._sensors.legacy_dict()

    async def set_relay(self, device: str, state: bool) -> None:
        if device not in self._relays:
            raise ValueError(f"Unknown relay: {device}")
        async with self._lock:
            self._relays[device] = state

    async def update_relays(self, values: dict[str, bool]) -> None:
        async with self._lock:
            for device in self._relays:
                if device in values:
                    self._relays[device] = bool(values[device])

    async def relays(self) -> dict[str, bool]:
        async with self._lock:
            return deepcopy(self._relays)

    async def snapshot(self) -> dict[str, object]:
        async with self._lock:
            return {"sensors": self._sensors.legacy_dict(), "relays": deepcopy(self._relays)}
