/*
  ESP32 + INMP441 voice board for new_backend.

  Required Arduino library:
    - WebSockets by Markus Sattler / Links2004

  This sketch sends 16 kHz mono 16-bit PCM to ws://BACKEND_HOST:BACKEND_PORT/ws/voice.
  It works as a microphone-only board by default. Set ENABLE_SPEAKER to 1 if
  you also wired a MAX98357A I2S amplifier using the pins below; then the
  backend's Google Cloud TTS reply will be played through the speaker.

  INMP441 wiring (set INMP441 L/R to GND for left channel):
    VDD -> 3V3, GND -> GND, SCK -> GPIO 26, WS -> GPIO 25, SD -> GPIO 22

  Touch-sensor wiring (TTP223-style module):
    VCC -> 3V3, GND -> GND, OUT -> GPIO 18
  The module must output HIGH while touched. Red LED is GPIO 4; green LED is
  GPIO 5, matching the previously working voice-board wiring.
*/

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>

// ---------- CHANGE THESE VALUES ----------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_HOST = "172.20.10.14";  // Laptop Wi-Fi / hotspot IPv4
const uint16_t BACKEND_PORT = 8000;
// ----------------------------------------

// 0 = mic-only. 1 = receive and play Cloud TTS using a MAX98357A speaker.
#define ENABLE_SPEAKER 0

constexpr uint8_t TOUCH_SENSOR_PIN = 18;  // TTP223 OUT: HIGH when touched.
constexpr uint8_t RECORDING_LED_PIN = 4;  // Red LED.
constexpr uint8_t READY_LED_PIN = 5;      // Green LED.
constexpr uint8_t MIC_SCK_PIN = 26;
constexpr uint8_t MIC_WS_PIN = 25;
constexpr uint8_t MIC_SD_PIN = 22;

#if ENABLE_SPEAKER
constexpr uint8_t SPEAKER_BCLK_PIN = 32;
constexpr uint8_t SPEAKER_LRCK_PIN = 33;
constexpr uint8_t SPEAKER_DIN_PIN = 19;
#endif

constexpr uint32_t SAMPLE_RATE = 16000;
constexpr size_t MIC_SAMPLE_COUNT = 256;
constexpr unsigned long DEBOUNCE_MS = 250;
constexpr unsigned long PROCESS_TIMEOUT_MS = 35000;

enum VoiceState { DISCONNECTED, IDLE, RECORDING, PROCESSING, PLAYING };
VoiceState voiceState = DISCONNECTED;
WebSocketsClient webSocket;
bool previousTouchState = false;
unsigned long previousTouchEvent = 0;
unsigned long processStartedAt = 0;

#if ENABLE_SPEAKER
int expectedAudioBytes = 0;
int receivedAudioBytes = 0;
bool waitingForAudioSize = false;
bool speakerHasOddByte = false;
uint8_t speakerOddByte = 0;
#endif

void showStatus(const String& message) {
  Serial.printf("[VOICE] %s\n", message.c_str());
}

void setIndicators(bool recording, bool ready) {
  digitalWrite(RECORDING_LED_PIN, recording ? HIGH : LOW);
  digitalWrite(READY_LED_PIN, ready ? HIGH : LOW);
}

void setVoiceState(VoiceState nextState) {
  voiceState = nextState;
  switch (voiceState) {
    case DISCONNECTED:
      setIndicators(false, false);
      break;
    case IDLE:
      setIndicators(false, true);
      break;
    case RECORDING:
      setIndicators(true, false);
      break;
    case PROCESSING:
    case PLAYING:
      setIndicators(false, true);
      break;
  }
}

void setupMicrophone() {
  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  config.sample_rate = SAMPLE_RATE;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 8;
  config.dma_buf_len = MIC_SAMPLE_COUNT;
  config.use_apll = false;
  config.tx_desc_auto_clear = false;
  config.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = MIC_SCK_PIN;
  pins.ws_io_num = MIC_WS_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = MIC_SD_PIN;
  i2s_driver_install(I2S_NUM_0, &config, 0, nullptr);
  i2s_set_pin(I2S_NUM_0, &pins);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

#if ENABLE_SPEAKER
void setupSpeaker() {
  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  config.sample_rate = SAMPLE_RATE;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 8;
  config.dma_buf_len = 128;
  config.use_apll = false;
  config.tx_desc_auto_clear = true;
  config.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = SPEAKER_BCLK_PIN;
  pins.ws_io_num = SPEAKER_LRCK_PIN;
  pins.data_out_num = SPEAKER_DIN_PIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_driver_install(I2S_NUM_1, &config, 0, nullptr);
  i2s_set_pin(I2S_NUM_1, &pins);
  i2s_zero_dma_buffer(I2S_NUM_1);
}

void playPcmBytes(uint8_t* payload, size_t length) {
  int16_t samples[128];
  size_t sampleCount = 0;
  size_t index = 0;

  if (speakerHasOddByte && length > 0) {
    samples[sampleCount++] = static_cast<int16_t>(speakerOddByte | (payload[0] << 8));
    speakerHasOddByte = false;
    index = 1;
  }

  while (index + 1 < length) {
    samples[sampleCount++] = static_cast<int16_t>(payload[index] | (payload[index + 1] << 8));
    index += 2;
    if (sampleCount == 128) {
      size_t written = 0;
      i2s_write(I2S_NUM_1, samples, sampleCount * sizeof(int16_t), &written, portMAX_DELAY);
      sampleCount = 0;
    }
  }
  if (index < length) {
    speakerOddByte = payload[index];
    speakerHasOddByte = true;
  }
  if (sampleCount > 0) {
    size_t written = 0;
    i2s_write(I2S_NUM_1, samples, sampleCount * sizeof(int16_t), &written, portMAX_DELAY);
  }
}
#endif

void beginRecording() {
  if (!webSocket.isConnected()) {
    showStatus("Backend WebSocket is not connected");
    return;
  }
  setVoiceState(RECORDING);
  webSocket.sendTXT("START");
  showStatus("Listening - press button again to stop");
}

void stopRecording() {
  setVoiceState(PROCESSING);
  processStartedAt = millis();
  webSocket.sendTXT("STOP");
  showStatus("Processing...");
}

void sendMicrophoneFrame() {
  int32_t rawSamples[MIC_SAMPLE_COUNT];
  size_t bytesRead = 0;
  const esp_err_t result = i2s_read(I2S_NUM_0, rawSamples, sizeof(rawSamples), &bytesRead, portMAX_DELAY);
  if (result != ESP_OK || bytesRead == 0) return;

  // INMP441 provides 24-bit data in a 32-bit I2S frame. Convert it to signed
  // 16-bit little-endian PCM, matching VOICE_SAMPLE_RATE=16000 and
  // VOICE_SAMPLE_WIDTH=2 in new_backend/.env.
  uint8_t pcmBytes[MIC_SAMPLE_COUNT * 2];
  size_t pcmLength = 0;
  const size_t count = bytesRead / sizeof(int32_t);
  for (size_t i = 0; i < count; ++i) {
    const int16_t sample = static_cast<int16_t>(rawSamples[i] >> 16);
    pcmBytes[pcmLength++] = static_cast<uint8_t>(sample & 0xFF);
    pcmBytes[pcmLength++] = static_cast<uint8_t>((sample >> 8) & 0xFF);
  }
  if (pcmLength > 0) webSocket.sendBIN(pcmBytes, pcmLength);
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    showStatus("Connected to backend");
    setVoiceState(IDLE);
    return;
  }
  if (type == WStype_DISCONNECTED) {
    showStatus("Backend disconnected");
    setVoiceState(DISCONNECTED);
    return;
  }

  if (type == WStype_TEXT) {
    // Do not assume a WebSocket text frame carries a trailing NUL byte.
    String text;
    text.reserve(length);
    for (size_t index = 0; index < length; ++index) text += static_cast<char>(payload[index]);
    if (text.startsWith("LCD:")) {
      showStatus(text.substring(4));
      return;
    }
    if (text == "VOICE_DONE") {
      setVoiceState(IDLE);
      showStatus("Ready");
      return;
    }
    if (text.startsWith("TRANSCRIPT:")) {
      Serial.printf("[TRANSCRIPT] %s\n", text.substring(11).c_str());
      return;
    }
    if (text == "PONG") return;

#if ENABLE_SPEAKER
    if (text == "AUDIO_START") {
      waitingForAudioSize = true;
      expectedAudioBytes = 0;
      receivedAudioBytes = 0;
      speakerHasOddByte = false;
      voiceState = PLAYING;
      return;
    }
    if (waitingForAudioSize) {
      expectedAudioBytes = text.toInt();
      waitingForAudioSize = false;
      return;
    }
#endif
    return;
  }

#if ENABLE_SPEAKER
  if (type == WStype_BIN && voiceState == PLAYING) {
    playPcmBytes(payload, length);
    receivedAudioBytes += length;
    if (expectedAudioBytes > 0 && receivedAudioBytes >= expectedAudioBytes) {
      voiceState = IDLE;
      showStatus("Ready");
    }
  }
#endif
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WIFI] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[WIFI] Connected: %s\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  pinMode(TOUCH_SENSOR_PIN, INPUT);
  pinMode(RECORDING_LED_PIN, OUTPUT);
  pinMode(READY_LED_PIN, OUTPUT);
  setVoiceState(DISCONNECTED);
  setupMicrophone();
#if ENABLE_SPEAKER
  setupSpeaker();
#endif
  connectWifi();
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/voice");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  showStatus("Ready");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  webSocket.loop();

  // One rising edge is one touch. Holding the sensor must not repeatedly
  // start/stop recording, so it only acts after a release and new touch.
  const bool touchDetected = digitalRead(TOUCH_SENSOR_PIN) == HIGH;
  if (touchDetected && !previousTouchState && millis() - previousTouchEvent > DEBOUNCE_MS) {
    previousTouchEvent = millis();
    if (voiceState == IDLE) beginRecording();
    else if (voiceState == RECORDING) stopRecording();
  }
  previousTouchState = touchDetected;

  if (voiceState == RECORDING) sendMicrophoneFrame();
  if (voiceState == PROCESSING && millis() - processStartedAt > PROCESS_TIMEOUT_MS) {
    showStatus("Voice request timed out");
    setVoiceState(IDLE);
  }
  delay(1);
}
