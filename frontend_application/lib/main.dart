import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'providers/home_provider.dart';
import 'providers/voice_provider.dart';
import 'screens/home_dashboard.dart';
import 'screens/voice_assistant_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(statusBarColor: Colors.transparent, statusBarIconBrightness: Brightness.dark));
  runApp(const SmartHomeApp());
}

class SmartHomeApp extends StatelessWidget {
  const SmartHomeApp({super.key});
  @override
  Widget build(BuildContext context) => MultiProvider(
    providers: [ChangeNotifierProvider(create: (_) => HomeProvider()..start()), ChangeNotifierProvider(create: (_) => VoiceProvider())],
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'SVPCET Smart Home',
      theme: ThemeData(useMaterial3: true, scaffoldBackgroundColor: const Color(0xFFF7F8FB), colorSchemeSeed: const Color(0xFF2FBF71)),
      home: const HomeShell(),
    ),
  );
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int index = 0;
  final pages = const [HomeDashboard(), VoiceAssistantScreen()];
  @override
  Widget build(BuildContext context) => Scaffold(
    body: IndexedStack(index: index, children: pages),
    bottomNavigationBar: NavigationBar(
      selectedIndex: index,
      onDestinationSelected: (value) => setState(() => index = value),
      height: 76,
      destinations: const [
        NavigationDestination(icon: Icon(Icons.grid_view_rounded), label: 'Home'),
        NavigationDestination(icon: Icon(Icons.graphic_eq_rounded), label: 'Voice'),
      ],
    ),
  );
}
