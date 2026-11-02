import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:livekit_client/livekit_client.dart';

import '../config/api_config.dart';

enum VoicePhase { idle, listening, thinking, speaking, error }

class VoiceMessage {
  const VoiceMessage(this.text, this.isUser);
  final String text;
  final bool isUser;
}

/// LiveKit provides the mobile app with real-time microphone uplink and agent
/// audio downlink. The ESP32 `/ws/voice` route remains separate and unchanged.
class VoiceService {
  final _state = StreamController<VoiceUpdate>.broadcast();
  Room? _room;
  EventsListener<RoomEvent>? _listener;
  bool _initialised = false;
  bool _connecting = false;
  bool _stopRequested = false;
  final Set<String> _seenFinalMessages = <String>{};

  Stream<VoiceUpdate> get updates => _state.stream;

  Future<void> start() async {
    if (_connecting || _room?.connectionState == ConnectionState.connected) return;
    _connecting = true;
    _stopRequested = false;
    _state.add(const VoiceUpdate.phase(VoicePhase.thinking, 'Voice agent se connect ho raha hai...'));

    try {
      final credentials = await _requestToken();
      if (_stopRequested) return;
      final serverUrl = credentials['server_url']?.toString() ?? '';
      final token = credentials['participant_token']?.toString() ?? '';
      if (serverUrl.isEmpty || token.isEmpty) {
        throw StateError('Voice server ne incomplete credentials bheje.');
      }

      if (!_initialised) {
        await LiveKitClient.initialize();
        _initialised = true;
      }
      if (_stopRequested) return;
      await _disconnect();
      if (_stopRequested) return;

      final room = Room();
      final listener = room.createListener();
      listener
        ..on<RoomDisconnectedEvent>((event) {
          _room = null;
          _state.add(const VoiceUpdate.phase(VoicePhase.idle, 'Voice session band ho gaya. Tap karke dobara boliye.'));
        })
        ..on<TranscriptionEvent>(_onTranscription);

      _room = room;
      _listener = listener;
      await room.connect(serverUrl, token);
      if (_stopRequested) {
        await _disconnect();
        return;
      }
      final participant = room.localParticipant;
      if (participant == null) {
        throw StateError('Voice room mein microphone participant nahi mila.');
      }
      await participant.setMicrophoneEnabled(true);
      _state.add(const VoiceUpdate.phase(VoicePhase.listening, 'Sun raha hoon...'));
    } catch (error) {
      await _disconnect();
      _state.add(VoiceUpdate.phase(VoicePhase.error, _friendlyError(error)));
      rethrow;
    } finally {
      _connecting = false;
    }
  }

  Future<Map<String, dynamic>> _requestToken() async {
    final response = await http
        .post(
          ApiConfig.liveKitTokenUri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'participant_name': 'SVPCET Mobile User'}),
        )
        .timeout(const Duration(seconds: 15));
    Map<String, dynamic> payload = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) payload = decoded;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError(payload['detail']?.toString() ?? 'Voice token request failed (${response.statusCode}).');
    }
    return payload;
  }

  void _onTranscription(TranscriptionEvent event) {
    final text = event.segments.map((segment) => segment.text).join(' ').trim();
    if (text.isEmpty) return;
    final isAgent = event.participant.identity.contains('agent') ||
        event.participant.identity.contains('sahayak') ||
        event.participant.identity.contains('ghar');
    final isFinal = event.segments.any((segment) => segment.isFinal);

    if (isAgent) {
      _state.add(const VoiceUpdate.phase(VoicePhase.speaking, 'Jawab suna raha hoon...'));
    } else if (isFinal) {
      _state.add(const VoiceUpdate.phase(VoicePhase.thinking, 'Soch raha hoon...'));
    }
    if (!isFinal) return;

    final key = '${event.participant.identity}|$text';
    if (_seenFinalMessages.add(key)) {
      _state.add(VoiceUpdate.message(VoiceMessage(text, !isAgent)));
    }
  }

  Future<void> stop() async {
    _stopRequested = true;
    final participant = _room?.localParticipant;
    if (participant != null) await participant.setMicrophoneEnabled(false);
    await _disconnect();
    _state.add(const VoiceUpdate.phase(VoicePhase.idle, 'Tap karke Hindi mein boliye'));
  }

  Future<void> _disconnect() async {
    final listener = _listener;
    final room = _room;
    _listener = null;
    _room = null;
    _seenFinalMessages.clear();
    if (listener != null) await listener.dispose();
    if (room != null) {
      await room.disconnect();
      await room.dispose();
    }
  }

  String _friendlyError(Object error) {
    final message = '$error';
    if (message.contains('SocketException') || message.contains('ClientException')) {
      return 'Backend tak nahi pahunch pa raha. Phone aur laptop ka Wi-Fi/IP check karein.';
    }
    return message.replaceFirst('Bad state: ', '');
  }

  Future<void> dispose() async {
    await _disconnect();
    await _state.close();
  }
}

class VoiceUpdate {
  const VoiceUpdate.phase(this.phase, this.status) : message = null;
  const VoiceUpdate.message(this.message) : phase = null, status = null;
  final VoicePhase? phase;
  final String? status;
  final VoiceMessage? message;
}
