import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
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

/// 간짱 대기 멘젠 론이라 리치 없이는 역이 없다.
HandReading _noYaku() => HandReading.fromJson({
      'tiles': [
        for (final c in '1m 3m 2p 3p 4p 5s 6s 7s 7p 8p 9p 9s 9s'.split(' ')) {'tile': c, 'conf': 0.99}
      ],
      'win_tile': {'tile': '2m', 'conf': 0.99},
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
        {Side winner = Side.right, Set<Side> tracked = const {}, Map<String, String?> last = const {}}) =>
    mergeReading(hand: hand, center: _center(sticks, last: last), winnerSide: winner, game: g, seats: _seats, trackedRiichi: tracked);

void main() {
  group('대국: 유국으로 남은 리치봉 주인', () {
    test('유국·도중 유국이면 남기고, 화료로 공탁이 넘어가면 비운다', () {
      final g = _game()..declareRiichi(1);
      expect(g.carriedStickSeats, isEmpty);
      g.draw({1});
      expect(g.carriedStickSeats, {1});
      expect(g.riichiSeats, isEmpty);
      expect(g.riichiSticks, 1);
      expect(g.unknownSticks, 0);

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

    test('주인을 모르는 공탁', () {
      expect(Game(id: 'g', startedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D'], riichiSticks: 2).unknownSticks, 2);
    });
  });

  group('병합: 남은 봉은 이번 판 리치의 증거가 아니다', () {
    late Game g;
    setUp(() {
      g = _game()..declareRiichi(1);
      g.draw({1});
    });

    test('봉 주인이 리치 없이 화료: 리치로 치지 않고 확인을 묻는다', () {
      final m = _merge(g, _pinfu(), {Side.right});
      expect(m.situation.riichi, isFalse);
      expect(m.hasFlag(MergeIssue.riichiCarried), isTrue);
      expect(m.hasFlag(MergeIssue.riichiMismatch), isFalse);
      expect(m.photoRiichiSeats, isEmpty);
      expect(
        autoRecordBlocker(
          warnings: const [],
          issues: [for (final f in m.flags) f.issue],
          otherWinners: 0,
          isTsumo: false,
          loser: 0,
          resultValid: true,
          paoBase: 0,
          gameOver: false,
          doraIndicators: 2,
          riichi: false,
        ),
        contains('riichiCarried'),
      );
    });

    test('봉 주인인데 리치 없이는 역이 없으면 리치로 본다', () {
      final m = _merge(g, _noYaku(), {Side.right}, last: const {'top': '2m'}); // 쯔모면 멘젠 쯔모 역이 있다
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiCarried), isTrue);
    });

    test('다른 사람 화료: 봉 주인에게 1000점을 또 걷지 않는다', () {
      final m = _merge(g, _pinfu(), {Side.right}, winner: Side.bottom);
      expect(m.situation.riichi, isFalse);
      expect(m.photoRiichiSeats, isEmpty);
      expect(g.autoRiichiCandidates(m.photoRiichiSeats, winner: 0, winnerRiichi: false), isEmpty);
      expect(m.hasFlag(MergeIssue.riichiCarried), isFalse);
    });

    test('다른 자리의 새 리치봉은 그대로 리치', () {
      final m = _merge(g, _pinfu(), {Side.right, Side.top}, winner: Side.bottom);
      expect(m.photoRiichiSeats, {2});
      expect(g.autoRiichiCandidates(m.photoRiichiSeats, winner: 0, winnerRiichi: false), {2});
    });

    test('봉 주인이 점수판에 다시 리치: 리치, 확인 없음', () {
      g.declareRiichi(1);
      final m = _merge(g, _pinfu(), {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiCarried), isFalse);
    });

    test('봉 주인 자리에서 추적이 변화를 봄: 리치로 보되 확인을 묻는다', () {
      final m = _merge(g, _pinfu(), {Side.right}, tracked: {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(m.photoRiichiSeats, {1});
      expect(m.hasFlag(MergeIssue.riichiCarried), isTrue);
    });

    test('남은 봉 없는 평소 리치는 그대로', () {
      final m = _merge(_game(), _pinfu(), {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiCarried), isFalse);
      expect(m.hasFlag(MergeIssue.riichiMismatch), isTrue);
    });

    test('공탁 주인을 모르면 사진 리치를 쓰되 확인을 묻는다', () {
      final resumed = Game(id: 'g', startedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D'], riichiSticks: 1);
      final m = _merge(resumed, _pinfu(), {Side.right});
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiCarried), isTrue);
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
      expect(tester.widget<CheckboxListTile>(find.byKey(const ValueKey('draw-tenpai-2'))).value, isTrue);
      expect(tester.widget<FilterChip>(find.byKey(const ValueKey('draw-riichi-2'))).selected, isTrue);

      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      final g = gameStore.current!;
      expect(g.riichiSticks, 1);
      expect(g.carriedStickSeats, {2});
      expect(g.scores[2], 25000 - 1000 + 3000);
    });
  });

  group('추적기: 전판 봉', () {
    const grid = GridZones.initial;
    const cols = 8, rows = 4;
    final frac = {for (final s in Side.values) s: 2 / (cols * rows)};
    final t0 = DateTime(2026, 10, 30, 12);
    DateTime at(int sec) => t0.add(Duration(seconds: sec));

    ZoneSnapshot snap(Side side, int shift) {
      final gray = Uint8List(cols * rows)..fillRange(0, cols * rows, 80 + shift);
      return ZoneSnapshot(box: grid.riverBand(side), cols: cols, rows: rows, gray: gray, white: Uint8List(cols * rows), whiteFrac: 0);
    }

    Map<Side, ZoneSnapshot> rivers() => {for (final s in Side.values) s: snap(s, 0)};
    Map<Side, ZoneSnapshot> strips(Set<Side> sticks) => {for (final s in Side.values) s: snap(s, sticks.contains(s) ? 40 : 0)};

    test('기록이 아는 남은 봉은 다른 자리 리치를 확정할 때 끼지 않고, 그 자리 띠가 바뀌면 남는다', () {
      final tr = RiverTracker(tileFrac: frac);
      // 아래 자리 봉이 꽂힌 채 시작.
      tr.onFrame(rivers(), strips({Side.bottom}), at(0));
      tr.onFrame(rivers(), strips({Side.bottom}), at(3));
      expect(tr.riichi, isEmpty);
      // 위 자리 새 리치. 서버는 보이는 봉을 모두 답한다.
      const read = {Side.bottom: true, Side.top: true, Side.left: false, Side.right: false};
      tr.onFrame(rivers(), strips({Side.bottom, Side.top}), at(6));
      final a1 = tr.onFrame(rivers(), strips({Side.bottom, Side.top}), at(9));
      expect(a1.length, 1);
      tr.onSticksRead(a1.single.frame, read, at(10));
      final a2 = tr.onFrame(rivers(), strips({Side.bottom, Side.top}), at(15));
      expect(a2.length, 1);
      tr.onSticksRead(a2.single.frame, read, at(16));
      expect(tr.riichiAt.keys, [Side.top]);
      expect(tr.riichiExcept({Side.bottom}), {Side.top});
      // 기록에 없는 봉은 추적 전에 한 리치로 본다(추적을 판 도중에 켠 경우).
      expect(tr.riichiExcept(const {}), {Side.bottom, Side.top});
      // 띠가 바뀌어 확정한 자리는 남은 봉 주인이어도 남는다(병합이 확인을 묻는다).
      expect(tr.riichiExcept({Side.bottom, Side.top}), {Side.top});
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
