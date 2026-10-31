"""Google Cloud clients authenticated solely with a service-account file."""

from __future__ import annotations

import io
import logging
import wave
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

    def generate_assistant_reply(self, prompt: str) -> str:
        """Generate one concise assistant reply through Vertex AI Gemini."""

        response = self.vertex_client.models.generate_content(
            model=self.settings.vertex_gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=80,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Vertex AI returned an empty response.")
        return text

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
