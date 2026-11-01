import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/home_snapshot.dart';
import '../providers/home_provider.dart';

class HomeDashboard extends StatelessWidget {
  const HomeDashboard({super.key});
  @override
  Widget build(BuildContext context) => SafeArea(child: Consumer<HomeProvider>(builder: (context, home, _) {
    final data = home.snapshot;
    return RefreshIndicator(
      onRefresh: home.refresh,
      child: ListView(padding: const EdgeInsets.fromLTRB(20, 22, 20, 28), children: [
        const Text('Smart Home', style: TextStyle(fontSize: 31, fontWeight: FontWeight.w800, color: Color(0xFF171A21))),
        const SizedBox(height: 4),
        const Text('SVPCET E&TC • Home automation', style: TextStyle(color: Color(0xFF757B86))),
        const SizedBox(height: 22),
        _ConnectionCard(data: data, loading: home.loading, error: home.error, onRefresh: home.refresh),
        const SizedBox(height: 26),
        const Text('Device controls', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _DeviceCard(title: 'Light', icon: Icons.lightbulb_rounded, isOn: data?.lightOn ?? false, busy: home.commandInProgress || data?.relayBoardConnected != true, onChanged: (state) => _set(context, 'light', state))),
          const SizedBox(width: 12),
          Expanded(child: _DeviceCard(title: 'Fan', icon: Icons.air_rounded, isOn: data?.fanOn ?? false, busy: home.commandInProgress || data?.relayBoardConnected != true, onChanged: (state) => _set(context, 'fan', state))),
        ]),
        const SizedBox(height: 28),
        const Text('Sensor readings', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        if (data == null) _EmptySensors(message: home.error ?? 'Waiting for backend data...') else _SensorGrid(data: data),
      ]),
    );
  }));

  Future<void> _set(BuildContext context, String device, bool state) async {
    final result = await context.read<HomeProvider>().setRelay(device, state);
    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result ? '${device == 'light' ? 'Light' : 'Fan'} ${state ? 'ON' : 'OFF'}' : context.read<HomeProvider>().error ?? 'Command failed')));
  }
}

class _ConnectionCard extends StatelessWidget {
  const _ConnectionCard({required this.data, required this.loading, required this.error, required this.onRefresh});
  final HomeSnapshot? data; final bool loading; final String? error; final Future<void> Function({bool silent}) onRefresh;
  @override
  Widget build(BuildContext context) {
    final online = data?.backendOnline == true; final relay = data?.relayBoardConnected == true;
    return Container(padding: const EdgeInsets.all(17), decoration: _box, child: Column(children: [
      _status(Icons.dns_rounded, 'Backend', online ? 'Running' : 'Offline', online), const Divider(height: 22),
      _status(Icons.memory_rounded, 'Relay ESP32', relay ? 'Connected' : 'Not connected', relay),
      if (error != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text(error!, style: const TextStyle(color: Color(0xFFC64040), fontSize: 12))),
      Align(alignment: Alignment.centerRight, child: TextButton.icon(onPressed: loading ? null : () => onRefresh(), icon: const Icon(Icons.refresh_rounded, size: 18), label: const Text('Refresh'))),
    ]));
  }
  static final _box = BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22), boxShadow: [BoxShadow(color: Colors.black.withOpacity(.05), blurRadius: 18)]);
  Widget _status(IconData icon, String label, String status, bool good) => Row(children: [Container(padding: const EdgeInsets.all(9), decoration: BoxDecoration(color: (good ? const Color(0xFF2FBF71) : const Color(0xFFE75252)).withOpacity(.12), borderRadius: BorderRadius.circular(12)), child: Icon(icon, color: good ? const Color(0xFF24935A) : const Color(0xFFD33F3F))), const SizedBox(width: 12), Expanded(child: Text(label, style: const TextStyle(fontWeight: FontWeight.w700))), Text(status, style: TextStyle(fontWeight: FontWeight.w700, color: good ? const Color(0xFF24935A) : const Color(0xFFD33F3F)))]);
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({required this.title, required this.icon, required this.isOn, required this.busy, required this.onChanged});
  final String title; final IconData icon; final bool isOn; final bool busy; final ValueChanged<bool> onChanged;
  @override
  Widget build(BuildContext context) => Container(padding: const EdgeInsets.all(17), decoration: _ConnectionCard._box, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Icon(icon, color: isOn ? const Color(0xFFFFB52E) : const Color(0xFF8A909A), size: 32), const SizedBox(height: 19), Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)), Text(isOn ? 'ON' : 'OFF', style: TextStyle(color: isOn ? const Color(0xFF24935A) : const Color(0xFF858B95), fontWeight: FontWeight.w700)), const SizedBox(height: 7), Switch.adaptive(value: isOn, onChanged: busy ? null : onChanged)]));
}

class _SensorGrid extends StatelessWidget {
  const _SensorGrid({required this.data}); final HomeSnapshot data;
  @override
  Widget build(BuildContext context) => GridView.count(crossAxisCount: 2, childAspectRatio: 1.35, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), crossAxisSpacing: 12, mainAxisSpacing: 12, children: [_card('Temperature', '${data.temperature.toStringAsFixed(1)} °C', Icons.thermostat_rounded, const Color(0xFFEF745D)), _card('Humidity', '${data.humidity.toStringAsFixed(1)}%', Icons.water_drop_rounded, const Color(0xFF4D8DFF)), _card('Air quality', data.gasDetected ? 'Gas detected' : 'Normal', Icons.air_rounded, data.gasDetected ? const Color(0xFFD64949) : const Color(0xFF2FBF71)), _card('Light level', '${data.ldr}', Icons.wb_sunny_rounded, const Color(0xFFFFB52E))]);
  Widget _card(String title, String value, IconData icon, Color color) => Container(padding: const EdgeInsets.all(15), decoration: _ConnectionCard._box.copyWith(borderRadius: BorderRadius.circular(19)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Icon(icon, color: color), const Spacer(), Text(title, style: const TextStyle(color: Color(0xFF737985), fontSize: 12)), const SizedBox(height: 3), Text(value, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16))]));
}
class _EmptySensors extends StatelessWidget { const _EmptySensors({required this.message}); final String message; @override Widget build(BuildContext context) => Container(padding: const EdgeInsets.all(24), decoration: _ConnectionCard._box, child: Text(message, textAlign: TextAlign.center, style: const TextStyle(color: Color(0xFF737985)))); }
