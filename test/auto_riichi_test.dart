import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/ui/game/win_sheet.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/mount/capture_label.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

List<Map<String, dynamic>> _tiles(String codes) =>
    [for (final c in codes.split(' ')) {'tile': c, 'conf': 0.99}];

/// 핑후 쯔모 손패(리치).
ScoreResult _result() {
  final e = HandEditor();
  for (final c in ['1m', '2m', '3m', '4p', '5p', '6p', '7s', '8s', '9s', '2m', '3m', '5p', '5p', '4m']) {
    e.closed.add(HandTile(Tiles.parse(c)));
  }
  e.isTsumo = true;
  e.riichi = true;
  e.seatWind = Tiles.west;
  final r = e.calculate();
  assert(r.isValid, r.error);
  return r;
}

void _resumeGame() => gameStore.resume(
      const ['A', 'B', 'C', 'D'],
      const GameSettings(),
      scores: const [25000, 25000, 25000, 25000],
      roundWind: 0,
      roundNumber: 1,
      honba: 0,
    );

Future<void> _openSheet(WidgetTester tester, {Set<int> photo = const {}, bool winnerRiichi = true}) async {
  await tester.pumpWidget(MaterialApp(
    home: ResultScreen(
      result: _result(),
      isTsumo: true,
      gameSeat: 2,
      photoRiichiSeats: photo,
      winnerRiichi: winnerRiichi,
    ),
  ));
  await tester.tap(find.textContaining('대국에 반영'));
  await tester.pumpAndSettle();
}

Future<void> _submit(WidgetTester tester) async {
  await tester.ensureVisible(find.text('기록'));
  await tester.tap(find.text('기록'));
  await tester.pumpAndSettle();
}

void main() {
  group('병합: 사진 리치 자리', () {
    test('확신도 기준 이상인 자리만 자리 번호로', () {
      final g = Game(
        id: 'g',
        startedAt: DateTime(2026, 10, 23),
        settings: const GameSettings(),
        names: const ['A', 'B', 'C', 'D'],
      );
      const seats = SeatMap(1);
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 2m 3m 5p 5p'),
          'win_tile': {'tile': '4m', 'conf': 0.9},
        }),
        center: CenterReading.fromJson({
          'riichi': {'bottom': false, 'right': true, 'top': true, 'left': true},
          'riichi_conf': {'bottom': 0.99, 'right': 0.9, 'top': 0.95, 'left': 0.3},
        }),
        winnerSide: Side.top,
        game: g,
        seats: seats,
      );
      expect(m.photoRiichiSeats, {seats.seatOf(Side.right), seats.seatOf(Side.top)});
      expect(m.situation.riichi, isTrue); // 화료자(위) 리치
      expect(m.flags.map((f) => f.message).join(), contains('리치봉을 자동으로'));
    });
  });

  group('화료 시트: 리치봉 자동 반영', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));
    tearDown(gameStore.discardCurrent);

    testWidgets('점수판에 없던 리치를 칩으로 켜 두고, 기록하면 1000점씩 공탁 → 화료자가 가져간다', (tester) async {
      _resumeGame();
      await _openSheet(tester, photo: {1, 2});
      expect(find.byKey(const ValueKey('auto-riichi-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('auto-riichi-2')), findsOneWidget);
      expect(find.textContaining('+공탁 2000'), findsOneWidget);
      await _submit(tester);

      final g = gameStore.current!;
      expect(g.riichiSticks, 0);
      expect(g.scores.reduce((a, b) => a + b), 100000);
      expect(g.scores[1], g.scores[3] - 1000); // B 만 리치봉을 냈다(둘 다 자, 쯔모 지불 같음)
      final texts = g.events.map((e) => e.description).toList();
      expect(texts, contains('B 리치 (자동)'));
      expect(texts, contains('C 리치 (자동)'));
    });

    testWidgets('칩을 끄면 그 자리는 넣지 않는다', (tester) async {
      _resumeGame();
      await _openSheet(tester, photo: {1});
      await tester.tap(find.byKey(const ValueKey('auto-riichi-1')));
      await tester.pump();
      expect(find.textContaining('+공탁 1000'), findsOneWidget); // C(화료자) 것만
      await _submit(tester);
      final g = gameStore.current!;
      expect(g.scores[1], g.scores[3]);
      expect(g.events.map((e) => e.description), isNot(contains('B 리치 (자동)')));
    });

    testWidgets('점수판에 이미 있는 리치는 다시 넣지 않는다', (tester) async {
      _resumeGame();
      gameStore.mutate((g) => g.declareRiichi(1));
      await _openSheet(tester, photo: {1});
      expect(find.byKey(const ValueKey('auto-riichi-1')), findsNothing);
      expect(find.byKey(const ValueKey('auto-riichi-2')), findsOneWidget);
      await _submit(tester);
      final g = gameStore.current!;
      expect(g.scores.reduce((a, b) => a + b), 100000);
      expect(g.scores[1], g.scores[3] - 1000); // 수동 리치 1000점 한 번만
      expect(g.events.where((e) => e.description.startsWith('B 리치')).length, 1);
    });

    testWidgets('사진도 손패도 리치가 아니면 칩이 없다', (tester) async {
      _resumeGame();
      await _openSheet(tester, winnerRiichi: false);
      expect(find.textContaining('리치봉 자동 반영'), findsNothing);
    });
  });

  test('label.json 에 리치 4자리와 자동 반영 자리가 남는다', () {
    final j = captureLabelJson(
      HandEditor(),
      const WinOutcome(
        winner: 2,
        loser: null,
        isTsumo: true,
        roundLabel: '동1국',
        honba: 0,
        riichiSeats: {2, 1},
        autoRiichiSeats: {1},
      ),
    );
    expect(j['riichi_seats'], [1, 2]);
    expect(j['auto_riichi_seats'], [1]);
  });
}
