import 'dart:async';

import 'package:flutter/foundation.dart';

import '../services/voice_service.dart';

class VoiceProvider extends ChangeNotifier {
  final VoiceService _service = VoiceService();
  final List<VoiceMessage> messages = [];
  VoicePhase phase = VoicePhase.idle;
  String status = 'Tap karke Hindi mein boliye';
  StreamSubscription? _subscription;

  VoiceProvider() {
    _subscription = _service.updates.listen((event) {
      if (event.message != null) {
        if (messages.isEmpty || messages.last.text != event.message!.text || messages.last.isUser != event.message!.isUser) {
          messages.add(event.message!);
        }
      }
      if (event.phase != null) phase = event.phase!;
      if (event.status != null) status = event.status!;
      notifyListeners();
    });
  }

  bool get isListening => phase == VoicePhase.listening;
  bool get isBusy => phase == VoicePhase.thinking || phase == VoicePhase.speaking;

  Future<void> toggle() async {
    try {
      if (isListening) {
        await _service.stop();
      } else if (!isBusy) {
        phase = VoicePhase.listening;
        status = 'Microphone connect ho raha hai...';
        notifyListeners();
        await _service.start();
      }
    } catch (error) {
      phase = VoicePhase.error;
      status = '$error';
      notifyListeners();
    }
  }

  void clear() {
    messages.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _service.dispose();
    super.dispose();
  }
}
