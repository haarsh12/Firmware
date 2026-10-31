"""Configuration for the smart-home backend.

Secrets never live in source control.  Google client libraries are given a
service-account JSON path from ``GOOGLE_APPLICATION_CREDENTIALS`` instead of a
Gemini API key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Typed environment settings loaded from the backend-local ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "*"

    google_application_credentials: str = ""
    google_cloud_project: str = ""
    vertex_ai_location: str = "global"
    vertex_gemini_model: str = "gemini-2.5-flash"

    voice_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    voice_sample_width: int = Field(default=2, ge=2, le=4)
    voice_max_audio_seconds: int = Field(default=25, ge=1, le=240)
    speech_language: str = "hi-IN"
    speech_alternative_languages: str = "en-IN"
    speech_model: str = "latest_long"
    voice_debug_every_frames: int = Field(default=20, ge=1, le=200)

    enable_cloud_tts: bool = True
    tts_language: str = "hi-IN"
    tts_voice_name: str = ""
    tts_sample_rate: int = Field(default=16000, ge=8000, le=48000)

    esp32_http_base_url: str = ""
    max_assistant_words: int = Field(default=45, ge=3, le=100)
    assistant_max_output_tokens: int = Field(default=256, ge=32, le=1024)

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def speech_alternatives(self) -> list[str]:
        return [language.strip() for language in self.speech_alternative_languages.split(",") if language.strip()]

    @property
    def google_credentials_path(self) -> Path:
        """Resolve a configured credential filename relative to this backend."""

        path = Path(self.google_application_credentials).expanduser()
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @property
    def max_audio_bytes(self) -> int:
        """Maximum mono PCM payload accepted from the ESP32 in one voice turn."""

        return self.voice_sample_rate * self.voice_sample_width * self.voice_max_audio_seconds


@lru_cache
def get_settings() -> Settings:
    return Settings()
