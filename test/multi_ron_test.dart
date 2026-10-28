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
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

HandReading _hand(String codes) =>
    HandReading.fromJson({'tiles': [for (final c in codes.split(' ')) {'tile': c, 'conf': 0.95}]});

/// 아래(0)가 4통을 버려 위(2)·왼쪽(3)이 함께 론. 왼쪽 강 끝도 4통이라 서로를 방총자로 보면 안 된다.
final _center = CenterReading.fromJson({
  'last_discards': {'bottom': '4p', 'right': '7m', 'top': '1z', 'left': '4p'},
});
const _seats = SeatMap(0);

List<TableMerge> _doubleRon(Game g) => [
      mergeReading(
          hand: _hand('1m 2m 3m 4m 5m 6m 7m 8m 9m 2p 3p 5s 5s'),
          center: _center,
          winnerSide: Side.top,
          game: g,
          seats: _seats,
          otherWinners: {Side.left}),
      mergeReading(
          hand: _hand('2s 3s 4s 6s 7s 8s 1z 1z 1z 2p 3p 9m 9m'),
          center: _center,
          winnerSide: Side.left,
          game: g,
          seats: _seats,
          otherWinners: {Side.top}),
    ];

Game _game({GameSettings settings = const GameSettings()}) => Game(
      id: 'g',
      startedAt: DateTime(2026, 10, 26),
      settings: settings,
      names: const ['A', 'B', 'C', 'D'],
    );

void main() {
  widgetTests();
  group('동시 론', () {
    test('방총자 다음 차례부터 가까운 순', () {
      expect(Game.ronOrder(0, [3, 1]), [1, 3]);
      expect(Game.ronOrder(2, [1, 3]), [3, 1]);
      expect(Game.ronOrder(3, [2, 0, 1]), [0, 1, 2]);
    });

    test('더블론: 각자 론 점수, 본장·공탁은 가까운 쪽, 친이 안 났으면 친 교체', () {
      final g = _game();
      g.declareRiichi(2); // 공탁 1
      g.honba = 2;
      g.multiRon(loser: 0, payments: {
        3: paymentFor(han: 1, fu: 30, isDealer: false, isTsumo: false, honba: 0), // 1000
        1: paymentFor(han: 3, fu: 40, isDealer: false, isTsumo: false, honba: 0), // 5200
      }, summaries: {
        1: '3판 40부',
        3: '1판 30부',
      });
      // B(1) 가 A(0) 바로 다음 차례 → 본장 600·공탁 1000 은 B
      expect(g.scores, [25000 - 6800, 25000 + 6800, 24000, 25000 + 1000]);
      expect(g.scores.reduce((a, b) => a + b), 100000);
      expect(g.riichiSticks, 0);
      expect(g.dealer, 1);
      expect(g.honba, 0);
      final e = g.events.last;
      expect(e.kind, 'win');
      expect(e.description, startsWith('더블론(A) B 3판 40부 5200 / D 1판 30부 1000'));
      expect(e.description, contains('+공탁 1 B'));
    });

    test('친이 화료자 중에 있으면 연장, 본장 +1', () {
      final g = _game();
      g.multiRon(loser: 1, payments: {
        0: paymentFor(han: 2, fu: 30, isDealer: true, isTsumo: false, honba: 0),
        2: paymentFor(han: 2, fu: 30, isDealer: false, isTsumo: false, honba: 0),
      });
      expect(g.dealer, 0);
      expect(g.honba, 1);
      expect(g.roundNumber, 1);
    });

    test('트리플론(인정하는 규칙)', () {
      final g = _game(settings: const GameSettings(multiRon: GameSettings.multiRonTriple));
      g.multiRon(loser: 3, payments: {
        for (final w in [0, 1, 2]) w: paymentFor(han: 1, fu: 30, isDealer: w == 0, isTsumo: false, honba: 0),
      });
      expect(g.scores[3], 25000 - 1500 - 1000 - 1000);
      expect(g.events.last.description, startsWith('트리플론(D)'));
    });

    test('방총자가 화료자면 오류', () {
      expect(
        () => _game().multiRon(loser: 1, payments: {
          1: paymentFor(han: 1, fu: 30, isDealer: false, isTsumo: false, honba: 0),
        }),
        throwsArgumentError,
      );
    });

    test('도중 유국: 점수 그대로, 친 유지, 본장 +1, 공탁은 남음', () {
      final g = _game();
      g.declareRiichi(1);
      g.abortiveDraw('트리플론');
      expect(g.scores, [25000, 24000, 25000, 25000]);
      expect(g.dealer, 0);
      expect(g.honba, 1);
      expect(g.riichiSticks, 1);
      expect(g.riichiSeats, isEmpty);
      expect(g.events.last.description, '도중 유국 (트리플론)');
    });

    test('자동 리치 후보: 화료자 리치는 각자 손패 계산을 따른다', () {
      final g = _game();
      final c = g.autoRiichiCandidates({0, 1, 3}, winner: 1, winnerRiichi: false, otherWinners: {2: true});
      // 1 은 사진엔 리치지만 손패는 리치 아님 → 뺌, 2 는 손패가 리치 → 넣음
      expect(c, {0, 2, 3});
    });
  });

  group('동시 론 판독 병합', () {
    test('다른 화료자는 방총자 후보에서 빠진다', () {
      final ms = _doubleRon(_game());
      for (final m in ms) {
        expect(m.loser, 0);
        expect(m.isTsumo, isFalse);
        expect(m.hasFlag(MergeIssue.loserAmbiguous), isFalse);
        expect(m.hand, isNotNull);
      }
      // 빼지 않으면 왼쪽 강 끝 4통도 후보가 되어 방총자가 모호하다.
      final alone = mergeReading(
          hand: _hand('1m 2m 3m 4m 5m 6m 7m 8m 9m 2p 3p 5s 5s'),
          center: _center,
          winnerSide: Side.top,
          game: _game(),
          seats: _seats);
      expect(alone.hasFlag(MergeIssue.loserAmbiguous), isTrue);
    });

    test('더블론 인정: 방총자 다음 차례부터 가까운 순으로 둘 다', () {
      final g = _game();
      final r = pickRonWinners(_doubleRon(g), g.settings, g.names);
      expect(r.kept.map((m) => m.winner), [2, 3]);
      expect(r.loser, 0);
      expect(r.flags, isEmpty);
    });

    test('머리치기: 가까운 한 명만', () {
      final g = _game(settings: const GameSettings(multiRon: GameSettings.multiRonHeadBump));
      final r = pickRonWinners(_doubleRon(g).reversed.toList(), g.settings, g.names);
      expect(r.kept.map((m) => m.winner), [2]);
      expect(r.flags.single.message, contains('머리치기'));
    });

    test('쯔모로 읽힌 손패가 섞이면 첫 손패만', () {
      final g = _game();
      final tsumo = mergeReading(
          hand: HandReading.fromJson({
            'tiles': [for (final c in '1m 2m 3m 4m 5m 6m 7m 8m 9m 2p 3p 5s 5s'.split(' ')) {'tile': c, 'conf': 0.95}],
            'win_tile': {'tile': '1p', 'conf': 0.95},
          }),
          center: _center,
          winnerSide: Side.top,
          game: g,
          seats: _seats);
      expect(tsumo.isTsumo, isTrue);
      final r = pickRonWinners([tsumo, _doubleRon(g)[1]], g.settings, g.names);
      expect(r.kept.single.winner, 2);
      expect(r.flags.single.issue, MergeIssue.multiRon);
    });
  });

  group('더블론 자동 판정', () {
    bool valid(TableMerge m) => calculate(m.hand!, m.situation).isValid;

    test('같은 방총자·같은 화료패로 둘 다 화료형이면 묻지 않는다', () {
      final ms = _doubleRon(_game());
      expect(ms.map((m) => m.closed.last.tile).toSet(), hasLength(1));
      expect(clearDoubleRon(ms, valid), isTrue);
    });

    test('한쪽이 역 없음·계산 실패면 묻는다', () {
      final ms = _doubleRon(_game());
      expect(clearDoubleRon(ms, (m) => m.winner == 2), isFalse);
    });

    test('쯔모로 읽힌 손패가 있거나 한 명뿐이면 묻는다', () {
      final g = _game();
      final tsumo = mergeReading(
          hand: HandReading.fromJson({
            'tiles': [for (final c in '1m 2m 3m 4m 5m 6m 7m 8m 9m 2p 3p 5s 5s'.split(' ')) {'tile': c, 'conf': 0.95}],
            'win_tile': {'tile': '1p', 'conf': 0.95},
          }),
          center: _center,
          winnerSide: Side.top,
          game: g,
          seats: _seats);
      expect(clearDoubleRon([tsumo, _doubleRon(g)[1]], valid), isFalse);
      expect(clearDoubleRon([_doubleRon(g).first], valid), isFalse);
    });

    test('방총자를 못 정하면 묻는다', () {
      final g = _game();
      final noLoser = mergeReading(
          hand: _hand('1m 2m 3m 4m 5m 6m 7m 8m 9m 2p 3p 5s 5s'),
          center: CenterReading.fromJson({'last_discards': <String, String>{}}),
          winnerSide: Side.top,
          game: g,
          seats: _seats,
          otherWinners: {Side.left});
      expect(clearDoubleRon([noLoser, _doubleRon(g)[1]], valid), isFalse);
    });
  });

  group('동시 론 규칙 설정', () {
    test('인정 인원과 트리플론 유국', () {
      expect(const GameSettings().maxRonWinners, 2);
      expect(const GameSettings().tripleRonDraws, isTrue);
      expect(const GameSettings(multiRon: GameSettings.multiRonHeadBump).maxRonWinners, 1);
      expect(const GameSettings(multiRon: GameSettings.multiRonTriple).maxRonWinners, 3);
      expect(const GameSettings(multiRon: GameSettings.multiRonTriple).tripleRonDraws, isFalse);
    });

    test('저장·불러오기, 예전 저장본은 기본값', () {
      const s = GameSettings(multiRon: GameSettings.multiRonHeadBump, bottomSeat: 2);
      expect(GameSettings.fromJson(s.toJson()).multiRon, GameSettings.multiRonHeadBump);
      expect(s.copyWith(bottomSeat: 1).multiRon, GameSettings.multiRonHeadBump);
      final old = s.toJson()..remove('multiRon');
      expect(GameSettings.fromJson(old).multiRon, GameSettings.multiRonDouble);
    });
  });
}

ScoreResult _ron(List<String> codes, {bool riichi = false}) {
  final e = HandEditor();
  for (final c in codes) {
    e.closed.add(HandTile(Tiles.parse(c)));
  }
  e.isTsumo = false;
  e.riichi = riichi;
  e.seatWind = Tiles.south;
  final r = e.calculate();
  assert(r.isValid, r.error);
  return r;
}

void _resume() => gameStore.resume(
      const ['A', 'B', 'C', 'D'],
      const GameSettings(),
      scores: const [25000, 25000, 25000, 25000],
      roundWind: 0,
      roundNumber: 1,
      honba: 0,
    );

Future<void> _tapVisible(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

void widgetTests() {
  group('화료 시트: 더블론', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));
    tearDown(gameStore.discardCurrent);

    testWidgets('점수판에서 함께 론한 사람을 더해 한 번에 기록', (tester) async {
      _resume();
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (ctx) => TextButton(
            onPressed: () => showWinSheet(ctx, gameStore.current!, winner: 1),
            child: const Text('열기'),
          ),
        ),
      ));
      await tester.tap(find.text('열기'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.widgetWithText(ChoiceChip, 'A')); // 방총자
      await _tapVisible(tester, find.byKey(const ValueKey('add-extra-win')));
      expect(find.byKey(const ValueKey('extra-win-0')), findsOneWidget);
      // 기본 규칙은 둘까지라 더 추가하는 버튼이 없다.
      expect(find.byKey(const ValueKey('add-extra-win')), findsNothing);
      await _tapVisible(tester, find.text('2명 론 기록'));

      final g = gameStore.current!;
      // 둘 다 1판 30부 1000점, A 가 2000점
      expect(g.scores, [23000, 26000, 26000, 25000]);
      expect(g.events.last.description, startsWith('더블론(A) B 1판 30부 1000 / C 1판 30부 1000'));
      expect(g.dealer, 1);
    });

    testWidgets('결과 화면이 함께 론한 사람을 보여 주고 시트에 미리 채운다', (tester) async {
      _resume();
      gameStore.mutate((g) => g.declareRiichi(3)); // 공탁 1 → 방총자(A) 다음 차례에 가까운 B 가 가져간다
      final main = _ron(['2m', '3m', '4m', '3p', '4p', '5p', '6s', '7s', '8s', '5s', '5s', '6m', '7m', '5m']);
      final other = _ron(['1m', '2m', '3m', '4p', '5p', '6p', '7s', '8s', '9s', '2m', '3m', '5p', '5p', '4m'],
          riichi: true);
      await tester.pumpWidget(MaterialApp(
        home: ResultScreen(
          result: main,
          gameSeat: 2,
          loser: 0,
          otherWins: [OtherWin(1, other, riichi: true)],
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('result-other-wins')), findsOneWidget);
      await _tapVisible(tester, find.textContaining('대국에 반영'));
      expect(find.byKey(const ValueKey('extra-win-0')), findsOneWidget);
      await _tapVisible(tester, find.text('2명 론 기록'));

      final g = gameStore.current!;
      expect(g.scores.reduce((a, b) => a + b), 100000);
      expect(g.riichiSticks, 0);
      expect(g.events.last.description, startsWith('더블론(A) B'));
      expect(g.events.last.description, contains('+공탁 2 B')); // D 의 리치 + B 자동 리치
      expect(g.events.where((e) => e.description == 'B 리치 (자동)'), hasLength(1));
    });

    testWidgets('"한 명만 론" 을 누르면 함께 론한 사람을 빼고 한 명만 기록한다', (tester) async {
      _resume();
      final main = _ron(['2m', '3m', '4m', '3p', '4p', '5p', '6s', '7s', '8s', '5s', '5s', '6m', '7m', '5m']);
      final other = _ron(['1m', '2m', '3m', '4p', '5p', '6p', '7s', '8s', '9s', '2m', '3m', '5p', '5p', '4m']);
      await tester.pumpWidget(MaterialApp(
        home: ResultScreen(result: main, gameSeat: 2, loser: 0, otherWins: [OtherWin(1, other)]),
      ));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.byKey(const ValueKey('result-single-ron')));
      expect(find.byKey(const ValueKey('result-other-wins')), findsNothing);
      await _tapVisible(tester, find.textContaining('대국에 반영'));
      expect(find.byKey(const ValueKey('extra-win-0')), findsNothing);
      await _tapVisible(tester, find.text('기록'));

      final g = gameStore.current!;
      expect(g.scores.reduce((a, b) => a + b), 100000);
      expect(g.events.last.description, isNot(contains('더블론')));
      expect(g.scores[1], 25000); // B 는 함께 론에서 빠졌다
    });
  });
}
