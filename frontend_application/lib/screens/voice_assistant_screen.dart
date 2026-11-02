import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/voice_provider.dart';
import '../services/voice_service.dart';
import '../widgets/siri_wave_orb.dart';

class VoiceAssistantScreen extends StatelessWidget {
  const VoiceAssistantScreen({super.key});
  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Consumer<VoiceProvider>(
        builder: (context, voice, _) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 22, 18, 8),
              child: Row(children: [
                const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Voice Sahayak', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: Color(0xFF171A21))),
                  SizedBox(height: 3), Text('Hindi voice assistant', style: TextStyle(color: Color(0xFF737985))),
                ])),
                IconButton(onPressed: voice.messages.isEmpty ? null : voice.clear, icon: const Icon(Icons.delete_outline_rounded)),
              ]),
            ),
            Expanded(
              child: voice.messages.isEmpty
                  ? const SizedBox()
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      itemCount: voice.messages.length,
                      itemBuilder: (_, index) {
                        final message = voice.messages[index];
                        return Align(
                          alignment: message.isUser ? Alignment.centerRight : Alignment.centerLeft,
                          child: Container(
                            constraints: const BoxConstraints(maxWidth: 300),
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 11),
                            decoration: BoxDecoration(color: message.isUser ? const Color(0xFF202635) : Colors.white, borderRadius: BorderRadius.circular(18), boxShadow: [BoxShadow(color: Colors.black.withOpacity(.04), blurRadius: 14)]),
                            child: Text(message.text, style: TextStyle(height: 1.35, color: message.isUser ? Colors.white : const Color(0xFF252A35))),
                          ),
                        );
                      },
                    ),
            ),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(24, 12, 24, 34),
              decoration: const BoxDecoration(color: Colors.white, borderRadius: BorderRadius.vertical(top: Radius.circular(34))),
              child: Column(children: [
                SiriWaveOrb(active: voice.isListening || voice.isBusy, onTap: voice.toggle),
                const SizedBox(height: 10),
                Text(voice.status, textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.w600, color: _statusColor(voice.phase))),
                const SizedBox(height: 6),
                Text(voice.isActive ? 'Tap the wave to stop this conversation' : 'Tap the wave to speak', style: const TextStyle(color: Color(0xFF8A909A))),
              ]),
            ),
          ],
        ),
      ),
    );
  }

  Color _statusColor(VoicePhase phase) => switch (phase) {
    VoicePhase.error => const Color(0xFFD64848),
    VoicePhase.listening => const Color(0xFF5B7CFA),
    VoicePhase.speaking => const Color(0xFF7B55D7),
    _ => const Color(0xFF2B8556),
  };
}
