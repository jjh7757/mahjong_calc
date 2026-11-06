// 키오스크 결과 화면을 실제 글꼴(맑은 고딕)로 PNG 로 그린다(눈 확인용, 전체 테스트에는 안 들어감).
//   CASE=haneman|many|yakuman|fu|four OUT=build/x.png flutter test tool/render_result_kiosk_test.dart
//   CAUTION=표시패,울기 면 대국 중 자동 반영 카운트다운과 경고 줄까지 그린다.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
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
  testWidgets('render', (tester) async {
    // ignore: invalid_use_of_visible_for_testing_member
    SharedPreferences.setMockInitialValues({'voice.result': false});
    await tester.runAsync(() async {
      await _font('Roboto', [r'C:\Windows\Fonts\malgun.ttf', r'C:\Windows\Fonts\malgunbd.ttf']);
    });
    final out = Platform.environment['OUT'] ?? 'build/result_kiosk.png';
    final w = double.parse(Platform.environment['W'] ?? '1280');
    final h = double.parse(Platform.environment['H'] ?? '800');
    tester.view.physicalSize = Size(w, h);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final c = Platform.environment['CASE'] ?? 'haneman';
    final hand = switch (c) {
      'yakuman' => Hand.parse('555z666z777z123m4p 4p'),
      // 부수가 점수에 들어가는 손패: 백 암각 + 간짱 대기 → 기본 20 + 멘젠 론 10 + 8 + 2 = 40부.
      'fu' => Hand.parse('234m678p555z13s99m 2s'),
      _ => Hand.parse('223344m567p67s55s 8s'),
    };
    final sit = switch (c) {
      'yakuman' => Situation(isTsumo: false, seatWind: Tiles.south, doraIndicators: [Tiles.parse('3p')]),
      // 역 4줄(리치·탕야오·핑후·이페코): 16:9 에서 4줄째가 상황 칩에 안 가리는지.
      'four' => Situation(isTsumo: false, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('1z')]),
      'fu' => Situation(isTsumo: false, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('7p')]),
      'many' => Situation(
          isTsumo: true,
          seatWind: Tiles.south,
          riichi: true,
          ippatsu: true,
          doraIndicators: [Tiles.parse('1m'), Tiles.parse('4z')],
          uraIndicators: [Tiles.parse('4p'), Tiles.parse('1m')],
        ),
      _ => Situation(
          isTsumo: false,
          seatWind: Tiles.south,
          riichi: true,
          ippatsu: true,
          doraIndicators: [Tiles.parse('4z')],
          uraIndicators: [Tiles.parse('1m')],
        ),
    };
    final r = calculate(hand, sit);
    final key = GlobalKey();
    final caution = Platform.environment['CAUTION']?.split(',');
    if (caution != null) gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
    await tester.pumpWidget(RepaintBoundary(
      key: key,
      child: MaterialApp(debugShowCheckedModeBanner: false, home: ResultScreen(result: r, hand: hand, situation: sit, isTsumo: sit.isTsumo, gameSeat: caution == null ? null : 2, loser: caution == null ? null : 1, autoRecordAfter: caution == null ? null : const Duration(seconds: 600), autoCautions: caution ?? const [])),
    ));
    await tester.pump(const Duration(seconds: 5));
    await tester.runAsync(() async {
      for (final e in find.byType(Image).evaluate()) {
        await precacheImage((e.widget as Image).image, e);
      }
    });
    await tester.pump(const Duration(seconds: 1));
    await tester.runAsync(() async {
      final boundary = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      final img = await boundary.toImage();
      final png = await img.toByteData(format: ui.ImageByteFormat.png);
      File(out).writeAsBytesSync(png!.buffer.asUint8List());
    });
    await tester.pumpWidget(const SizedBox());
  });
}
