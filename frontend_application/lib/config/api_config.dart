class ApiConfig {
  /// Override at build/run time, e.g.
  /// flutter run --dart-define=BACKEND_HOST=192.168.50.207
  static const String backendHost = String.fromEnvironment(
    'BACKEND_HOST',
    defaultValue: '192.168.50.207',
  );
  static const int backendPort = int.fromEnvironment('BACKEND_PORT', defaultValue: 8000);

  static String get httpBaseUrl => 'http://$backendHost:$backendPort';
  static String get websocketBaseUrl => 'ws://$backendHost:$backendPort';
  static Uri httpUri(String path) => Uri.parse('$httpBaseUrl$path');
  static Uri voiceUri() => Uri.parse('$websocketBaseUrl/ws/voice');
}
