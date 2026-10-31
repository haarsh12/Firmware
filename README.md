# Smart Home Vertex AI Backend

This is a clean replacement backend for the existing home-automation project.
It preserves the prior HTTP and WebSocket contracts while replacing the Gemini
API key with the supplied Google Cloud service-account JSON. The key is read in
place, never copied into this project, and `.env`/JSON credential files are
ignored by Git.

## What is included .


- FastAPI backend using a service account for Vertex AI Gemini, Cloud
  Speech-to-Text, and optional Cloud Text-to-Speech.
- Existing phone-app endpoints: `/api/sensor/data`, `/api/device/control`,
  `/api/device/status`, `/app/sensors`, and `/app/relay`.
- ESP32 compatibility endpoints: `/sensors/data`, `/api/sensors/update`, and
  a relay channel at `/ws/relay`.
- Voice channel at `/ws/voice` for 16 kHz, 16-bit, mono PCM audio. It streams
  interim transcript updates as you speak, instead of waiting to upload an
  entire recording first.
- A deterministic relay parser: the LLM cannot decide which physical device to
  switch; only direct user phrases such as `light on`, `batti band`, and
  `pankha chalu` create commands.
- Complete sketches at `firmware/esp32_relay/esp32_relay.ino` and
  `firmware/esp32_inmp441_voice/esp32_inmp441_voice.ino`.

## Google Cloud preparation

Use the service account from the supplied credential file. On its Google Cloud
project, enable these APIs:

1. Vertex AI API
2. Cloud Speech-to-Text API
3. Cloud Text-to-Speech API, if `ENABLE_CLOUD_TTS=true`

For least privilege, grant that service account the roles required for each
enabled API, including **Vertex AI User** (`roles/aiplatform.user`) and **Cloud
Speech Client** (`roles/speech.client`), rather than project Owner. Cloud
Speech and Text-to-Speech client libraries use Google Application Default
Credentials; this project supplies the same service-account credential directly
to every Google client.

## Install and start (Windows PowerShell)

```powershell
cd D:\home_ss\new_backend
.\setup_venv.ps1
.\start.ps1
```

`setup_venv.ps1` creates `venv`, installs all required packages, and creates a
local `.env` if it is absent. Its default credential path points to:

```text
../home_automation/project-d8fe05cb-90bb-4815-aca-c79b84dcbad5.json
```

Start-up validates that the file can be loaded. Then visit:

- `http://localhost:8000/docs` for interactive API documentation.
- `http://localhost:8000/health` for credential and relay-board status.

## ESP32 flashing

1. Install Arduino libraries **WebSockets** (Links2004) and **ArduinoJson 6**.
   The relay sketch also requires **DHT sensor library by Adafruit** when its
   `ENABLE_DHT_SENSOR` setting is left as `1`.
2. Edit `WIFI_SSID`, `WIFI_PASSWORD`, `BACKEND_HOST`, and `BACKEND_PORT` in
   both sketches. `BACKEND_HOST` is the LAN address printed by Windows, not
   `localhost`. The supplied microphone sketch is prefilled for laptop IP
   `172.20.10.14`; update it if the hotspot/DHCP address changes.
3. Confirm the GPIO wiring / relay active-level constants match your board.
4. Upload the relay sketch first. `/health` should report one relay connection.
5. Upload the INMP441 sketch. One touch starts a voice turn. After you finish
   speaking, 1.2 seconds of silence sends it automatically; a second touch is
   still available as a manual stop. Its Serial Monitor shows live partial
   transcripts, final transcript, audio frame diagnostics, and response.

For an internet-hosted backend, ESP32 boards need TLS (`wss://`/`https://`).
These supplied sketches target a trusted local LAN using `ws://` and `http://`.
Do not expose the local backend directly to the public internet.

## Wire protocol

The relay board sends `{"type":"relay_status","light":true,"fan":false}`.
The backend sends `{"type":"relay_command","device":"light","state":true}`.

The voice board sends the following sequence. Binary frames are sent live at
roughly 100 ms per frame, so Cloud Speech can produce partial transcript
updates before recording ends:

```text
START
<binary 16-bit mono PCM chunks>
STOP
```

The backend sends `PARTIAL:...`, `FINAL:...`, `TRANSCRIPT:...`, `REPLY:...`,
`STATUS:...`, and `LCD:...`. Only when TTS is enabled it also sends
`AUDIO_START`, byte count, and raw 16-bit PCM chunks. Every voice turn ends
with `VOICE_DONE`; the microphone firmware then returns to Ready.

## Test

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

The tests cover local relay phrase parsing and require no cloud access. A real
voice turn requires billing/API enablement and the IAM roles listed above.

## Official references

Google’s [Gemini API on Vertex AI quickstart](https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart)
documents the Vertex AI User role and the Gen AI SDK. The [Cloud Speech
client-library guide](https://cloud.google.com/speech-to-text/docs/libraries)
and [Cloud Text-to-Speech client-library guide](https://cloud.google.com/text-to-speech/docs/libraries)
document the Python clients used here. Google’s [Speech-to-Text IAM
reference](https://cloud.google.com/iam/docs/roles-permissions/speech) lists
the Cloud Speech Client role.
