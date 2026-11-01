/*
  Smart-home voice agent: ESP32 + INMP441 + MAX98357A + 16x2 I2C LCD.

  Arduino libraries:
    - WebSockets by Markus Sattler / Links2004
    - LiquidCrystal_I2C

  Pin map for this specific voice board:
    TTP223 touch OUT   -> GPIO 5 (HIGH when touched)
    Recording LED      -> GPIO 18
    Ready LED          -> GPIO 19
    Backend LED        -> GPIO 21 (ON only while /ws/voice is connected)
    AI-response LED    -> GPIO 22 (ON while transcript/AI/TTS is processing)

    INMP441: SCK -> GPIO 26, WS -> GPIO 25, SD -> GPIO 32
    MAX98357A: BCLK -> GPIO 14, LRC/WS -> GPIO 27, DIN -> GPIO 33
    OLED I2C: SDA -> GPIO 4, SCL -> GPIO 15

  The backend address below is the laptop hotspot/LAN address supplied for
  this project. Change only if the laptop address changes.
*/

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <math.h>

// ---------- CHANGE ONLY YOUR WIFI VALUES ----------
const char* WIFI_SSID = "Harsh's Galaxy A21s";
const char* WIFI_PASSWORD = "datachor";
const char* BACKEND_HOST = "192.168.50.207";  // Laptop Wi-Fi / hotspot IPv4
const uint16_t BACKEND_PORT = 8000;
// ---------------------------------------------------

// Change 0x3C to 0x3D if your OLED does not respond at 0x3C.
constexpr uint8_t OLED_ADDRESS = 0x3C;
constexpr uint8_t OLED_SDA_PIN = 4;
constexpr uint8_t OLED_SCL_PIN = 15;

constexpr uint8_t TOUCH_SENSOR_PIN = 5;
constexpr uint8_t RECORDING_LED_PIN = 18;
constexpr uint8_t READY_LED_PIN = 19;
constexpr uint8_t BACKEND_LED_PIN = 21;
constexpr uint8_t AI_RESPONSE_LED_PIN = 22;

constexpr uint8_t MIC_SCK_PIN = 26;
constexpr uint8_t MIC_WS_PIN = 25;
constexpr uint8_t MIC_SD_PIN = 32;

constexpr uint8_t SPEAKER_BCLK_PIN = 14;
constexpr uint8_t SPEAKER_LRCK_PIN = 27;
constexpr uint8_t SPEAKER_DIN_PIN = 33;

constexpr uint32_t SAMPLE_RATE = 16000;
constexpr size_t MIC_FRAME_SAMPLES = 1600;      // 100 ms at 16 kHz
constexpr size_t I2S_DMA_BUFFER_SAMPLES = 256;
constexpr unsigned long DEBOUNCE_MS = 250;
constexpr unsigned long MIN_RECORDING_MS = 8000;
constexpr unsigned long MAX_RECORDING_MS = 60000;
constexpr unsigned long AUTO_STOP_SILENCE_MS = 1800;
constexpr unsigned long PROCESS_TIMEOUT_MS = 80000;
constexpr unsigned long AUDIO_DEBUG_INTERVAL_MS = 500;
constexpr int SPEECH_RMS_THRESHOLD = 1000;
constexpr float SPEAKER_GAIN = 1.6F;
// Temporary diagnostic: a short 1 kHz tone before each cloud reply proves
// that the full firmware's MAX98357A output path is physically audible.
constexpr bool SPEAKER_DIAGNOSTIC_TONE = true;

enum VoiceState { DISCONNECTED, IDLE, RECORDING, PROCESSING, PLAYING };

WebSocketsClient webSocket;
LiquidCrystal_I2C lcd(OLED_ADDRESS, 16, 2);
VoiceState voiceState = DISCONNECTED;

bool previousTouchState = false;
unsigned long previousTouchEvent = 0;
unsigned long recordingStartedAt = 0;
unsigned long lastSpeechAt = 0;
unsigned long lastAudioDebugAt = 0;
unsigned long processStartedAt = 0;
unsigned long sentAudioBytes = 0;
unsigned long sentAudioFrames = 0;
bool heardSpeech = false;

int expectedAudioBytes = 0;
int receivedAudioBytes = 0;
bool waitingForAudioSize = false;
bool speakerHasOddByte = false;
uint8_t speakerOddByte = 0;
bool microphoneInstalled = false;
bool microphoneRunning = false;
size_t speakerI2sWrittenBytes = 0;
unsigned long speakerI2sWriteErrors = 0;

// Static storage avoids overflowing the ESP32 loop stack.
int32_t rawMicrophoneSamples[MIC_FRAME_SAMPLES];
uint8_t pcmMicrophoneBytes[MIC_FRAME_SAMPLES * 2];

String lcdLine1;
String lcdLine2;
String lcdPendingWords;
bool lcdFillingSecondLine = false;
bool lcdScrolling = false;
unsigned long nextLcdWordAt = 0;

void logVoice(const String& message) {
  Serial.printf("[VOICE] %s\n", message.c_str());
}

String lcdField(const String& source) {
  String field = source.substring(0, 16);
  while (field.length() < 16) field += ' ';
  return field;
}

void renderLcd() {
  lcd.setCursor(0, 0);
  lcd.print(lcdField(lcdLine1));
  lcd.setCursor(0, 1);
  lcd.print(lcdField(lcdLine2));
}

void showLcdStatus(const String& line1, const String& line2 = "") {
  lcdScrolling = false;
  lcdPendingWords = "";
  lcdLine1 = line1;
  lcdLine2 = line2;
  renderLcd();
}

String takeNextLcdWord() {
  lcdPendingWords.trim();
  if (lcdPendingWords.length() == 0) return "";
  const int spaceAt = lcdPendingWords.indexOf(' ');
  String word;
  if (spaceAt < 0) {
    word = lcdPendingWords;
    lcdPendingWords = "";
  } else {
    word = lcdPendingWords.substring(0, spaceAt);
    lcdPendingWords = lcdPendingWords.substring(spaceAt + 1);
  }
  // A word longer than the LCD width is displayed in successive pieces.
  if (word.length() > 16) {
    lcdPendingWords = word.substring(16) + " " + lcdPendingWords;
    word = word.substring(0, 16);
  }
  return word;
}

void beginLcdReply(const String& reply) {
  lcdLine1 = "";
  lcdLine2 = "";
  lcdPendingWords = reply;
  lcdFillingSecondLine = false;
  lcdScrolling = true;
  nextLcdWordAt = 0;
}

void updateLcdReply() {
  if (!lcdScrolling || millis() < nextLcdWordAt) return;
  const String word = takeNextLcdWord();
  if (word.length() == 0) {
    lcdScrolling = false;
    return;
  }

  if (!lcdFillingSecondLine) {
    const String candidate = lcdLine1.length() ? lcdLine1 + " " + word : word;
    if (candidate.length() <= 16) {
      lcdLine1 = candidate;
    } else {
      lcdFillingSecondLine = true;
      lcdLine2 = word;
    }
  } else {
    const String candidate = lcdLine2.length() ? lcdLine2 + " " + word : word;
    if (candidate.length() <= 16) {
      lcdLine2 = candidate;
    } else {
      // Terminal-like two-line rolling display: old line 1 drops away,
      // previous line 2 becomes line 1, and the new word starts line 2.
      lcdLine1 = lcdLine2;
      lcdLine2 = word;
    }
  }
  renderLcd();
  nextLcdWordAt = millis() + 380;
}

void setBackendConnected(bool connected) {
  digitalWrite(BACKEND_LED_PIN, connected ? HIGH : LOW);
}

void setAiResponding(bool active) {
  digitalWrite(AI_RESPONSE_LED_PIN, active ? HIGH : LOW);
}

void setVoiceState(VoiceState nextState) {
  voiceState = nextState;
  switch (voiceState) {
    case DISCONNECTED:
      digitalWrite(RECORDING_LED_PIN, LOW);
      digitalWrite(READY_LED_PIN, LOW);
      break;
    case IDLE:
      digitalWrite(RECORDING_LED_PIN, LOW);
      digitalWrite(READY_LED_PIN, HIGH);
      break;
    case RECORDING:
      digitalWrite(RECORDING_LED_PIN, HIGH);
      digitalWrite(READY_LED_PIN, LOW);
      break;
    case PROCESSING:
    case PLAYING:
      digitalWrite(RECORDING_LED_PIN, LOW);
      digitalWrite(READY_LED_PIN, HIGH);
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
  config.dma_buf_len = I2S_DMA_BUFFER_SAMPLES;
  config.use_apll = false;
  config.tx_desc_auto_clear = false;
  config.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = MIC_SCK_PIN;
  pins.ws_io_num = MIC_WS_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = MIC_SD_PIN;
  const esp_err_t installResult = i2s_driver_install(I2S_NUM_0, &config, 0, nullptr);
  const esp_err_t pinResult = i2s_set_pin(I2S_NUM_0, &pins);
  i2s_zero_dma_buffer(I2S_NUM_0);
  microphoneInstalled = installResult == ESP_OK && pinResult == ESP_OK;
  microphoneRunning = microphoneInstalled;
  Serial.printf("[MIC] I2S install=%d pins=%d\n", installResult, pinResult);
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
    int32_t sample = static_cast<int16_t>(payload[index] | (payload[index + 1] << 8));
    sample = static_cast<int32_t>(sample * SPEAKER_GAIN);
    samples[sampleCount++] = static_cast<int16_t>(constrain(sample, -32768, 32767));
    index += 2;
    if (sampleCount == 128) {
      size_t written = 0;
      const esp_err_t result = i2s_write(
          I2S_NUM_1, samples, sampleCount * sizeof(int16_t), &written, portMAX_DELAY);
      speakerI2sWrittenBytes += written;
      if (result != ESP_OK || written != sampleCount * sizeof(int16_t)) speakerI2sWriteErrors++;
      sampleCount = 0;
    }
  }
  if (index < length) {
    speakerOddByte = payload[index];
    speakerHasOddByte = true;
  }
  if (sampleCount > 0) {
    size_t written = 0;
    const esp_err_t result = i2s_write(
        I2S_NUM_1, samples, sampleCount * sizeof(int16_t), &written, portMAX_DELAY);
    speakerI2sWrittenBytes += written;
    if (result != ESP_OK || written != sampleCount * sizeof(int16_t)) speakerI2sWriteErrors++;
  }
}

void playSpeakerDiagnosticTone() {
  if (!SPEAKER_DIAGNOSTIC_TONE) return;
  constexpr size_t TONE_SAMPLES = 1600;  // 100 ms at 16 kHz
  constexpr float PI_F = 3.14159265F;
  int16_t tone[160];
  for (size_t block = 0; block < TONE_SAMPLES / 160; ++block) {
    for (size_t index = 0; index < 160; ++index) {
      const float phase = 2.0F * PI_F * 1000.0F * (block * 160 + index) / SAMPLE_RATE;
      tone[index] = static_cast<int16_t>(sinf(phase) * 5000.0F);
    }
    size_t written = 0;
    const esp_err_t result = i2s_write(I2S_NUM_1, tone, sizeof(tone), &written, portMAX_DELAY);
    speakerI2sWrittenBytes += written;
    if (result != ESP_OK || written != sizeof(tone)) speakerI2sWriteErrors++;
  }
  Serial.println("[SPEAKER] Diagnostic tone queued");
}

void prepareSpeakerForPlayback() {
  // Some ESP32 Arduino-core/board combinations do not reliably drive I2S1
  // when I2S0 (the INMP441 receiver) remains installed, even if I2S0 is
  // stopped. Fully release the microphone peripheral, then freshly install
  // the known-working MAX98357A configuration from the standalone test.
  if (microphoneInstalled) {
    if (microphoneRunning) {
      const esp_err_t stopResult = i2s_stop(I2S_NUM_0);
      Serial.printf("[MIC] I2S paused for speaker=%d\n", stopResult);
    }
    const esp_err_t uninstallResult = i2s_driver_uninstall(I2S_NUM_0);
    Serial.printf("[MIC] I2S released for speaker=%d\n", uninstallResult);
    microphoneInstalled = false;
    microphoneRunning = false;
  }

  const esp_err_t speakerUninstallResult = i2s_driver_uninstall(I2S_NUM_1);
  Serial.printf("[SPEAKER] I2S reset=%d\n", speakerUninstallResult);
  setupSpeaker();
}

void beginRecording() {
  if (!webSocket.isConnected()) {
    logVoice("Backend WebSocket is not connected");
    showLcdStatus("Backend offline", "Check WiFi");
    return;
  }
  setVoiceState(RECORDING);
  if (!microphoneInstalled) {
    setupMicrophone();
  }
  if (!microphoneRunning) {
    const esp_err_t result = i2s_start(I2S_NUM_0);
    microphoneRunning = result == ESP_OK;
    Serial.printf("[MIC] I2S resume=%d\n", result);
    if (!microphoneRunning) {
      logVoice("Microphone could not resume");
      setVoiceState(IDLE);
      return;
    }
  }
  setAiResponding(false);
  recordingStartedAt = millis();
  lastSpeechAt = recordingStartedAt;
  lastAudioDebugAt = recordingStartedAt;
  sentAudioBytes = 0;
  sentAudioFrames = 0;
  heardSpeech = false;
  i2s_zero_dma_buffer(I2S_NUM_0);
  webSocket.sendTXT("START");
  logVoice("Listening - speak; manual touch or silence sends after 8 seconds");
  showLcdStatus("Listening...", "Speak now");
}

void stopRecording(const char* reason = "manual touch") {
  if (voiceState != RECORDING) return;
  setVoiceState(PROCESSING);
  setAiResponding(true);
  processStartedAt = millis();
  // Do not keep the INMP441 receiver clocking while MAX98357A is playing.
  // This avoids peripheral/DMA contention on ESP32 Arduino core versions.
  webSocket.sendTXT("STOP");
  Serial.printf("[VOICE] Recording stopped (%s): frames=%lu bytes=%lu duration=%.2fs\n",
                reason, sentAudioFrames, sentAudioBytes,
                (millis() - recordingStartedAt) / 1000.0);
  showLcdStatus("Processing...", "Please wait");
}

void sendMicrophoneFrame() {
  size_t bytesRead = 0;
  const esp_err_t result = i2s_read(
      I2S_NUM_0, rawMicrophoneSamples, sizeof(rawMicrophoneSamples), &bytesRead, portMAX_DELAY);
  if (result != ESP_OK || bytesRead == 0) return;

  const size_t count = bytesRead / sizeof(int32_t);
  size_t pcmLength = 0;
  int64_t sumSquares = 0;
  for (size_t index = 0; index < count; ++index) {
    const int16_t sample = static_cast<int16_t>(rawMicrophoneSamples[index] >> 16);
    sumSquares += static_cast<int64_t>(sample) * sample;
    pcmMicrophoneBytes[pcmLength++] = static_cast<uint8_t>(sample & 0xFF);
    pcmMicrophoneBytes[pcmLength++] = static_cast<uint8_t>((sample >> 8) & 0xFF);
  }
  if (pcmLength > 0 && webSocket.isConnected()) {
    webSocket.sendBIN(pcmMicrophoneBytes, pcmLength);
    sentAudioBytes += pcmLength;
    sentAudioFrames++;
  }

  const int rms = count ? static_cast<int>(sqrt(static_cast<double>(sumSquares) / count)) : 0;
  const unsigned long now = millis();
  if (rms >= SPEECH_RMS_THRESHOLD) {
    heardSpeech = true;
    lastSpeechAt = now;
  }
  if (now - lastAudioDebugAt >= AUDIO_DEBUG_INTERVAL_MS) {
    Serial.printf("[AUDIO] frame=%lu rms=%d threshold=%d speech=%s bytes=%lu\n",
                  sentAudioFrames, rms, SPEECH_RMS_THRESHOLD,
                  rms >= SPEECH_RMS_THRESHOLD ? "yes" : "no", sentAudioBytes);
    lastAudioDebugAt = now;
  }

  if (now - recordingStartedAt >= MAX_RECORDING_MS) {
    stopRecording("60 second maximum");
  } else if (heardSpeech && now - recordingStartedAt >= MIN_RECORDING_MS &&
             now - lastSpeechAt >= AUTO_STOP_SILENCE_MS) {
    stopRecording("speech silence detected");
  }
}

void handleBackendStatus(const String& status) {
  Serial.printf("[BACKEND STATUS] %s\n", status.c_str());
  if (status.startsWith("Finalizing") || status.startsWith("Thinking") ||
      status.startsWith("Generating audio")) {
    setAiResponding(true);
  }
}

void handleLcdMessage(const String& message) {
  logVoice(message);
  if (message == "Listening...") {
    showLcdStatus("Listening...", "Speak now");
  } else if (message == "Processing...") {
    showLcdStatus("Processing...", "Please wait");
  } else {
    beginLcdReply(message);
  }
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    logVoice("Connected to backend");
    setBackendConnected(true);
    setVoiceState(IDLE);
    showLcdStatus("AI Home", "Ready");
    return;
  }
  if (type == WStype_DISCONNECTED) {
    logVoice("Backend disconnected");
    setBackendConnected(false);
    setAiResponding(false);
    setVoiceState(DISCONNECTED);
    showLcdStatus("Backend offline", "Reconnecting...");
    return;
  }

  if (type == WStype_TEXT) {
    String text;
    text.reserve(length);
    for (size_t index = 0; index < length; ++index) text += static_cast<char>(payload[index]);

    if (text.startsWith("LCD:")) {
      handleLcdMessage(text.substring(4));
      return;
    }
    if (text.startsWith("STATUS:")) {
      handleBackendStatus(text.substring(7));
      return;
    }
    if (text.startsWith("DEBUG:")) {
      Serial.printf("[BACKEND DEBUG] %s\n", text.substring(6).c_str());
      return;
    }
    if (text.startsWith("PARTIAL:")) {
      Serial.printf("[PARTIAL TRANSCRIPT] %s\n", text.substring(8).c_str());
      return;
    }
    if (text.startsWith("FINAL:")) {
      Serial.printf("[FINAL TRANSCRIPT] %s\n", text.substring(6).c_str());
      return;
    }
    if (text.startsWith("TRANSCRIPT:")) {
      Serial.printf("[TRANSCRIPT] %s\n", text.substring(11).c_str());
      return;
    }
    if (text.startsWith("REPLY:")) {
      Serial.printf("[ASSISTANT REPLY] %s\n", text.substring(6).c_str());
      return;
    }
    if (text.startsWith("ERROR:")) {
      Serial.printf("[BACKEND ERROR] %s\n", text.substring(6).c_str());
      setAiResponding(false);
      return;
    }
    if (text == "VOICE_DONE") {
      setAiResponding(false);
      setVoiceState(IDLE);
      logVoice("Ready");
      return;
    }
    if (text == "AUDIO_START") {
      waitingForAudioSize = true;
      expectedAudioBytes = 0;
      receivedAudioBytes = 0;
      speakerHasOddByte = false;
      speakerI2sWrittenBytes = 0;
      speakerI2sWriteErrors = 0;
      i2s_zero_dma_buffer(I2S_NUM_1);
      prepareSpeakerForPlayback();
      setAiResponding(true);
      setVoiceState(PLAYING);
      Serial.println("[SPEAKER] Receiving TTS audio");
      playSpeakerDiagnosticTone();
      return;
    }
    if (text == "AUDIO_END") {
      Serial.printf("[SPEAKER] TTS stream ended: received=%d i2s_written=%u write_errors=%lu\n",
                    receivedAudioBytes, static_cast<unsigned>(speakerI2sWrittenBytes), speakerI2sWriteErrors);
      return;
    }
    if (waitingForAudioSize) {
      expectedAudioBytes = text.toInt();
      waitingForAudioSize = false;
      Serial.printf("[SPEAKER] Expected TTS bytes: %d\n", expectedAudioBytes);
      return;
    }
    if (text == "PONG") return;
    Serial.printf("[BACKEND] %s\n", text.c_str());
    return;
  }

  if (type == WStype_BIN && voiceState == PLAYING) {
    playPcmBytes(payload, length);
    receivedAudioBytes += length;
    if (expectedAudioBytes > 0 && receivedAudioBytes >= expectedAudioBytes) {
      Serial.println("[SPEAKER] Finished playing received PCM");
      setVoiceState(PROCESSING);  // VOICE_DONE switches to Ready.
    }
  }
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
  pinMode(BACKEND_LED_PIN, OUTPUT);
  pinMode(AI_RESPONSE_LED_PIN, OUTPUT);
  setBackendConnected(false);
  setAiResponding(false);
  setVoiceState(DISCONNECTED);

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  lcd.init();
  lcd.backlight();
  showLcdStatus("AI Home", "Starting...");

  setupMicrophone();
  setupSpeaker();
  connectWifi();
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/voice");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  logVoice("Voice agent starting");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  webSocket.loop();
  updateLcdReply();

  // One rising edge equals one touch. A second touch stops manually; otherwise
  // speech silence is detected only after the requested 8-second minimum.
  const bool touchDetected = digitalRead(TOUCH_SENSOR_PIN) == HIGH;
  if (touchDetected && !previousTouchState && millis() - previousTouchEvent > DEBOUNCE_MS) {
    previousTouchEvent = millis();
    if (voiceState == IDLE) beginRecording();
    else if (voiceState == RECORDING) stopRecording("manual touch");
  }
  previousTouchState = touchDetected;

  if (voiceState == RECORDING) sendMicrophoneFrame();
  if (voiceState == PROCESSING && millis() - processStartedAt >= PROCESS_TIMEOUT_MS) {
    logVoice("Backend response timeout");
    setAiResponding(false);
    setVoiceState(IDLE);
    showLcdStatus("Response timeout", "Try again");
  }
  delay(1);
}
