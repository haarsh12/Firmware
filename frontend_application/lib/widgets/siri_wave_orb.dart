import 'dart:math' as math;

import 'package:flutter/material.dart';

class SiriWaveOrb extends StatefulWidget {
  const SiriWaveOrb({super.key, required this.active, required this.onTap});
  final bool active;
  final VoidCallback onTap;

  @override
  State<SiriWaveOrb> createState() => _SiriWaveOrbState();
}

class _SiriWaveOrbState extends State<SiriWaveOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat();
  @override
  void dispose() { _controller.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: widget.onTap,
    child: AnimatedBuilder(
      animation: _controller,
      builder: (_, __) => CustomPaint(size: const Size(210, 210), painter: _OrbPainter(_controller.value, widget.active)),
    ),
  );
}

class _OrbPainter extends CustomPainter {
  const _OrbPainter(this.value, this.active);
  final double value;
  final bool active;
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final base = active ? 67.0 : 55.0;
    final glow = Paint()..color = const Color(0xFF5B7CFA).withOpacity(active ? .16 : .08)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 28);
    canvas.drawCircle(center, base + 18, glow);
    final colors = active ? const [Color(0xFF5B7CFA), Color(0xFFB35CFF), Color(0xFF21C7C2), Color(0xFFFF709B)] : const [Color(0xFF2FBF71)];
    for (var index = 0; index < colors.length; index++) {
      final angle = value * math.pi * 2 + index * math.pi * 2 / colors.length;
      final offset = active ? Offset(math.cos(angle) * 16, math.sin(angle) * 16) : Offset.zero;
      final radius = active ? base * .58 : base;
      canvas.drawCircle(center + offset, radius, Paint()..color = colors[index].withOpacity(active ? .72 : 1));
    }
    canvas.drawCircle(center, active ? 39 : 42, Paint()..color = Colors.white.withOpacity(.78));
    final mic = TextPainter(text: TextSpan(text: active ? '◼' : '♩', style: TextStyle(color: active ? const Color(0xFF5B7CFA) : const Color(0xFF2FBF71), fontSize: 28, fontWeight: FontWeight.w700)), textDirection: TextDirection.ltr)..layout();
    mic.paint(canvas, center - Offset(mic.width / 2, mic.height / 2));
  }
  @override
  bool shouldRepaint(covariant _OrbPainter old) => old.value != value || old.active != active;
}
