# Flutter Smart Home App Setup Guide

## ✅ Dependencies Installed
The following dependencies have been successfully added to `pubspec.yaml`:
- `provider: ^6.1.1` - State management
- `http: ^1.1.0` - HTTP requests to ESP32
- `shared_preferences: ^2.2.2` - Local data storage
- `intl: ^0.19.0` - Date/time formatting

## 🚀 Quick Start

### 1. Verify Installation
```bash
cd frontend_application
flutter pub get
flutter doctor
```

### 2. Configure ESP32 IP Address
Edit `lib/services/esp32_api_service.dart`:
```dart
static const String _baseUrl = 'http://YOUR_ESP32_IP'; // Change this
```

**Default IP**: `192.168.1.100`

### 3. Run the App
```bash
# For Android emulator/device
flutter run

# For web (testing only)
flutter run -d web

# For Windows desktop
flutter run -d windows
```

## 📱 App Features

### Home Dashboard
- **Device Controls**: Light and Fan ON/OFF buttons
- **Sensor Monitoring**: Temperature, Humidity, Gas, Light levels
- **Real-time Updates**: Auto-refresh every 5 seconds
- **Connection Status**: ESP32 connectivity indicator
- **History**: Sensor data history with timestamps

### Premium Design
- **Neomorphic UI**: Modern white design with soft shadows
- **Smooth Animations**: Button press and state change animations
- **Responsive Layout**: Works on phones, tablets, and desktop
- **Dark/Light Theme**: Automatic theme switching

## 🔧 ESP32 Configuration

### Required ESP32 Endpoints
Your ESP32 should provide these HTTP endpoints:

```
GET /status          - Device status (light, fan, wifi, uptime)
GET /sensor          - Sensor readings (temperature, humidity, gas, ldr)
GET /light/on        - Turn light ON
GET /light/off       - Turn light OFF
GET /fan/on          - Turn fan ON
GET /fan/off         - Turn fan OFF
```

### Example ESP32 Response Format
```json
// /sensor endpoint
{
  "temperature": 25.6,
  "humidity": 60.2,
  "mqAnalog": 450,
  "mqDigital": 0,
  "ldr": 1200
}

// /status endpoint
{
  "light": true,
  "fan": false,
  "wifi_connected": true,
  "bluetooth_connected": false,
  "uptime": 3600
}
```

## 🛠️ Troubleshooting

### Common Issues

1. **"Device offline" Error**
   - Check ESP32 IP address in `esp32_api_service.dart`
   - Ensure ESP32 and phone are on same WiFi network
   - Test ESP32 endpoints in browser: `http://ESP32_IP/status`

2. **Build Errors**
   ```bash
   flutter clean
   flutter pub get
   flutter run
   ```

3. **Network Permission (Android)**
   - Add to `android/app/src/main/AndroidManifest.xml`:
   ```xml
   <uses-permission android:name="android.permission.INTERNET" />
   ```

4. **HTTP Cleartext Traffic (Android)**
   - Add to `android/app/src/main/AndroidManifest.xml` in `<application>`:
   ```xml
   android:usesCleartextTraffic="true"
   ```

### Testing Without ESP32
The app includes mock data and error handling, so you can test the UI even without a physical ESP32 device.

## 📂 Project Structure
```
frontend_application/
├── lib/
│   ├── main.dart                    # App entry point
│   ├── theme/app_theme.dart         # App theme configuration
│   ├── screens/home_dashboard.dart  # Main dashboard screen
│   ├── providers/sensor_provider.dart # State management
│   ├── services/
│   │   ├── esp32_api_service.dart   # ESP32 HTTP API client
│   │   └── history_storage_service.dart # Local data storage
│   ├── models/sensor_reading.dart   # Data models
│   └── widgets/                     # Custom UI components
│       ├── control_button.dart
│       ├── sensor_card.dart
│       └── history_tile.dart
└── pubspec.yaml                     # Dependencies
```

## 🎯 Next Steps

1. **Test the App**: Run `flutter run` and verify UI works
2. **Configure ESP32**: Update IP address in API service
3. **Test Integration**: Connect to your ESP32 device
4. **Customize**: Modify colors, add features, or integrate with voice pipeline

## 🔗 Integration with Voice Pipeline

This Flutter app is designed to work with the ESP32 Home Controller from the voice pipeline system. The voice commands processed by the backend will control the same devices that this app manages through direct HTTP calls.

**Voice Command Flow**:
ESP32 Voice Sender → FastAPI Backend → Gemini AI → ESP32 Home Controller ← Flutter App

Both the voice system and mobile app control the same ESP32 Home Controller device.