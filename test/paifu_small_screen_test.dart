// 좁은 세로 화면에서 패보 재생 화면이 넘치지 않는지(11-23).
// 손패 없는 판(r20_143236)은 패널에 "시작 손패 입력" 단추가 더 붙고, 리뷰가 없어 패널 높이 상한 + 스크롤이 안 걸려
// 400×800 · 380×800 에서 패널 Column 이 아래로 37px 넘쳤다. 묶어 둔 예시 전부(assets/paifu · assets/paifu_h3)를
// 두 크기로 띄워 요약 → 재생 화면 → 모든 걸음을 넘기며 레이아웃 오류가 없는지 본다.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 엔진 참고값은 끝나지 않는 것으로(레이아웃만 본다).
Future<PaifuReview> _never(Paifu p) => Completer<PaifuReview>().future;

List<File> _assets() => [
      for (final dir in ['assets/paifu', 'assets/paifu_h3'])
        ...(Directory(dir).listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
          ..sort((a, b) => a.path.compareTo(b.path))),
    ];

Paifu _load(String path) => Paifu.fromJson(jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>);

/// [body] 동안 난 Flutter 오류(넘침 포함)를 모아 돌려준다.
Future<List<String>> _collectErrors(Future<void> Function() body) async {
  final errors = <String>[];
  final old = FlutterError.onError;
  FlutterError.onError = (d) => errors.add(d.toString());
  try {
    await body();
  } finally {
    FlutterError.onError = old;
  }
  return errors;
}

Future<void> _pumpScreen(WidgetTester tester, Paifu p, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p, engineReview: _never)));
  await tester.pump();
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('예시 패보 22판이 있다(assets/paifu 11 + assets/paifu_h3 11)', () {
    expect(_assets().length, 22);
  });

  for (final size in const [Size(400, 800), Size(380, 800)]) {
    final tag = '${size.width.toInt()}×${size.height.toInt()}';
    for (final f in _assets()) {
      final name = f.uri.pathSegments.last;
      testWidgets('$tag $name: 요약 · 재생 화면 모든 걸음에서 넘침 없음', (tester) async {
        final p = _load(f.path);
        final errors = await _collectErrors(() async {
          await _pumpScreen(tester, p, size);
          final summary = find.byKey(const ValueKey('paifu-summary-play'));
          if (summary.evaluate().isNotEmpty) {
            await tester.ensureVisible(summary);
            await tester.tap(summary);
            await tester.pump();
          }
          expect(find.byKey(const ValueKey('paifu-now')), findsOneWidget);
          for (var i = 0; i <= p.events.length; i++) {
            await tester.tap(find.byKey(const ValueKey('paifu-next')), warnIfMissed: false);
            await tester.pump();
          }
        });
        expect(errors, isEmpty);
      });
    }
  }

  group('손패 없는 판 r20', () {
    final p = _load('assets/paifu/r20_143236.json');

    testWidgets('400×800: 패널 위 칸이 스크롤되어 시작 손패 입력 단추에 닿고, 사건 목록도 남는다', (tester) async {
      expect(p.hasHeroHands, isFalse);
      final errors = await _collectErrors(() async {
        await _pumpScreen(tester, p, const Size(400, 800));
        final scroll = find.byKey(const ValueKey('paifu-panel-scroll'));
        expect(scroll, findsOneWidget);
        expect(tester.state<ScrollableState>(find.descendant(of: scroll, matching: find.byType(Scrollable))).position.maxScrollExtent,
            greaterThan(0));
        await tester.ensureVisible(find.byKey(const ValueKey('paifu-start-hand')));
        await tester.pump();
        expect(tester.getRect(find.byKey(const ValueKey('paifu-start-hand'))).bottom, lessThanOrEqualTo(800));
        // 사건 목록은 적어도 두 줄(40px × 2).
        final log = find.byWidgetPredicate((w) => w is ListView && w.controller != null);
        expect(tester.getSize(log).height, greaterThanOrEqualTo(80));
      });
      expect(errors, isEmpty);
    });

    testWidgets('1280×800 가로: 다 들어가 위 칸은 스크롤이 안 생긴다(넓은 화면 모양 그대로)', (tester) async {
      final errors = await _collectErrors(() async {
        await _pumpScreen(tester, p, const Size(1280, 800));
        final scroll = find.byKey(const ValueKey('paifu-panel-scroll'));
        expect(tester.state<ScrollableState>(find.descendant(of: scroll, matching: find.byType(Scrollable))).position.maxScrollExtent,
            0);
      });
      expect(errors, isEmpty);
    });
  });
}
