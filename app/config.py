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
    voice_max_audio_seconds: int = Field(default=60, ge=8, le=240)
    speech_language: str = "hi-IN"
    speech_alternative_languages: str = "en-IN"
    speech_model: str = "latest_long"
    voice_debug_every_frames: int = Field(default=20, ge=1, le=200)

    enable_cloud_tts: bool = True
    tts_language: str = "hi-IN"
    tts_voice_name: str = ""
    tts_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    tts_timeout_seconds: float = Field(default=25.0, ge=5.0, le=90.0)

    # Xiaozhi is optional. It is a separate MCP control surface and never
    # replaces the Google/Vertex voice endpoint above.
    xiaozhi_mcp_enabled: bool = True
    xiaozhi_mcp_shared_secret: str = ""
    xiaozhi_mcp_allow_unauthenticated: bool = False
    xiaozhi_cloud_mcp_url: str = ""
    xiaozhi_mcp_reconnect_max_seconds: int = Field(default=30, ge=2, le=300)

    esp32_http_base_url: str = ""
    max_assistant_words: int = Field(default=45, ge=3, le=100)
    assistant_max_output_tokens: int = Field(default=512, ge=128, le=1024)

    # Local college/project knowledge base. Web pages are ingested explicitly;
    # normal voice queries only read the local ChromaDB vector database.
    knowledge_base_enabled: bool = True
    knowledge_base_directory: str = "data/chroma"
    knowledge_base_collection: str = "svpcet_assistant"
    knowledge_base_embedding_model: str = "gemini-embedding-001"
    knowledge_base_embedding_dimensions: int = Field(default=768, ge=128, le=3072)
    knowledge_base_results: int = Field(default=4, ge=1, le=8)
    knowledge_base_max_context_chars: int = Field(default=5000, ge=500, le=12000)

    # Desktop media control. It opens the locally configured default browser;
    # this feature is deliberately disabled outside the trusted local machine.
    desktop_media_enabled: bool = True
    youtube_search_timeout_seconds: float = Field(default=8.0, ge=3.0, le=30.0)

    # LiveKit powers the Flutter voice conversation only. It is separate from
    # the ESP32 WebSocket voice flow and Xiaozhi MCP bridge.
    livekit_enabled: bool = False
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "svpcet-home-agent"
    livekit_token_ttl_minutes: int = Field(default=15, ge=5, le=60)
    livekit_local_backend_url: str = "http://127.0.0.1:8000"

    @property
    def livekit_configured(self) -> bool:
        return self.livekit_enabled and bool(
            self.livekit_url.strip() and self.livekit_api_key.strip() and self.livekit_api_secret.strip()
        )

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

    @property
    def knowledge_base_path(self) -> Path:
        path = Path(self.knowledge_base_directory).expanduser()
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
