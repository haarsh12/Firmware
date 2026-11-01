import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../models/home_snapshot.dart';

class BackendService {
  BackendService({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Future<HomeSnapshot> loadSnapshot() async {
    final results = await Future.wait([
      _getJson('/health'),
      _getJson('/app/sensors'),
    ]);
    return HomeSnapshot.fromJson(results[0], results[1]);
  }

  Future<void> setRelay(String device, bool state) async {
    final response = await _client
        .post(
          ApiConfig.httpUri('/app/relay'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'device': device, 'state': state}),
        )
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != HttpStatus.ok) {
      final body = _decode(response.body);
      throw BackendException(body['detail']?.toString() ?? 'Relay command failed (${response.statusCode}).');
    }
  }

  Future<Map<String, dynamic>> _getJson(String path) async {
    final response = await _client.get(ApiConfig.httpUri(path)).timeout(const Duration(seconds: 8));
    if (response.statusCode != HttpStatus.ok) {
      throw BackendException('Backend returned ${response.statusCode}.');
    }
    return _decode(response.body);
  }

  Map<String, dynamic> _decode(String source) {
    final value = jsonDecode(source);
    if (value is! Map) throw const BackendException('Backend sent an invalid response.');
    return Map<String, dynamic>.from(value);
  }

  void dispose() => _client.close();
}

class BackendException implements Exception {
  const BackendException(this.message);
  final String message;
  @override
  String toString() => message;
}
