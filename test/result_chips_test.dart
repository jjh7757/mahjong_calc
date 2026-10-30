// 결과 화면 상황 칩: 누르면 그 자리에서 다시 계산한다(2026-10-29).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  // 리치·탕야오·핑후·이페코 4판 30부 론 7700 → 더블 리치면 5판 만관 8000.
  final hand = Hand.parse('223344m567p67s55s 8s');
  final sit = Situation(
    isTsumo: false,
    seatWind: Tiles.south,
    riichi: true,
    doraIndicators: [Tiles.parse('1z')],
    uraIndicators: [Tiles.parse('1z')],
  );

  Future<void> pumpResult(WidgetTester tester, {required bool kiosk}) async {
    SharedPreferences.setMockInitialValues({'voice.result': false});
    tester.view.physicalSize = kiosk ? const Size(1280, 800) : const Size(400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final r = calculate(hand, sit);
    await tester.pumpWidget(MaterialApp(
      home: ResultScreen(result: r, hand: hand, situation: sit, isTsumo: false, seatWind: Tiles.south),
    ));
    await tester.pump();
  }

  testWidgets('키오스크: 더블 리치 칩을 누르면 더블 리치 2판으로 바로 다시 계산한다', (tester) async {
    await pumpResult(tester, kiosk: true);
    expect(find.byKey(const ValueKey('result-chips')), findsOneWidget);
    expect(find.text('더블 리치'), findsOneWidget); // 칩만(역 줄엔 아직 없음)
    expect(find.text('리치'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('result-chip-double-riichi')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    // 역 줄에 "더블 리치" 가 생기고(칩 + 역 줄 = 2), 점수는 8000.
    expect(find.text('더블 리치'), findsNWidgets(2));
    expect(find.textContaining('8000', findRichText: true), findsWidgets);
    expect(find.textContaining('더블 리치(으)로 다시 계산'), findsOneWidget);

    // 다시 누르면 리치도 꺼져 리치 없는 3판(탕야오·핑후·이페코) → 3900.
    await tester.tap(find.byKey(const ValueKey('result-chip-double-riichi')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('더블 리치'), findsOneWidget);
    expect(find.textContaining('3900', findRichText: true), findsWidgets);
  });

  testWidgets('칩으로 고치면 onSituationChanged 로 알린다(기록 label.json 이 계산과 같아지게)', (tester) async {
    Situation? got;
    SharedPreferences.setMockInitialValues({'voice.result': false});
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: ResultScreen(
        result: calculate(hand, sit),
        hand: hand,
        situation: sit,
        isTsumo: false,
        seatWind: Tiles.south,
        onSituationChanged: (s) => got = s,
      ),
    ));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('result-chip-riichi'))); // 리치 끔
    await tester.pump();
    expect(got, isNotNull);
    expect(got!.riichi, isFalse);
  });

  testWidgets('키오스크: 일발 칩은 리치가 없으면 리치도 같이 켠다', (tester) async {
    await pumpResult(tester, kiosk: true);
    await tester.tap(find.byKey(const ValueKey('result-chip-riichi'))); // 리치 끔 → 3판
    await tester.pump();
    expect(find.textContaining('3900', findRichText: true), findsWidgets);
    await tester.tap(find.byKey(const ValueKey('result-chip-ippatsu'))); // 일발 켬 → 리치+일발 5판 만관
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('일발'), findsNWidgets(2));
    expect(find.textContaining('8000', findRichText: true), findsWidgets);
  });

  testWidgets('폰: 상황 고치기 칩이 있고 하저로어를 켜면 5판 만관', (tester) async {
    await pumpResult(tester, kiosk: false);
    expect(find.text('상황 고치기'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const ValueKey('result-chip-last-tile')));
    await tester.tap(find.byKey(const ValueKey('result-chip-last-tile')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('하저로어'), findsNWidgets(2));
    expect(find.textContaining('8000'), findsWidgets);
  });
}
