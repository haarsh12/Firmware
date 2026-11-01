class HomeSnapshot {
  const HomeSnapshot({
    required this.backendOnline,
    required this.relayBoardConnected,
    required this.lightOn,
    required this.fanOn,
    required this.temperature,
    required this.humidity,
    required this.mqAnalog,
    required this.mqDigital,
    required this.ldr,
    required this.updatedAt,
  });

  final bool backendOnline;
  final bool relayBoardConnected;
  final bool lightOn;
  final bool fanOn;
  final double temperature;
  final double humidity;
  final int mqAnalog;
  final int mqDigital;
  final int ldr;
  final DateTime updatedAt;

  factory HomeSnapshot.fromJson(Map<String, dynamic> health, Map<String, dynamic> state) {
    final sensors = Map<String, dynamic>.from(state['sensors'] as Map? ?? const {});
    final relays = Map<String, dynamic>.from(state['relays'] as Map? ?? const {});
    num number(Object? value) => value is num ? value : num.tryParse('$value') ?? 0;
    return HomeSnapshot(
      backendOnline: health['status'] == 'healthy' || health['status'] == 'online',
      relayBoardConnected: number(health['relay_board_connections']).toInt() > 0,
      lightOn: relays['light'] == true,
      fanOn: relays['fan'] == true,
      temperature: number(sensors['temperature']).toDouble(),
      humidity: number(sensors['humidity']).toDouble(),
      mqAnalog: number(sensors['mqAnalog']).toInt(),
      mqDigital: number(sensors['mqDigital']).toInt(),
      ldr: number(sensors['ldr']).toInt(),
      updatedAt: DateTime.now(),
    );
  }

  bool get gasDetected => mqDigital == 1;
}
