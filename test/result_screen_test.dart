import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 리치 핑후 손패(4m 화료).
ScoreResult _result({required bool tsumo, int seatWind = Tiles.south}) {
  final e = HandEditor();
  for (final c in ['1m', '2m', '3m', '4p', '5p', '6p', '7s', '8s', '9s', '2m', '3m', '5p', '5p', '4m']) {
    e.closed.add(HandTile(Tiles.parse(c)));
  }
  e.isTsumo = tsumo;
  e.riichi = true;
  e.seatWind = seatWind;
  final r = e.calculate();
  assert(r.isValid, r.error);
  return r;
}

/// 점수 이동판 한 자리의 글을 이어 붙인 것(예: `南|화료|+2700`).
String _seat(WidgetTester tester, int side) => tester
    .widgetList<Text>(find.descendant(of: find.byKey(ValueKey('cross-seat-$side')), matching: find.byType(Text)))
    .map((t) => t.data ?? '')
    .join('|');

void main() {
  group('Game.winDelta', () {
    const p = Payment(ron: 0, tsumoFromDealer: 2000, tsumoFromNonDealer: 1000, total: 4000);

    test('자 쯔모: 친 2000, 자 1000씩, 공탁과 새 리치는 화료자에게', () {
      final d = Game.winDelta(
          dealer: 0, winner: 2, payment: p, isTsumo: true, sticks: 1, newRiichi: const [1, 2]);
      expect(d, [-2000, -1000 - 1000, 4000 + 3000 - 1000, -1000]);
      expect(d.reduce((a, b) => a + b), 1000); // 이미 공탁에 있던 1000 만큼 늘어난다
    });

    test('론인데 방총자가 없으면 화료자 몫만', () {
      const ron = Payment(ron: 3900, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: 3900);
      expect(Game.winDelta(dealer: 0, winner: 1, payment: ron, isTsumo: false), [0, 0, 0, 0]);
      expect(Game.winDelta(dealer: 0, winner: 1, payment: ron, isTsumo: false, loser: 3), [0, 3900, 0, -3900]);
    });

    test('win() 이 같은 계산을 쓴다', () {
      final g = Game(id: 'g', startedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D'])
        ..declareRiichi(3);
      g.win(winner: 2, payment: p, isTsumo: true);
      expect(g.scores, [23000, 24000, 30000, 23000]);
    });
  });

  group('결과 화면', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));
    tearDown(gameStore.discardCurrent);

    testWidgets('역이 차례로 나오고, 대국 없이 쯔모면 화료자를 아래에 두고 변화만', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: ResultScreen(result: _result(tsumo: true), isTsumo: true, seatWind: Tiles.south),
      ));
      // 연출 중에는 변화량이 아직 0
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('리치'), findsOneWidget);
      await tester.pumpAndSettle();
      // 리치·쯔모·핑후 3판 20부 → 자 700/1300, 아래가 화료자(남), 오른쪽(서)·위(북)는 자, 왼쪽(동)은 친
      expect(_seat(tester, 0), contains('+2700'));
      expect(_seat(tester, 1), contains('-700'));
      expect(_seat(tester, 2), contains('-700'));
      expect(_seat(tester, 3), contains('-1300'));
    });

    testWidgets('대국 없이 론이면 방총자 자리를 눌러 고른다', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: ResultScreen(result: _result(tsumo: false), seatWind: Tiles.south),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('cross-prompt')), findsOneWidget);
      await tester.ensureVisible(find.byKey(const ValueKey('cross-seat-2')));
      await tester.tap(find.byKey(const ValueKey('cross-seat-2')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('cross-prompt')), findsNothing);
      expect(_seat(tester, 2), contains('방총'));
      expect(_seat(tester, 2), contains('-'));
      expect(_seat(tester, 1), contains('±0'));
    });

    testWidgets('대국 중이면 점수판 점수에서 바뀐 점수까지, 고른 방총자는 화료 시트로', (tester) async {
      gameStore.resume(const ['A', 'B', 'C', 'D'], const GameSettings(),
          scores: const [25000, 25000, 25000, 25000], roundWind: 0, roundNumber: 1, honba: 0);
      await tester.pumpWidget(MaterialApp(
        home: ResultScreen(result: _result(tsumo: false), seatWind: Tiles.south, gameSeat: 1, winnerRiichi: true),
      ));
      await tester.pumpAndSettle();
      // 아래 = 자리 0(A, 친). 오른쪽 = B(화료자). 위 = C.
      await tester.ensureVisible(find.byKey(const ValueKey('cross-seat-2')));
      await tester.tap(find.byKey(const ValueKey('cross-seat-2')));
      await tester.pumpAndSettle();
      final ron = _result(tsumo: false).payment.ron;
      expect(_seat(tester, 1), contains('리치')); // 점수판에 없던 화료자 리치를 자동으로
      expect(_seat(tester, 1), contains('${25000 + ron}')); // 리치봉 -1000 을 다시 가져온다
      expect(_seat(tester, 2), contains('${25000 - ron}'));

      await tester.tap(find.textContaining('대국에 반영'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('기록'));
      await tester.tap(find.text('기록'));
      await tester.pumpAndSettle();
      expect(gameStore.current!.scores, [25000, 25000 + ron, 25000 - ron, 25000]);
    });
  });
}
