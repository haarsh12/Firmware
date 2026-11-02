"""Sensor, relay, and phone-app compatibility endpoints."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from app.relay_manager import RelayManager, RelayUnavailableError
from app.schemas import DeviceAction, RelayCommand, SensorData
from app.state import SmartHomeState


LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["sensors-and-relays"])


def _state(request: Request) -> SmartHomeState:
    return request.app.state.home_state


def _manager(request: Request) -> RelayManager:
    return request.app.state.relay_manager


async def _dispatch(manager: RelayManager, device: str, relay_state: bool) -> dict[str, object]:
    try:
        await manager.dispatch(device, relay_state)
    except RelayUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"status": "ok", "device": device, "state": relay_state}


@router.post("/sensors/data")
@router.post("/api/sensors/update")
async def push_sensor_data(data: SensorData, request: Request) -> dict[str, str]:
    """Accept sensor readings from either current or legacy ESP32 firmware."""

    await _state(request).set_sensors(data)
    await _manager(request).note_http_heartbeat()
    LOGGER.info(
        "Relay ESP32 sensor update: temperature=%.1fC humidity=%.1f%% mq_analog=%s mq_digital=%s ldr=%s",
        data.temperature,
        data.humidity,
        data.mq_analog,
        data.mq_digital,
        data.ldr,
    )
    return {"status": "ok"}


@router.get("/relay/next")
async def poll_relay_command(request: Request) -> dict[str, object]:
    """HTTP command fallback for boards that cannot retain `/ws/relay`."""

    manager = _manager(request)
    await manager.note_http_heartbeat()
    command = await manager.next_http_command()
    return command or {"type": "no_command"}


@router.get("/sensors/latest")
async def latest_sensors(request: Request) -> dict[str, int | float]:
    return await _state(request).sensors()


@router.post("/relay/set")
async def set_relay(command: RelayCommand, request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), command.device, command.state)


@router.get("/light/on")
async def light_on(request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), "light", True)


@router.get("/light/off")
async def light_off(request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), "light", False)


@router.get("/fan/on")
async def fan_on(request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), "fan", True)


@router.get("/fan/off")
async def fan_off(request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), "fan", False)


@router.get("/api/sensor/data")
async def phone_sensor_data(request: Request) -> dict[str, int | float | bool]:
    snapshot = await _state(request).snapshot()
    sensors = snapshot["sensors"]
    relays = snapshot["relays"]
    assert isinstance(sensors, dict) and isinstance(relays, dict)
    return {**sensors, "light": relays["light"], "fan": relays["fan"]}


@router.post("/api/device/control")
async def phone_device_control(action: DeviceAction, request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), action.device, action.action == "on")


@router.get("/api/device/status")
async def device_status(request: Request) -> dict[str, bool | int]:
    relays = await _state(request).relays()
    return {**relays, "wifi_connected": await _manager(request).board_connected()}


@router.post("/api/device/status")
async def relay_board_status(payload: dict[str, bool], request: Request) -> dict[str, str]:
    """Compatibility endpoint for older relay firmware status callbacks."""

    await _manager(request).apply_board_status(payload)
    return {"status": "ok"}


@router.get("/api/device/ping")
async def device_ping() -> dict[str, int | str]:
    return {"status": "ok", "latency_ms": 0}


@router.get("/app/sensors")
async def app_sensors(request: Request) -> dict[str, object]:
    return await _state(request).snapshot()


@router.post("/app/relay")
async def app_relay(command: RelayCommand, request: Request) -> dict[str, object]:
    return await _dispatch(_manager(request), command.device, command.state)


@router.get("/app/status")
async def app_status(request: Request) -> dict[str, object]:
    return {
        "status": "online",
        "relay_board_connected": await _manager(request).board_connected(),
    }


@router.websocket("/ws/relay")
async def relay_websocket(websocket: WebSocket) -> None:
    """Persistent relay-board channel.

    The board accepts ``relay_command`` messages and returns ``relay_status``
    whenever a physical touch switch changes a relay.
    """

    manager: RelayManager = websocket.app.state.relay_manager
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "relay_status", **(await websocket.app.state.home_state.relays())})
        while True:
            message = await websocket.receive_text()
            if message == "PING":
                await websocket.send_text("PONG")
                continue
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                LOGGER.warning("Ignoring non-JSON relay-board message")
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("type") in {"relay_status", "status"}:
                await manager.apply_board_status(payload)
                LOGGER.info(
                    "Relay ESP32 status received: light=%s fan=%s",
                    payload.get("light"),
                    payload.get("fan"),
                )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
