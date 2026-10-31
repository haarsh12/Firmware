/*
  MAX98357A + speaker test for Arduino IDE.

  This test intentionally has NO microphone, LCD, relay, or touch sensor. It
  connects to new_backend /ws/speaker-test, asks Google Cloud TTS to say
  "Hello world, how are you?", and plays the returned raw PCM on the speaker.
  It repeats the phrase after a two-second quiet gap, so amplifier volume and
  wiring can be tuned without touching the ESP32.

  Required Arduino library: WebSockets by Markus Sattler / Links2004

  ESP32 -> MAX98357A:
    GPIO 32 -> BCLK / BCK
    GPIO 33 -> LRC / WS / LRCLK
    GPIO 19 -> DIN
    GND     -> GND
    5V      -> VIN (use a stable supply; share ground with the ESP32)
  Speaker: connect directly to MAX98357A SPK+ and SPK-. Never connect either
  speaker terminal to ESP32 GND.
*/

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>

// ---------- CHANGE ONLY YOUR WIFI VALUES ----------
const char* WIFI_SSID = "Harsh's Galaxy A21s";
const char* WIFI_PASSWORD = "datachor";
const char* BACKEND_HOST = "192.168.134.207";  // Laptop Wi-Fi / hotspot IPv4
const uint16_t BACKEND_PORT = 8000;
// ---------------------------------------------------

constexpr uint8_t SPEAKER_BCLK_PIN = 32;
constexpr uint8_t SPEAKER_LRCK_PIN = 33;
constexpr uint8_t SPEAKER_DIN_PIN = 19;
constexpr uint32_t SAMPLE_RATE = 16000;
constexpr float SPEAKER_GAIN = 1.6F;
constexpr unsigned long REPEAT_GAP_MS = 2000;
const char* TEST_PHRASE = "Hello world, how are you?";

WebSocketsClient webSocket;
bool waitingForAudioSize = false;
bool hasOddByte = false;
uint8_t oddByte = 0;
int expectedBytes = 0;
int receivedBytes = 0;
bool playbackActive = false;
bool requestInFlight = false;
unsigned long nextTestRequestAt = 0;

void scheduleNextTest(unsigned long delayMs = REPEAT_GAP_MS) {
  requestInFlight = false;
  playbackActive = false;
  nextTestRequestAt = millis() + delayMs;
}

void requestTestSpeech() {
  if (!webSocket.isConnected() || requestInFlight || playbackActive) return;
  requestInFlight = true;
  Serial.println("[TEST] Requesting the next speaker phrase");
  webSocket.sendTXT(String("SPEAK:") + TEST_PHRASE);
}

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

  const esp_err_t installResult = i2s_driver_install(I2S_NUM_1, &config, 0, nullptr);
  const esp_err_t pinResult = i2s_set_pin(I2S_NUM_1, &pins);
  i2s_zero_dma_buffer(I2S_NUM_1);
  Serial.printf("[SPEAKER] I2S install=%d pins=%d\n", installResult, pinResult);
}

void playPcm(uint8_t* payload, size_t length) {
  int16_t samples[128];
  size_t sampleCount = 0;
  size_t index = 0;
  if (hasOddByte && length > 0) {
    samples[sampleCount++] = static_cast<int16_t>(oddByte | (payload[0] << 8));
    hasOddByte = false;
    index = 1;
  }
  while (index + 1 < length) {
    int32_t sample = static_cast<int16_t>(payload[index] | (payload[index + 1] << 8));
    sample = static_cast<int32_t>(sample * SPEAKER_GAIN);
    samples[sampleCount++] = static_cast<int16_t>(constrain(sample, -32768, 32767));
    index += 2;
    if (sampleCount == 128) {
      size_t written = 0;
      i2s_write(I2S_NUM_1, samples, sampleCount * sizeof(int16_t), &written, portMAX_DELAY);
      sampleCount = 0;
    }
  }
  if (index < length) {
    oddByte = payload[index];
    hasOddByte = true;
  }
  if (sampleCount > 0) {
    size_t written = 0;
    i2s_write(I2S_NUM_1, samples, sampleCount * sizeof(int16_t), &written, portMAX_DELAY);
  }
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    Serial.println("[WS] Connected. Test phrase will repeat every 2 seconds after playback.");
    scheduleNextTest(300);
    return;
  }
  if (type == WStype_DISCONNECTED) {
    Serial.println("[WS] Disconnected; will reconnect.");
    requestInFlight = false;
    playbackActive = false;
    return;
  }
  if (type == WStype_TEXT) {
    String text;
    text.reserve(length);
    for (size_t index = 0; index < length; ++index) text += static_cast<char>(payload[index]);
    Serial.printf("[WS] %s\n", text.c_str());
    if (text == "AUDIO_START") {
      waitingForAudioSize = true;
      expectedBytes = 0;
      receivedBytes = 0;
      hasOddByte = false;
      playbackActive = true;
    } else if (waitingForAudioSize) {
      expectedBytes = text.toInt();
      waitingForAudioSize = false;
      Serial.printf("[SPEAKER] Receiving %d bytes\n", expectedBytes);
    } else if (text == "AUDIO_END") {
      Serial.printf("[SPEAKER] Test finished; received %d bytes\n", receivedBytes);
      scheduleNextTest();
    } else if (text.startsWith("ERROR:")) {
      Serial.println("[TEST] Backend error; retrying in 2 seconds.");
      scheduleNextTest();
    }
    return;
  }
  if (type == WStype_BIN) {
    playPcm(payload, length);
    receivedBytes += length;
    if (expectedBytes > 0 && receivedBytes >= expectedBytes) {
      Serial.println("[SPEAKER] PCM playback complete.");
    }
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WIFI] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  Serial.printf("\n[WIFI] Connected: %s\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  setupSpeaker();
  connectWifi();
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/speaker-test");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  webSocket.loop();
  if (webSocket.isConnected() && !requestInFlight && !playbackActive &&
      static_cast<long>(millis() - nextTestRequestAt) >= 0) {
    requestTestSpeech();
  }
  delay(1);
}
