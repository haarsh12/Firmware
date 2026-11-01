"""Google Cloud clients authenticated solely with a service-account file."""

from __future__ import annotations

import io
import json
import logging
import wave
from dataclasses import dataclass
from functools import cached_property

from google import genai
from google.cloud import speech, texttospeech
from google.genai import types
from google.oauth2 import service_account

from app.config import Settings


LOGGER = logging.getLogger(__name__)
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class GoogleCloudConfigurationError(RuntimeError):
    """Raised when service-account configuration cannot be used."""


@dataclass(frozen=True, slots=True)
class GeneratedAssistantReply:
    """Model result with Latin LCD text and natural text for Cloud TTS."""

    display_text: str
    speech_text: str


class GoogleCloudService:
    """Lazy Google Cloud client factory used by STT, Vertex AI, and TTS."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def credentials(self):
        credential_path = self.settings.google_credentials_path
        if not self.settings.google_application_credentials:
            raise GoogleCloudConfigurationError("GOOGLE_APPLICATION_CREDENTIALS is not configured.")
        if not credential_path.is_file():
            raise GoogleCloudConfigurationError(
                f"Service-account file is not readable: {credential_path}"
            )
        try:
            return service_account.Credentials.from_service_account_file(
                str(credential_path), scopes=[_CLOUD_PLATFORM_SCOPE]
            )
        except (OSError, ValueError) as exc:
            raise GoogleCloudConfigurationError("Could not load the Google service-account file.") from exc

    @property
    def project_id(self) -> str:
        project_id = self.settings.google_cloud_project.strip() or self.credentials.project_id or ""
        if not project_id:
            raise GoogleCloudConfigurationError(
                "GOOGLE_CLOUD_PROJECT is required when the credential has no project_id."
            )
        return project_id

    @cached_property
    def vertex_client(self) -> genai.Client:
        return genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.settings.vertex_ai_location,
            credentials=self.credentials,
            http_options=types.HttpOptions(api_version="v1"),
        )

    @cached_property
    def speech_client(self) -> speech.SpeechClient:
        return speech.SpeechClient(credentials=self.credentials)

    @cached_property
    def tts_client(self) -> texttospeech.TextToSpeechClient:
        return texttospeech.TextToSpeechClient(credentials=self.credentials)

    def validate_configuration(self) -> tuple[bool, str]:
        """Validate local credentials without making a billable cloud request."""

        try:
            _ = self.project_id
        except GoogleCloudConfigurationError as exc:
            return False, str(exc)
        return True, "Service-account credentials loaded."

    def transcribe_pcm(self, pcm_audio: bytes) -> str:
        """Transcribe 16-bit mono PCM captured by the INMP441 ESP32."""

        if not pcm_audio:
            return ""
        if self.settings.voice_sample_width != 2:
            raise GoogleCloudConfigurationError("Cloud Speech input is configured for 16-bit PCM only.")

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.settings.voice_sample_rate,
            language_code=self.settings.speech_language,
            alternative_language_codes=self.settings.speech_alternatives,
            model=self.settings.speech_model,
            enable_automatic_punctuation=True,
            audio_channel_count=1,
        )
        response = self.speech_client.recognize(
            config=config,
            audio=speech.RecognitionAudio(content=pcm_audio),
        )
        return " ".join(
            result.alternatives[0].transcript.strip()
            for result in response.results
            if result.alternatives and result.alternatives[0].transcript.strip()
        ).strip()

    def streaming_recognition_config(self) -> speech.StreamingRecognitionConfig:
        """Build a real-time Cloud Speech configuration for PCM from the ESP32."""

        if self.settings.voice_sample_width != 2:
            raise GoogleCloudConfigurationError("Cloud Speech input is configured for 16-bit PCM only.")
        return speech.StreamingRecognitionConfig(
            config=speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.settings.voice_sample_rate,
                language_code=self.settings.speech_language,
                alternative_language_codes=self.settings.speech_alternatives,
                model=self.settings.speech_model,
                enable_automatic_punctuation=True,
                audio_channel_count=1,
            ),
            interim_results=True,
            single_utterance=False,
            enable_voice_activity_events=True,
        )

    def generate_assistant_reply(self, prompt: str) -> GeneratedAssistantReply:
        """Generate separate LCD and Hindi/English TTS reply fields via Vertex."""

        response = self.vertex_client.models.generate_content(
            model=self.settings.vertex_gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=self.settings.assistant_max_output_tokens,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                # The agent performs no tool calls or multi-step reasoning.
                # Disabling the default thinking budget reserves output tokens
                # for the required display_text/speech_text JSON fields.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
                response_json_schema={
                    "type": "object",
                    "properties": {
                        "display_text": {
                            "type": "string",
                            "description": "Complete Latin-script Hinglish or English text for a 16x2 LCD.",
                        },
                        "speech_text": {
                            "type": "string",
                            "description": "Same meaning in natural Hindi Devanagari or English for TTS.",
                        },
                    },
                    "required": ["display_text", "speech_text"],
                },
            ),
        )
        text = _extract_response_text(response)
        if not text:
            details = _response_details(response)
            LOGGER.warning("Vertex AI returned no text. %s", details)
            raise RuntimeError(f"Vertex AI returned an empty response ({details}).")
        try:
            payload = json.loads(text)
            display_text = str(payload["display_text"]).strip()
            speech_text = str(payload["speech_text"]).strip()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Vertex AI did not return the required reply JSON fields.") from exc
        if not display_text or not speech_text:
            raise RuntimeError("Vertex AI returned blank display or speech text.")
        return GeneratedAssistantReply(display_text=display_text, speech_text=speech_text)

    def embed_texts(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Create Vertex embeddings for local Chroma storage and retrieval."""

        if not texts:
            return []
        response = self.vertex_client.models.embed_content(
            model=self.settings.knowledge_base_embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.settings.knowledge_base_embedding_dimensions,
            ),
        )
        embeddings = getattr(response, "embeddings", None) or []
        values = [list(getattr(item, "values", None) or []) for item in embeddings]
        if len(values) != len(texts) or any(not item for item in values):
            raise RuntimeError("Vertex AI did not return one embedding for each knowledge-base text.")
        return values

    def synthesize_pcm(self, text: str) -> bytes:
        """Synthesize 16-bit mono PCM for an optional I2S speaker.

        Cloud TTS returns LINEAR16 in a WAV container, while the ESP32 protocol
        carries raw PCM.  The WAV header is removed here.
        """

        if not self.settings.enable_cloud_tts:
            return b""

        voice_options: dict[str, str] = {"language_code": self.settings.tts_language}
        if self.settings.tts_voice_name.strip():
            voice_options["name"] = self.settings.tts_voice_name.strip()
        response = self.tts_client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(**voice_options),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.settings.tts_sample_rate,
            ),
        )
        try:
            with wave.open(io.BytesIO(response.audio_content), "rb") as wav_file:
                if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
                    raise GoogleCloudConfigurationError("Cloud TTS did not return 16-bit mono audio.")
                return wav_file.readframes(wav_file.getnframes())
        except wave.Error as exc:
            raise GoogleCloudConfigurationError("Cloud TTS returned invalid LINEAR16 audio.") from exc


def _extract_response_text(response: object) -> str:
    """Extract all textual candidate parts without relying on a convenience field."""

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        text = "".join((getattr(part, "text", None) or "") for part in parts).strip()
        if text:
            return text
    return ""


def _response_details(response: object) -> str:
    """Produce safe diagnostic metadata for an empty Vertex response."""

    candidates = getattr(response, "candidates", None) or []
    finishes = [str(getattr(candidate, "finish_reason", "unknown")) for candidate in candidates]
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None) if feedback else None
    return f"candidates={len(candidates)}, finish_reasons={finishes}, prompt_block={block_reason}"
