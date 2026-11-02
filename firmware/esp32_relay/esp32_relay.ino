/*
  ESP32 relay + sensor board for new_backend.

  Required Arduino libraries:
    - WebSockets by Markus Sattler / Links2004
    - ArduinoJson 6.x
    - DHT sensor library by Adafruit (only when ENABLE_DHT_SENSOR is 1)

  This replaces the old Bluetooth-only sketch. The relay board keeps a
  WebSocket at ws://BACKEND_HOST:BACKEND_PORT/ws/relay, so Xiaozhi and the
  Google/Vertex backend can both command the same physical relays.

  Current wiring from the original working board:
    touch 1 = GPIO 18, touch 2 = GPIO 19
    relay 1 (light) = GPIO 27, relay 2 (fan) = GPIO 26
    DHT11 data = GPIO 32

  MQ-2 support is included but disabled until the sensor is wired.  Set
  ENABLE_MQ2_SENSOR to 1 and select the two pins once it is installed.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#define ENABLE_DHT_SENSOR 1
#define ENABLE_MQ2_SENSOR 0
#define ENABLE_LDR_SENSOR 0
#if ENABLE_DHT_SENSOR
  #include <DHT.h>
#endif

// ---------- CHANGE THESE VALUES ----------
const char* WIFI_SSID = "Harsh's Galaxy A21s";
const char* WIFI_PASSWORD = "datachor";
// Current laptop Wi-Fi IPv4 as of the last backend configuration. Change this
// only if Windows reports a different Wi-Fi IPv4 address after reconnecting.
const char* BACKEND_HOST = "192.168.112.207";
const uint16_t BACKEND_PORT = 8000;
// ----------------------------------------

// Your original Bluetooth sketch used HIGH = ON, so this must remain false.
// Change it to true only if a future relay board behaves in reverse.
const bool RELAY_ACTIVE_LOW = false;

// Adjust pins to match your board. Avoid ESP32 boot-strapping pins.
constexpr uint8_t LIGHT_RELAY_PIN = 27;
constexpr uint8_t FAN_RELAY_PIN = 26;
constexpr uint8_t LIGHT_TOUCH_PIN = 18;
constexpr uint8_t FAN_TOUCH_PIN = 19;
// Change these only when the MQ-2 module is physically connected.
constexpr uint8_t MQ2_ANALOG_PIN = 34;
constexpr uint8_t MQ2_DIGITAL_PIN = 4;
constexpr uint8_t LDR_PIN = 35;
#if ENABLE_DHT_SENSOR
constexpr uint8_t DHT_PIN = 32;
constexpr uint8_t DHT_TYPE = DHT11;
DHT dht(DHT_PIN, DHT_TYPE);
#endif

constexpr unsigned long SENSOR_INTERVAL_MS = 5000;
constexpr unsigned long COMMAND_POLL_INTERVAL_MS = 350;
constexpr unsigned long DEBOUNCE_MS = 250;

WebSocketsClient webSocket;
bool lightState = false;
bool fanState = false;
bool previousLightTouch = LOW;
bool previousFanTouch = LOW;
unsigned long previousSensorPost = 0;
unsigned long previousCommandPoll = 0;
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
  Serial.printf("[WS] Status published: light=%s fan=%s\n", lightState ? "ON" : "OFF", fanState ? "ON" : "OFF");
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
  Serial.printf("[WS] Command received: %s -> %s\n", device, enabled ? "ON" : "OFF");
  publishRelayStatus();
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    Serial.printf("[WS] Relay backend connected: ws://%s:%u/ws/relay\n", BACKEND_HOST, BACKEND_PORT);
    publishRelayStatus();
    return;
  }
  if (type == WStype_DISCONNECTED) {
    Serial.println("[WS] Relay backend disconnected; retrying automatically");
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
  Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
  const unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected: %s, gateway: %s\n", WiFi.localIP().toString().c_str(), WiFi.gatewayIP().toString().c_str());
  } else {
    Serial.println("\n[WIFI] Connection timed out; will retry");
    WiFi.disconnect();
  }
}

void postSensorData() {
  if (WiFi.status() != WL_CONNECTED) return;

  StaticJsonDocument<256> document;
#if ENABLE_MQ2_SENSOR
  document["mqAnalog"] = analogRead(MQ2_ANALOG_PIN);
  document["mqDigital"] = digitalRead(MQ2_DIGITAL_PIN);
#else
  document["mqAnalog"] = 0;
  document["mqDigital"] = 0;
#endif
#if ENABLE_LDR_SENSOR
  document["ldr"] = analogRead(LDR_PIN);
#else
  document["ldr"] = 0;
#endif
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
  Serial.printf("[HTTP] Sensor update %d: %s\n", statusCode, body.c_str());
  http.end();
}

// Reliable fallback when a router/hotspot permits HTTP but drops the long-lived
// WebSocket upgrade. It also lets the backend mark this board as connected.
void pollRelayCommand() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.setTimeout(1200);
  http.begin(backendHttpUrl("/relay/next"));
  const int statusCode = http.GET();
  if (statusCode == HTTP_CODE_OK) {
    const String body = http.getString();
    StaticJsonDocument<256> document;
    const DeserializationError error = deserializeJson(document, body);
    if (!error && strcmp(document["type"] | "", "relay_command") == 0) {
      Serial.printf("[HTTP] Command received: %s -> %s\n", document["device"] | "", document["state"].as<bool>() ? "ON" : "OFF");
      handleRelayCommand(document);
    }
  } else if (statusCode > 0) {
    Serial.printf("[HTTP] Command poll failed: %d\n", statusCode);
  }
  http.end();
}

void handleTouchInputs() {
  const unsigned long now = millis();
  const bool lightTouch = digitalRead(LIGHT_TOUCH_PIN);
  const bool fanTouch = digitalRead(FAN_TOUCH_PIN);

  // The original touch board outputs HIGH while touched.
  if (lightTouch == HIGH && previousLightTouch == LOW && now - previousLightPress > DEBOUNCE_MS) {
    previousLightPress = now;
    Serial.println("[TOUCH] Light touch detected");
    setLight(!lightState);
    publishRelayStatus();
  }
  if (fanTouch == HIGH && previousFanTouch == LOW && now - previousFanPress > DEBOUNCE_MS) {
    previousFanPress = now;
    Serial.println("[TOUCH] Fan touch detected");
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
  pinMode(LIGHT_TOUCH_PIN, INPUT);
  pinMode(FAN_TOUCH_PIN, INPUT);
#if ENABLE_MQ2_SENSOR
  pinMode(MQ2_DIGITAL_PIN, INPUT);
#endif
  setLight(false);
  setFan(false);
#if ENABLE_DHT_SENSOR
  dht.begin();
#endif

  Serial.println("[BOOT] Smart-home relay board starting");
  Serial.println("[BOOT] Relay 1=light GPIO27, Relay 2=fan GPIO26, DHT11 GPIO32");
  Serial.printf("[BOOT] MQ-2 enabled=%s, LDR enabled=%s\n", ENABLE_MQ2_SENSOR ? "yes" : "no", ENABLE_LDR_SENSOR ? "yes" : "no");

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
  if (millis() - previousCommandPoll >= COMMAND_POLL_INTERVAL_MS) {
    previousCommandPoll = millis();
    pollRelayCommand();
  }
  delay(5);
}
