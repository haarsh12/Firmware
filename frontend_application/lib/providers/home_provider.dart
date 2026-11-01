import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/home_snapshot.dart';
import '../services/backend_service.dart';

class HomeProvider extends ChangeNotifier {
  HomeProvider({BackendService? service}) : _service = service ?? BackendService();
  final BackendService _service;
  Timer? _timer;
  HomeSnapshot? snapshot;
  String? error;
  bool loading = false;
  bool commandInProgress = false;

  Future<void> start() async {
    await refresh();
    _timer ??= Timer.periodic(const Duration(seconds: 6), (_) => refresh(silent: true));
  }

  Future<void> refresh({bool silent = false}) async {
    if (loading) return;
    loading = true;
    if (!silent) notifyListeners();
    try {
      snapshot = await _service.loadSnapshot();
      error = null;
    } catch (exception) {
      error = 'Backend unavailable. Check Wi-Fi and laptop IP.';
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<bool> setRelay(String device, bool state) async {
    commandInProgress = true;
    error = null;
    notifyListeners();
    try {
      await _service.setRelay(device, state);
      await refresh(silent: true);
      return true;
    } on BackendException catch (exception) {
      error = exception.message;
      return false;
    } catch (_) {
      error = 'Unable to send the command.';
      return false;
    } finally {
      commandInProgress = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _service.dispose();
    super.dispose();
  }
}
