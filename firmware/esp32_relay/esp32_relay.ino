/*
  ESP32 relay + sensor board for new_backend.

  Required Arduino libraries:
    - WebSockets by Markus Sattler / Links2004
    - ArduinoJson 6.x
    - DHT sensor library by Adafruit (only when ENABLE_DHT_SENSOR is 1)

  Set Wi-Fi and backend address below before flashing.  The relay board keeps a
  WebSocket at ws://BACKEND_HOST:BACKEND_PORT/ws/relay and sends HTTP sensor
  updates to /sensors/data.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#define ENABLE_DHT_SENSOR 1
#if ENABLE_DHT_SENSOR
  #include <DHT.h>
#endif

// ---------- CHANGE THESE VALUES ----------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_HOST = "192.168.1.100";
const uint16_t BACKEND_PORT = 8000;
// ----------------------------------------

// Set true for relay boards where LOW energizes the relay.
const bool RELAY_ACTIVE_LOW = true;

// Adjust pins to match your board. Avoid ESP32 boot-strapping pins.
constexpr uint8_t LIGHT_RELAY_PIN = 5;
constexpr uint8_t FAN_RELAY_PIN = 21;
constexpr uint8_t LIGHT_TOUCH_PIN = 18;
constexpr uint8_t FAN_TOUCH_PIN = 19;
constexpr uint8_t MQ2_ANALOG_PIN = 34;
constexpr uint8_t MQ2_DIGITAL_PIN = 4;
constexpr uint8_t LDR_PIN = 35;
#if ENABLE_DHT_SENSOR
constexpr uint8_t DHT_PIN = 23;
constexpr uint8_t DHT_TYPE = DHT11;
DHT dht(DHT_PIN, DHT_TYPE);
#endif

constexpr unsigned long SENSOR_INTERVAL_MS = 5000;
constexpr unsigned long DEBOUNCE_MS = 250;

WebSocketsClient webSocket;
bool lightState = false;
bool fanState = false;
bool previousLightTouch = HIGH;
bool previousFanTouch = HIGH;
unsigned long previousSensorPost = 0;
unsigned long previousLightPress = 0;
unsigned long previousFanPress = 0;

String backendHttpUrl(const char* path) {
  return String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT) + path;
}

void writeRelay(uint8_t pin, bool enabled) {
  const uint8_t level = (enabled == RELAY_ACTIVE_LOW) ? LOW : HIGH;
  digitalWrite(pin, level);
}

void setLight(bool enabled) {
  lightState = enabled;
  writeRelay(LIGHT_RELAY_PIN, enabled);
  Serial.printf("[RELAY] light=%s\n", enabled ? "on" : "off");
}

void setFan(bool enabled) {
  fanState = enabled;
  writeRelay(FAN_RELAY_PIN, enabled);
  Serial.printf("[RELAY] fan=%s\n", enabled ? "on" : "off");
}

void publishRelayStatus() {
  if (!webSocket.isConnected()) return;
  StaticJsonDocument<128> document;
  document["type"] = "relay_status";
  document["light"] = lightState;
  document["fan"] = fanState;
  String payload;
  serializeJson(document, payload);
  webSocket.sendTXT(payload);
}

void handleRelayCommand(const JsonDocument& document) {
  const char* device = document["device"] | "";
  if (!document.containsKey("state")) return;
  const bool enabled = document["state"].as<bool>();
  if (strcmp(device, "light") == 0) {
    setLight(enabled);
  } else if (strcmp(device, "fan") == 0) {
    setFan(enabled);
  } else {
    return;
  }
  publishRelayStatus();
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    Serial.println("[WS] Relay backend connected");
    publishRelayStatus();
    return;
  }
  if (type != WStype_TEXT) return;

  StaticJsonDocument<256> document;
  const DeserializationError error = deserializeJson(document, payload, length);
  if (error) {
    Serial.printf("[WS] Invalid JSON: %s\n", error.c_str());
    return;
  }
  if (strcmp(document["type"] | "", "relay_command") == 0) {
    handleRelayCommand(document);
  } else if (strcmp(document["type"] | "", "relay_status") == 0) {
    // The backend sends the current state when the board first connects.
    if (document.containsKey("light")) setLight(document["light"].as<bool>());
    if (document.containsKey("fan")) setFan(document["fan"].as<bool>());
    publishRelayStatus();
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

void postSensorData() {
  if (WiFi.status() != WL_CONNECTED) return;

  StaticJsonDocument<256> document;
  document["mqAnalog"] = analogRead(MQ2_ANALOG_PIN);
  document["mqDigital"] = digitalRead(MQ2_DIGITAL_PIN);
  document["ldr"] = analogRead(LDR_PIN);
#if ENABLE_DHT_SENSOR
  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();
  document["temperature"] = isnan(temperature) ? 0.0 : temperature;
  document["humidity"] = isnan(humidity) ? 0.0 : humidity;
#else
  document["temperature"] = 0.0;
  document["humidity"] = 0.0;
#endif

  String body;
  serializeJson(document, body);
  HTTPClient http;
  http.begin(backendHttpUrl("/sensors/data"));
  http.addHeader("Content-Type", "application/json");
  const int statusCode = http.POST(body);
  Serial.printf("[HTTP] sensor update: %d\n", statusCode);
  http.end();
}

void handleTouchInputs() {
  const unsigned long now = millis();
  const bool lightTouch = digitalRead(LIGHT_TOUCH_PIN);
  const bool fanTouch = digitalRead(FAN_TOUCH_PIN);

  if (lightTouch == LOW && previousLightTouch == HIGH && now - previousLightPress > DEBOUNCE_MS) {
    previousLightPress = now;
    setLight(!lightState);
    publishRelayStatus();
  }
  if (fanTouch == LOW && previousFanTouch == HIGH && now - previousFanPress > DEBOUNCE_MS) {
    previousFanPress = now;
    setFan(!fanState);
    publishRelayStatus();
  }
  previousLightTouch = lightTouch;
  previousFanTouch = fanTouch;
}

void setup() {
  Serial.begin(115200);
  pinMode(LIGHT_RELAY_PIN, OUTPUT);
  pinMode(FAN_RELAY_PIN, OUTPUT);
  pinMode(LIGHT_TOUCH_PIN, INPUT_PULLUP);
  pinMode(FAN_TOUCH_PIN, INPUT_PULLUP);
  pinMode(MQ2_DIGITAL_PIN, INPUT);
  setLight(false);
  setFan(false);
#if ENABLE_DHT_SENSOR
  dht.begin();
#endif

  connectWifi();
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/relay");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  webSocket.loop();
  handleTouchInputs();
  if (millis() - previousSensorPost >= SENSOR_INTERVAL_MS) {
    previousSensorPost = millis();
    postSensorData();
  }
  delay(5);
}
