import 'package:flutter/material.dart';

import 'game/game_store.dart';
import 'ui/game/settlement_screen.dart';
import 'ui/hand_editor.dart';
import 'ui/kiosk.dart';
import 'ui/kiosk_lobby.dart';
import 'ui/mount/mount_screen.dart';
import 'ui/settings_screen.dart';

void main() {
  runApp(const MahjongApp());
}

class MahjongApp extends StatefulWidget {
  /// 테스트에서 저장소를 건너뛰고 싶을 때 false.
  final bool loadSavedRules;
  const MahjongApp({super.key, this.loadSavedRules = true});

  @override
  State<MahjongApp> createState() => _MahjongAppState();
}

class _MahjongAppState extends State<MahjongApp> {
  final HandEditor editor = HandEditor();

  @override
  void initState() {
    super.initState();
    if (widget.loadSavedRules) {
      RulesStore.load().then(editor.setRules);
      gameStore.load();
    }
  }

  @override
  void dispose() {
    editor.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '마작 점수 계산기',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF2E7D32),
        useMaterial3: true,
      ),
      navigatorObservers: [gameRouteObserver],
      // 대국 중이면 테이블 화면, 대국이 없으면 로비가 첫 화면. 폰도 같은 흐름이고 배치만 폰용(2026-10-29, 전엔 폰 = 계산기).
      // 대국 중에도 테이블의 "홈" 으로 로비를 볼 수 있다(kioskLobbyFor).
      // 대국이 끝나면 첫 화면으로 돌아올 때 종료 화면을 띄운다(작혼식).
      home: GameEndWatcher(
        child: ListenableBuilder(
          listenable: Listenable.merge([gameStore, kioskLobbyFor]),
          builder: (context, _) {
            final g = gameStore.current;
            return g != null && kioskLobbyFor.value != g.id
                ? MountScreen(key: ValueKey('table-${g.id}'), editor: editor, isHome: true)
                : KioskLobby(editor: editor);
          },
        ),
      ),
    );
  }
}
