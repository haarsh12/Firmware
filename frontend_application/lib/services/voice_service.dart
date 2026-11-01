import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_sound/flutter_sound.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/api_config.dart';

enum VoicePhase { idle, listening, thinking, speaking, error }

class VoiceMessage {
  const VoiceMessage(this.text, this.isUser);
  final String text;
  final bool isUser;
}

/// Uses exactly the backend's existing /ws/voice 16 kHz PCM protocol.
class VoiceService {
  final AudioRecorder _recorder = AudioRecorder();
  final FlutterSoundPlayer _player = FlutterSoundPlayer();
  WebSocketChannel? _channel;
  StreamSubscription? _socketSubscription;
  StreamSubscription<Uint8List>? _recordSubscription;
  final _state = StreamController<VoiceUpdate>.broadcast();
  bool _playerReady = false;
  bool _expectingAudio = false;
  int _audioExpected = 0;
  int _audioReceived = 0;

  Stream<VoiceUpdate> get updates => _state.stream;

  Future<void> start() async {
    if (_channel != null) return;
    if (!await _recorder.hasPermission()) {
      throw StateError('Microphone permission is required for voice chat.');
    }
    if (!_playerReady) {
      await _player.openPlayer();
      _playerReady = true;
    }
    _channel = WebSocketChannel.connect(ApiConfig.voiceUri());
    _socketSubscription = _channel!.stream.listen(_onSocketData, onError: _onSocketError, onDone: _onSocketDone);
    _channel!.sink.add('START');
    final audio = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));
    _recordSubscription = audio.listen((frame) => _channel?.sink.add(frame));
    _state.add(const VoiceUpdate.phase(VoicePhase.listening, 'Sun raha hoon...'));
  }

  Future<void> stop() async {
    await _recordSubscription?.cancel();
    _recordSubscription = null;
    if (await _recorder.isRecording()) await _recorder.stop();
    _channel?.sink.add('STOP');
    _state.add(const VoiceUpdate.phase(VoicePhase.thinking, 'Soch raha hoon...'));
  }

  void _onSocketData(dynamic event) {
    if (event is List<int>) {
      if (_expectingAudio) {
        _audioReceived += event.length;
        _player.feedUint8FromStream(Uint8List.fromList(event));
      }
      return;
    }
    final text = '$event';
    if (text == 'AUDIO_START') {
      _expectingAudio = true;
      _audioExpected = 0;
      _audioReceived = 0;
      _player.startPlayerFromStream(codec: Codec.pcm16, numChannels: 1, sampleRate: 16000, interleaved: true, bufferSize: 1024);
      _state.add(const VoiceUpdate.phase(VoicePhase.speaking, 'Jawab suna raha hoon...'));
      return;
    }
    if (_expectingAudio && _audioExpected == 0 && int.tryParse(text) != null) {
      _audioExpected = int.parse(text);
      return;
    }
    if (text == 'AUDIO_END') {
      _expectingAudio = false;
      _player.stopPlayer();
      return;
    }
    if (text == 'VOICE_DONE') {
      _state.add(const VoiceUpdate.phase(VoicePhase.idle, 'Tap karke phir boliye'));
      _closeSocket();
      return;
    }
    if (text.startsWith('TRANSCRIPT:') || text.startsWith('FINAL:')) {
      _state.add(VoiceUpdate.message(VoiceMessage(text.substring(text.indexOf(':') + 1), true)));
    } else if (text.startsWith('REPLY:')) {
      _state.add(VoiceUpdate.message(VoiceMessage(text.substring(6), false)));
    } else if (text.startsWith('STATUS:')) {
      _state.add(VoiceUpdate.phase(VoicePhase.thinking, text.substring(7)));
    } else if (text.startsWith('ERROR:')) {
      _state.add(VoiceUpdate.phase(VoicePhase.error, text.substring(6)));
    }
  }

  void _onSocketError(Object error) => _state.add(VoiceUpdate.phase(VoicePhase.error, 'Voice connection failed.'));
  void _onSocketDone() => _channel = null;

  Future<void> _closeSocket() async {
    await _socketSubscription?.cancel();
    _socketSubscription = null;
    await _channel?.sink.close();
    _channel = null;
  }

  Future<void> dispose() async {
    await _recordSubscription?.cancel();
    await _recorder.dispose();
    await _closeSocket();
    if (_playerReady) await _player.closePlayer();
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
