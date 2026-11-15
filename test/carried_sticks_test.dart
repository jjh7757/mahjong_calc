import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

Game _game() => Game(
      id: 'g',
      startedAt: DateTime(2026, 10, 30),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
    );

const _seats = SeatMap(0);
const _ron1000 = Payment(ron: 1000, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: 1000);

/// 오른쪽(B) 화료 손패. 핑후라 리치 없이도 역이 있다.
HandReading _pinfu() => HandReading.fromJson({
      'tiles': [
        for (final c in '1m 2m 3m 4p 5p 6p 7s 8s 9s 2m 3m 5p 5p'.split(' ')) {'tile': c, 'conf': 0.99}
      ],
      'win_tile': {'tile': '4m', 'conf': 0.99},
    });

CenterReading _center(Set<Side> sticks, {Map<String, String?> last = const {}}) => CenterReading.fromJson({
      'dora_indicators': [
        {'tile': '1z', 'conf': 0.99},
        {'tile': '2z', 'conf': 0.99},
      ],
      'riichi': {for (final s in Side.values) s.name: sticks.contains(s)},
      'riichi_conf': {for (final s in Side.values) s.name: sticks.contains(s) ? 0.9 : 0.0},
      'last_discards': last,
    });

TableMerge _merge(Game g, HandReading hand, Set<Side> sticks,
        {Side winner = Side.right,
        Set<Side> tracked = const {},
        Map<String, String?> last = const {}}) =>
    mergeReading(
      hand: hand,
      center: _center(sticks, last: last),
      winnerSide: winner,
      game: g,
      seats: _seats,
      trackedRiichi: tracked,
    );

/// 자동 반영을 막는 이유(화료 형태·표시패 등 다른 조건은 통과시킨다).
String? _blocker(TableMerge m) => autoRecordBlocker(
      warnings: const [],
      issues: [for (final f in m.flags) f.issue],
      otherWinners: 0,
      isTsumo: false,
      loser: 0,
      resultValid: true,
      paoBase: 0,
      gameOver: false,
    );

void main() {
  group('대국: 유국으로 남은 리치봉 주인', () {
    test('유국·도중 유국이면 남기고, 화료로 공탁이 넘어가면 비운다', () {
      final g = _game()..declareRiichi(1);
      expect(g.carriedStickSeats, isEmpty);
      g.draw({1});
      expect(g.carriedStickSeats, {1});
      expect(g.riichiSeats, isEmpty);
      expect(g.riichiSticks, 1);

      g.declareRiichi(2);
      g.abortiveDraw('구종구패');
      expect(g.carriedStickSeats, {1, 2});

      g.win(winner: 0, payment: _ron1000, isTsumo: false, loser: 3);
      expect(g.carriedStickSeats, isEmpty);
      expect(g.riichiSticks, 0);
    });

    test('되돌리기와 저장에도 남는다', () {
      final g = _game()..declareRiichi(1);
      g.draw({1});
      final before = g.checkpoint();
      g.win(winner: 0, payment: _ron1000, isTsumo: false, loser: 3);
      expect(g.carriedStickSeats, isEmpty);
      g.rewindTo(before);
      expect(g.carriedStickSeats, {1});

      final loaded = Game.fromJson(jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>);
      expect(loaded.carriedStickSeats, {1});
      expect(GameCheckpoint.fromJson(jsonDecode(jsonEncode(before.toJson())) as Map<String, dynamic>).carriedStickSeats, {1});
      // 이 칸이 없던 옛 저장본.
      final old = g.toJson()..remove('carriedStickSeats');
      expect(Game.fromJson(jsonDecode(jsonEncode(old)) as Map<String, dynamic>).carriedStickSeats, isEmpty);
    });
  });

  group('병합: 유국 공탁은 가운데에 모으므로 홈의 봉은 이번 판 리치(2026-11-13)', () {
    late Game g;
    setUp(() {
      g = _game()..declareRiichi(1);
      g.draw({1});
    });

    test('전판 봉 주인이 홈에 봉을 두고 화료: 리치로 계산하고 리치봉을 자동 반영', () {
      final m = _merge(g, _pinfu(), {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiMismatch), isTrue); // 점수판엔 없음 → 반영 때 리치봉을 넣는다
      expect(m.photoRiichiSeats, {1});
      expect(_blocker(m), isNull);
    });

    test('전판 봉 주인이 홈이 빈 채 화료: 리치 아님', () {
      final m = _merge(g, _pinfu(), const {});
      expect(m.situation.riichi, isFalse);
      expect(m.photoRiichiSeats, isEmpty);
    });

    test('다른 사람 화료 때 홈의 봉은 모두 이번 판 리치', () {
      final m = _merge(g, _pinfu(), {Side.right, Side.top}, winner: Side.bottom);
      expect(m.photoRiichiSeats, {1, 2});
      expect(g.autoRiichiCandidates(m.photoRiichiSeats, winner: 0, winnerRiichi: false), {1, 2});
    });

    test('울린 손패는 홈에 봉이 보여도 리치 불가', () {
      final open = HandReading(
        tiles: [for (final c in '1m 2m 3m 4m 5m 6m 7m 8m 9m 2z'.split(' ')) ReadTile.fromCode(c, 0.99)!],
        melds: [ReadMeld(ReadMeldType.chi, [for (final c in ['6m', '7m', '8m']) ReadTile.fromCode(c, 1)!], conf: 0.9)],
        winTile: ReadTile.fromCode('2z', 0.99),
      );
      final m = _merge(g, open, {Side.right});
      expect(m.situation.riichi, isFalse);
      expect(m.hasFlag(MergeIssue.riichiImpossible), isTrue);
    });

    test('점수판에 다시 리치한 봉 주인: 리치, 어긋남 없음', () {
      g.declareRiichi(1);
      final m = _merge(g, _pinfu(), {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiMismatch), isFalse);
    });

    test('유국 때 리치한 사람이 다음 판 다시 리치하고 화료: 공탁 2개 + 본장을 가져간다', () {
      // setUp: B(1) 리치 → 유국(B 혼자 텐파이). 공탁 1, 본장 1.
      expect(g.riichiSticks, 1);
      expect(g.honba, 1);
      final before = [...g.scores];
      final m = _merge(g, _pinfu(), {Side.right}); // 다음 판: B 홈에 새 봉(전판 봉은 가운데)
      expect(m.situation.riichi, isTrue);
      expect(_blocker(m), isNull);
      // 앱의 반영: 사진 리치 자리 중 점수판에 없는 것을 리치봉으로 넣고 화료. 지불액은 본장 포함(1300 + 300).
      for (final s in g.autoRiichiCandidates(m.photoRiichiSeats, winner: 1, winnerRiichi: m.situation.riichi)) {
        g.declareRiichi(s);
      }
      expect(g.riichiSticks, 2);
      g.win(winner: 1, payment: const Payment(ron: 1600, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: 1600), isTsumo: false, loser: 3);
      // B: −1000(새 리치봉) + 1300 + 본장 300 + 공탁 2000(전판 1 + 이번 판 1). D: −1300 − 300.
      expect(g.scores[1] - before[1], -1000 + 1300 + 300 + 2000);
      expect(g.scores[3] - before[3], -1300 - 300);
      expect(g.riichiSticks, 0);
      expect(g.carriedStickSeats, isEmpty);
    });

    test('유국 때 리치한 사람이 다음 판 다시 리치하고 다른 사람이 화료: 그 사람 리치봉도 걷는다', () {
      final before = [...g.scores];
      final m = _merge(g, _pinfu(), {Side.right}, winner: Side.bottom);
      for (final s in g.autoRiichiCandidates(m.photoRiichiSeats, winner: 0, winnerRiichi: m.situation.riichi)) {
        g.declareRiichi(s);
      }
      g.win(winner: 0, payment: const Payment(ron: 1600, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: 1600), isTsumo: false, loser: 3);
      expect(g.scores[1] - before[1], -1000);
      expect(g.scores[0] - before[0], 1300 + 300 + 2000);
    });

    test('주인을 모르는 공탁이 있어도 홈의 봉은 그대로 리치, 묻지 않는다', () {
      final resumed = Game(id: 'g', startedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D'], riichiSticks: 1);
      final m = _merge(resumed, _pinfu(), {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(_blocker(m), isNull);
    });
  });

  group('유국 창', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
    });
    tearDown(() {
      if (gameStore.current != null) gameStore.discardCurrent();
    });

    testWidgets('추적이 본 리치를 켜 두어 봉의 주인이 기록된다', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (c) => TextButton(
              onPressed: () => showDrawDialog(c, gameStore.current!, trackedRiichi: const {2}),
              child: const Text('유국'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('유국'));
      await tester.pumpAndSettle();
      expect(tester.widget<ChoiceChip>(find.byKey(const ValueKey('draw-tenpai-2'))).selected, isTrue);
      expect(tester.widget<ChoiceChip>(find.byKey(const ValueKey('draw-noten-2'))).selected, isFalse);
      expect(tester.widget<FilterChip>(find.byKey(const ValueKey('draw-riichi-2'))).selected, isTrue);

      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      final g = gameStore.current!;
      expect(g.riichiSticks, 1);
      expect(g.carriedStickSeats, {2});
      expect(g.scores[2], 25000 - 1000 + 3000);
    });

    testWidgets('유국 창: 자리마다 텐파이·노텐을 골라 누른다', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (c) => TextButton(
              onPressed: () => showDrawDialog(c, gameStore.current!),
              child: const Text('유국'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('유국'));
      await tester.pumpAndSettle();
      // 처음엔 리치 없는 자리 모두 노텐.
      for (var s = 0; s < 4; s++) {
        expect(tester.widget<ChoiceChip>(find.byKey(ValueKey('draw-noten-$s'))).selected, isTrue);
      }
      // 0·1 을 텐파이로 골랐다가 1 을 다시 노텐으로.
      await tester.tap(find.byKey(const ValueKey('draw-tenpai-0')));
      await tester.tap(find.byKey(const ValueKey('draw-tenpai-1')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('draw-riichi-1')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('draw-noten-1')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('draw-riichi-1')), findsNothing);
      expect(tester.widget<ChoiceChip>(find.byKey(const ValueKey('draw-tenpai-0'))).selected, isTrue);

      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      final g = gameStore.current!;
      // 0 혼자 텐파이: 노텐 셋이 1000씩.
      expect(g.scores, [28000, 24000, 24000, 24000]);
    });
  });

  group('유국 창: 도중 유국', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
    });
    tearDown(() {
      if (gameStore.current != null) gameStore.discardCurrent();
    });

    Future<void> abort(WidgetTester tester, Set<int> tracked) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (c) => TextButton(
              onPressed: () => showDrawDialog(c, gameStore.current!, trackedRiichi: tracked),
              child: const Text('유국'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('유국'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('draw-abortive-구종구패')));
      await tester.pumpAndSettle();
    }

    testWidgets('추적이 본 리치도 공탁에 넣고 봉 주인을 남기며, 창에 알린다', (tester) async {
      await abort(tester, const {2});
      expect(tester.widget<Text>(find.byKey(const ValueKey('draw-abortive-note'))).data, contains('C'));
      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      final g = gameStore.current!;
      expect(g.riichiSticks, 1);
      expect(g.carriedStickSeats, {2});
      expect(g.scores, [25000, 25000, 24000, 25000]);
      expect(g.honba, 1);
    });

    testWidgets('리치가 없으면 점수·공탁 그대로', (tester) async {
      await abort(tester, const {});
      expect(tester.widget<Text>(find.byKey(const ValueKey('draw-abortive-note'))).data, isNot(contains('1000')));
      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      final g = gameStore.current!;
      expect(g.riichiSticks, 0);
      expect(g.carriedStickSeats, isEmpty);
      expect(g.scores, [25000, 25000, 25000, 25000]);
    });
  });

  group('강의 눕힌 패 응답', () {
    const sent = [Side.right, Side.top, Side.left, Side.bottom];
    Map<String, dynamic> river(int count, List<int> sideways) => {'tile_count': count, 'rows': [count], 'sideways': sideways};

    test('틀로 읽었으면 있음·없음, 묻지 않은 자리는 빠진다', () {
      final j = {
        'method': 'frame',
        'rivers': [river(16, const []), river(17, const [11]), river(16, const []), river(16, const [6])],
      };
      expect(riverSidewaysFrom(j, sent, {Side.right, Side.top}), {Side.right: false, Side.top: true});
      expect(riverSidewaysFrom(j, sent, {Side.bottom}), {Side.bottom: true});
    });

    test('통째 읽기·응답 없음·보내지 않은 자리는 모름', () {
      final whole = {
        'method': 'whole',
        'rivers': [river(16, const [3]), river(17, const []), river(16, const []), river(16, const [])],
      };
      expect(riverSidewaysFrom(whole, sent, {Side.right}), {Side.right: null});
      expect(riverSidewaysFrom(null, sent, {Side.right}), {Side.right: null});
      expect(riverSidewaysFrom({'method': 'frame', 'rivers': []}, sent, {Side.right}), {Side.right: null});
      expect(riverSidewaysFrom({'method': 'frame', 'rivers': [river(16, const [])]}, const [Side.top], {Side.right}), {Side.right: null});
    });

    test('다른 자리보다 너무 적게 잡힌 강은 "없음" 으로 믿지 않는다(B 오른쪽: 1장)', () {
      Map<String, dynamic> j(int right, List<int> sideways) => {
            'method': 'frame',
            'rivers': [river(right, sideways), river(18, const []), river(16, const []), river(17, const [])],
          };
      expect(riverSidewaysFrom(j(1, const []), sent, {Side.right}), {Side.right: null});
      expect(riverSidewaysFrom(j(14, const []), sent, {Side.right}), {Side.right: false}); // 4장 차이는 울기로 뺏겼을 수 있다
      expect(riverSidewaysFrom(j(13, const []), sent, {Side.right}), {Side.right: null});
      expect(riverSidewaysFrom(j(1, const [0]), sent, {Side.right}), {Side.right: true}); // 찾았으면 적어도 믿는다
    });
  });

  group('묶음 복구', () {
    ObservedMeld meld(String codes) => ObservedMeld([for (final c in codes.split(' ')) ReadTile.fromCode(c, 1)!], conf: 0.9);

    test('종류만 틀린 가로 패(6s·6z 7m 8m)를 치로 고친다', () {
      for (final codes in ['6s 7m 8m', '6z 7m 8m', '7m 6p 8m']) {
        final fixed = repairMeldSuit(meld(codes))!;
        expect(fixed.type, ReadMeldType.chi, reason: codes);
        expect(fixed.tiles.map((t) => t.tile).toSet(), {Tiles.parse('6m'), Tiles.parse('7m'), Tiles.parse('8m')}, reason: codes);
        expect(fixed.toReadMeld().conf, 0, reason: codes);
      }
      expect(repairMeldSuit(meld('6m 6m 6s'))!.type, ReadMeldType.pon);
    });

    test('숫자까지 틀리거나 두 장이 다르면 고치지 않는다', () {
      expect(repairMeldSuit(meld('4p 4p 7m')), isNull);
      expect(repairMeldSuit(meld('3m 4s 5p')), isNull);
      expect(repairMeldSuit(meld('1z 2z 3z')), isNull);
    });

    test('손패 10장이면 울기로 고치고 표시패로 쓰지 않는다', () {
      final r = sortMelds([meld('6s 7m 8m')], 10);
      expect(r.melds.single.type, ReadMeldType.chi);
      expect(r.stray, isEmpty);
      expect(r.notes.single, contains('6m 7m 8m'));
    });

    test('손패 13장이면 모서리에 둔 표시패 그대로(4통 4통 7만)', () {
      final r = sortMelds([meld('4p 4p 7m')], 13);
      expect(r.melds, isEmpty);
      expect(r.stray.map((t) => t.code), ['4p', '4p', '7m']);
      // 종류만 고치면 치가 되는 묶음도 장수가 안 맞으면 표시패다.
      expect(sortMelds([meld('6s 7m 8m')], 13).stray.length, 3);
    });

    test('장수로 보아 울기인데 못 고치면 표시패로도 안 쓰고 경고만', () {
      final r = sortMelds([meld('4p 4p 7m')], 10);
      expect(r.melds, isEmpty);
      expect(r.stray, isEmpty);
      expect(r.notes.single, contains('판독을 고쳐'));
    });

    test('갤러리 실험 장면: 고친 울기로 리치 불가·표시패 칸 도라, 하네만 18000', () {
      final g = _game();
      final hand = HandReading(
        tiles: [for (final c in '1m 2m 3m 4m 0m 6m 7m 8m 9m 2z'.split(' ')) ReadTile.fromCode(c, 0.99)!],
        melds: [sortMelds([meld('6s 7m 8m')], 10).melds.single.toReadMeld()],
      );
      final center = CenterReading.fromJson({
        'dora_indicators': [
          {'tile': '4p', 'conf': 0.99},
          {'tile': '4p', 'conf': 0.99},
          {'tile': '7m', 'conf': 0.99},
        ],
        'dora_from': 'dealerZone',
        'riichi': {'bottom': true, 'right': true, 'top': true, 'left': false},
        'riichi_conf': {'bottom': 0.9, 'right': 0.9, 'top': 0.9, 'left': 0.0},
        'last_discards': {'right': '2z', 'top': '3z', 'left': '7z'},
      });
      final m = mergeReading(hand: hand, center: center, winnerSide: Side.bottom, game: g, seats: _seats);
      expect(m.hasFlag(MergeIssue.riichiImpossible), isTrue);
      expect(m.hasFlag(MergeIssue.meldUncertain), isTrue);
      expect(m.situation.riichi, isFalse);
      expect(m.situation.doraIndicators, [for (final c in ['4p', '4p', '7m']) Tiles.parse(c)]);
      expect(m.loser, 1);
      final r = calculate(m.hand!, m.situation);
      expect(r.isValid, isTrue, reason: r.error);
      expect(r.han, 6);
      expect(r.payment.total, 18000);
    });
  });
}
