import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';

/// 상황 칩을 누르면 필요한 상태(쯔모·론·리치)로 함께 바뀌어 버튼을 덜 누른다.
void main() {
  group('상황 칩이 전제 조건을 같이 켠다', () {
    test('영상개화 → 쯔모, 창깡 → 론', () {
      final e = HandEditor();
      expect(e.isTsumo, isFalse);
      e.setRinshan(true);
      expect(e.isTsumo, isTrue);
      expect(e.rinshan, isTrue);
      e.setChankan(true);
      expect(e.isTsumo, isFalse);
      expect(e.chankan, isTrue);
      expect(e.rinshan, isFalse);
    });

    test('일발 → 리치', () {
      final e = HandEditor()..setIppatsu(true);
      expect(e.riichi, isTrue);
      expect(e.ippatsu, isTrue);
      e.setRiichi(false);
      expect(e.ippatsu, isFalse);
    });

    test('더블 리치 상태에서 일발은 리치를 바꾸지 않는다', () {
      final e = HandEditor()
        ..setDoubleRiichi(true)
        ..setIppatsu(true);
      expect(e.doubleRiichi, isTrue);
      expect(e.riichi, isFalse);
      expect(e.ippatsu, isTrue);
    });

    test('뒷도라 탭 → 리치, 리치를 끄면 손패 탭으로', () {
      final e = HandEditor()..setTarget(InputTarget.ura);
      expect(e.riichi, isTrue);
      expect(e.target, InputTarget.ura);
      expect(e.cannotAdd(Tiles.parse('1m')), isNull);
      e.setRiichi(false);
      expect(e.target, InputTarget.hand);
      expect(e.uraIndicators, isEmpty);
    });

    test('울었으면 일발·뒷도라는 켜지지 않는다', () {
      final e = HandEditor()..addMeld(Meld.pon(Tiles.white));
      e.setIppatsu(true);
      expect(e.riichi, isFalse);
      expect(e.ippatsu, isFalse);
      e.setTarget(InputTarget.ura);
      expect(e.target, InputTarget.hand);
    });
  });

  group('손패가 차면 도라 탭으로', () {
    test('14장째를 넣으면 도라 탭, 한 장 빼면 손패 탭', () {
      final e = HandEditor();
      for (final t in parseTiles('123m456p789s23m55p').tiles) {
        e.add(t);
      }
      expect(e.target, InputTarget.hand);
      e.add(Tiles.parse('4m'));
      expect(e.closed.length, 14);
      expect(e.target, InputTarget.dora);
      e.add(Tiles.parse('9p'));
      expect(e.doraIndicators, [Tiles.parse('9p')]);
      e.removeClosedAt(0);
      expect(e.target, InputTarget.hand);
    });

    test('울어서 손패가 차도 도라 탭', () {
      final e = HandEditor();
      for (final t in parseTiles('123m456p789s23m').tiles) {
        e.add(t);
      }
      e.addMeld(Meld.pon(Tiles.white));
      expect(e.maxClosed, 11);
      expect(e.target, InputTarget.dora);
    });

    test('뒷도라 탭에 있을 때 손패를 빼도 탭은 그대로', () {
      final e = HandEditor();
      for (final t in parseTiles('123m456p789s23m55p4m').tiles) {
        e.add(t);
      }
      e.setTarget(InputTarget.ura);
      e.removeClosedAt(0);
      expect(e.target, InputTarget.ura);
    });
  });

  testWidgets('13장이면 대기패 시트에서 쯔모를 눌러 바로 결과로', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    // 첫 화면은 로비(폰도 태블릿과 같은 흐름, 2026-10-29) → 점수 계산 타일.
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lobby-calc')));
    await tester.pumpAndSettle();

    // 123m 456p 789s 23m 55p: 1m·4m 양면 대기
    for (final code in parseTiles('123m456p789s23m55p').tiles) {
      final key = find.byKey(ValueKey('palette-$code'));
      await tester.ensureVisible(key);
      await tester.tap(key);
      await tester.pump();
    }
    expect(find.text('손패 13/14'), findsOneWidget);
    await tester.tap(find.widgetWithText(ChoiceChip, '남풍').first);
    await tester.pump();

    await tester.tap(find.text('대기패 보기'));
    await tester.pumpAndSettle();
    expect(find.text('대기 2종'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('wait-4m-tsumo')));
    await tester.pumpAndSettle();

    // 핑후 + 멘젠 쯔모 = 2판 20부, 자: 400/700
    expect(find.text('핑후'), findsOneWidget);
    expect(find.text('멘젠 쯔모'), findsOneWidget);
  });
}
