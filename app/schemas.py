"""API schemas shared by the phone app, relay board, and voice board."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SensorData(BaseModel):
    """Latest environmental readings sent by the relay/sensor ESP32."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    mq_analog: int = Field(default=0, alias="mqAnalog")
    mq_digital: int = Field(default=0, alias="mqDigital")
    ldr: int = 0
    temperature: float = 0.0
    humidity: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def map_legacy_sensor_keys(cls, value: object) -> object:
        """Accept field names sent by all of the prior relay sketches."""

        if not isinstance(value, dict):
            return value
        mapped = dict(value)
        aliases = {
            "mqAnalog": ("mq_analog", "gas_analog"),
            "mqDigital": ("mq_digital", "gas_digital"),
            "ldr": ("light_level",),
            "temperature": ("temp",),
            "humidity": ("hum",),
        }
        for target, sources in aliases.items():
            if target not in mapped:
                for source in sources:
                    if source in mapped:
                        mapped[target] = mapped[source]
                        break
        return mapped

    def legacy_dict(self) -> dict[str, int | float]:
        return {
            "mqAnalog": self.mq_analog,
            "mqDigital": self.mq_digital,
            "ldr": self.ldr,
            "temperature": self.temperature,
            "humidity": self.humidity,
        }


class RelayCommand(BaseModel):
    device: Literal["light", "fan"]
    state: bool


class DeviceAction(BaseModel):
    device: Literal["light", "fan"]
    action: Literal["on", "off"]
