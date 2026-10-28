import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:shared_preferences/shared_preferences.dart';

Game _game({int roundWind = 1, int roundNumber = 2, int honba = 1}) => Game.resumed(
      id: 'g',
      startedAt: DateTime(2026, 10, 22),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      scores: const [12700, 32700, 38200, 16400],
      roundWind: roundWind,
      roundNumber: roundNumber,
      honba: honba,
    );

void main() {
  group('중간부터 시작', () {
    test('친은 국 번호로 정해지고 점수 차이가 사건으로 남는다', () {
      final g = _game();
      expect(g.dealer, 1);
      expect(g.roundLabel, '남2국 1본장');
      expect(g.seatWindOf(1), Tiles.east);
      expect(g.seatWindOf(0), Tiles.north);
      expect(g.events.single.kind, 'adjust');
      expect(g.events.single.delta, [-12300, 7700, 13200, -8600]);
    });

    test('리치 자리는 국이 끝나면 비고, 저장·복원된다', () {
      final g = _game();
      g.declareRiichi(3);
      expect(g.riichiSeats, {3});
      final back = Game.fromJson(g.toJson());
      expect(back.riichiSeats, {3});
      g.draw({3});
      expect(g.riichiSeats, isEmpty);
    });

    test('옛 저장 데이터(riichiSeats 없음)도 읽힌다', () {
      final j = _game().toJson()..remove('riichiSeats');
      expect(Game.fromJson(j).riichiSeats, isEmpty);
    });
  });

  group('계산기 자동 채움', () {
    test('자리를 고르면 자풍·장풍·본장·리치가 채워진다', () {
      final g = _game();
      g.declareRiichi(0);
      final e = HandEditor();
      expect(e.syncFromGame(g), isTrue); // 처음엔 장풍·본장만
      expect(e.roundWind, Tiles.south);
      expect(e.honba, 1);
      expect(e.seatWind, Tiles.east); // 자리 안 골랐으니 그대로
      expect(e.syncFromGame(g), isFalse); // 같은 국이면 다시 안 덮어씀

      e.setGameSeat(g, 0);
      expect(e.seatWind, Tiles.north);
      expect(e.riichi, isTrue);

      e.setGameSeat(g, 1);
      expect(e.seatWind, Tiles.east);
      expect(e.riichi, isFalse);
    });

    test('손으로 고친 본장은 국이 바뀌기 전까지 유지된다', () {
      final g = _game();
      final e = HandEditor();
      e.syncFromGame(g);
      e.setHonba(3);
      expect(e.syncFromGame(g), isFalse);
      expect(e.honba, 3);
      g.draw({}); // 남3국 2본장
      expect(e.syncFromGame(g), isTrue);
      expect(e.honba, 2);
    });

    test('울었으면 리치를 채우지 않는다', () {
      final g = _game();
      g.declareRiichi(2);
      final e = HandEditor();
      e.addMeld(Meld.pon(Tiles.parse('1z')));
      e.setGameSeat(g, 2);
      expect(e.riichi, isFalse);
    });

    test('대국이 없으면 자리 선택이 지워진다', () {
      final g = _game();
      final e = HandEditor();
      e.setGameSeat(g, 2);
      e.syncFromGame(null);
      expect(e.gameSeat, isNull);
    });
  });

  testWidgets('대국 중이면 입력 화면에 자리 선택이 뜨고, 반영하면 손패가 비워진다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    addTearDown(gameStore.discardCurrent);

    gameStore.resume(
      const ['A', 'B', 'C', 'D'],
      const GameSettings(),
      scores: const [25000, 25000, 25000, 25000],
      roundWind: 1,
      roundNumber: 2,
      honba: 1,
    );

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    expect(find.textContaining('대국 남2국 1본장'), findsOneWidget);

    // C 는 남2국에서 남가(친 B 의 다음).
    await tester.ensureVisible(find.byKey(const ValueKey('game-seat-2')));
    await tester.tap(find.byKey(const ValueKey('game-seat-2')));
    await tester.pump();
    expect(find.textContaining('점수판 값으로 채웠습니다'), findsOneWidget);

    // 핑후 손패를 넣고 계산 → 1판 30부 자 론 (본장 1 → 1300)
    for (final code in parseTiles('123m456p789s23m55p4m').tiles) {
      final key = find.byKey(ValueKey('palette-$code'));
      await tester.ensureVisible(key);
      await tester.tap(key);
      await tester.pump();
    }
    await tester.tap(find.text('점수 계산'));
    await tester.pumpAndSettle();
    expect(find.text('핑후'), findsOneWidget);
    expect(find.text('1300점'), findsOneWidget); // 본장 1 포함

    await tester.tap(find.textContaining('대국에 반영'));
    await tester.pumpAndSettle();
    // 화료자 C 가 미리 선택돼 있고 방총자만 고르면 된다.
    await tester.tap(find.widgetWithText(ChoiceChip, 'A').last);
    await tester.pump();
    await tester.tap(find.text('기록'));
    await tester.pumpAndSettle();

    final g = gameStore.current!;
    expect(g.scores[2], 26300);
    expect(g.scores[0], 23700);
    expect(g.roundLabel, '남3국');
    // 결과 화면이 닫히고 손패가 비워졌다.
    expect(find.text('손패 0/14'), findsOneWidget);
    expect(find.textContaining('대국 남3국'), findsOneWidget);
  });
}
