// 폰 배치(로비·테이블 화면 세로/가로·대국 시작 폼)를 실제 글꼴로 PNG 로 그린다(눈 확인용, 전체 테스트에는 안 들어감).
//   flutter test tool/render_phone_test.dart   → build/phone_*.png
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> _font(String family, List<String> files) async {
  final l = FontLoader(family);
  for (final f in files) {
    final b = File(f).readAsBytesSync();
    l.addFont(Future.value(ByteData.view(b.buffer)));
  }
  await l.load();
}

void main() {
  final root = GlobalKey();

  Future<void> shot(WidgetTester tester, String name) async {
    await tester.runAsync(() async {
      final b = root.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final img = await b.toImage(pixelRatio: 1);
      final png = await img.toByteData(format: ui.ImageByteFormat.png);
      File('build/phone_$name.png')
        ..createSync(recursive: true)
        ..writeAsBytesSync(png!.buffer.asUint8List());
    });
  }

  Future<void> setup(WidgetTester tester, Size size) async {
    // ignore: invalid_use_of_visible_for_testing_member
    SharedPreferences.setMockInitialValues({});
    await tester.runAsync(() async {
      // 테스트 기본 글꼴(FlutterTest)을 쓰는 글자(앱바 제목 등)도 네모가 아니게.
      for (final family in ['Roboto', 'FlutterTest']) {
        await _font(family, [r'C:\Windows\Fonts\malgun.ttf', r'C:\Windows\Fonts\malgunbd.ttf']);
      }
      await _font('MaterialIcons', [r'C:\Users\jjh7757\flutter\bin\cache\artifacts\material_fonts\materialicons-regular.otf']);
    });
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
    gameStore.history.clear();
  });

  testWidgets('render phone lobby + start form', (tester) async {
    await setup(tester, const Size(412, 915));
    await tester.pumpWidget(RepaintBoundary(key: root, child: const MahjongApp(loadSavedRules: false)));
    await tester.pumpAndSettle();
    await shot(tester, 'lobby');
    await tester.tap(find.byKey(const ValueKey('lobby-start')));
    await tester.pumpAndSettle();
    await shot(tester, 'start_form');
  });

  for (final (name, size) in const [('table', Size(412, 915)), ('table_small', Size(360, 640)), ('table_land', Size(915, 412))]) {
    testWidgets('render phone $name', (tester) async {
      await setup(tester, size);
      gameStore.start(const ['민수', '지현', '태호', '서연'], const GameSettings());
      gameStore.mutate((g) => g.declareRiichi(1));
      await tester.pumpWidget(RepaintBoundary(key: root, child: const MahjongApp(loadSavedRules: false)));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await shot(tester, name);
    });
  }
}
