// Game.handStart — 패보에 남길 국 시작 점수 · 공탁(docs/paifu_fill_scores_tsumogiri_design_1122.md 4절 A 명세).
// 국 시작 점수 = scores[s] + (이 국 리치면 1000), 국 시작 공탁 = riichiSticks − 이 국 리치 수.
// 경우마다 "국 시작 점수 합 + 공탁 × 1000 = 시작 점수 × 4" 도 본다.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/score.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

Game _game({int startPoints = 25000}) => Game(
      id: 'g',
      startedAt: DateTime(2026, 11, 22),
      settings: GameSettings(startPoints: startPoints, returnPoints: startPoints + 5000),
      names: const ['A', 'B', 'C', 'D'],
    );

Payment _ron(int v) => Payment(ron: v, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: v);

/// 국 시작 값과 불변식을 함께 본다.
void _expectStart(Game g, List<int> scores, int kyotaku, {String? reason}) {
  final st = g.handStart;
  expect(st, isNotNull, reason: reason);
  expect(st!.scores, scores, reason: reason);
  expect(st.kyotaku, kyotaku, reason: reason);
  expect(st.scores.reduce((a, b) => a + b) + st.kyotaku * 1000, g.settings.startPoints * 4, reason: '불변식 ${reason ?? ''}');
}

void main() {
  group('리치 수', () {
    test('리치 0명: 지금 점수 그대로, 공탁 0', () {
      final g = _game();
      _expectStart(g, [25000, 25000, 25000, 25000], 0);
    });

    test('리치 1명: 점수판 리치로 빠진 1000점을 되돌리고 그 봉은 공탁에서 뺀다', () {
      final g = _game()..declareRiichi(1);
      expect(g.scores, [25000, 24000, 25000, 25000]);
      expect(g.riichiSticks, 1);
      _expectStart(g, [25000, 25000, 25000, 25000], 0);
    });

    test('리치 2명', () {
      final g = _game()
        ..declareRiichi(3)
        ..declareRiichi(0);
      expect(g.scores, [24000, 25000, 25000, 24000]);
      _expectStart(g, [25000, 25000, 25000, 25000], 0);
    });

    test('시작 점수 30000 설정', () {
      final g = _game(startPoints: 30000)..declareRiichi(2);
      _expectStart(g, [30000, 30000, 30000, 30000], 0);
    });
  });

  group('국 넘김', () {
    test('유국 뒤 넘어온 봉: 다음 국은 riichiSeats 가 비고 봉은 공탁으로 남는다(새 리치 0 / 1)', () {
      final g = _game()..declareRiichi(1);
      g.draw({1}); // B 혼자 텐파이: 노텐 셋이 1000씩.
      expect(g.riichiSeats, isEmpty);
      expect(g.riichiSticks, 1);
      expect(g.honba, 1);
      _expectStart(g, [24000, 27000, 24000, 24000], 1, reason: '새 리치 0');

      g.declareRiichi(2);
      _expectStart(g, [24000, 27000, 24000, 24000], 1, reason: '새 리치 1(C)');

      // 넘어온 봉 주인(B)이 이 국에 다시 리치해도 넘어온 봉은 공탁 쪽.
      g.declareRiichi(1);
      expect(g.riichiSticks, 3);
      _expectStart(g, [24000, 27000, 24000, 24000], 1, reason: '새 리치 2(C · 넘어온 봉 주인 B)');
    });

    test('도중 유국(사가리치)으로 넘어온 봉 4개', () {
      final g = _game()
        ..declareRiichi(0)
        ..declareRiichi(1);
      g.fourRiichiDraw(); // 남은 두 자리도 리치봉을 넣고 유국.
      expect(g.riichiSticks, 4);
      _expectStart(g, [24000, 24000, 24000, 24000], 4);
    });

    test('본장: 친 화료로 본장이 늘어도 국 시작 값에는 안 들어간다, 화료가 공탁을 가져가면 다음 국 공탁 0', () {
      final g = _game()..declareRiichi(2);
      g.draw({}); // 전원 노텐: 점수 이동 없음, 친 노텐이라 친이 바뀌고 본장 1, 공탁 1 넘어감.
      expect(g.honba, 1);
      _expectStart(g, [25000, 25000, 24000, 25000], 1);

      // 이 국 친(자리 1)이 론 화료: 1500 + 본장 300, 공탁 1 을 가져간다.
      expect(g.dealer, 1);
      g.declareRiichi(3);
      g.win(winner: 1, payment: _ron(1800), isTsumo: false, loser: 0);
      expect(g.honba, 2, reason: '친 연장');
      expect(g.riichiSticks, 0);
      // A −1800, B +1800 + 공탁 2000(넘어온 1 + D 리치 1), D −1000.
      _expectStart(g, [23200, 28800, 24000, 24000], 0);
    });

    test('더블론: 공탁은 머리 화료자가 가져가고 다음 국 공탁 0', () {
      final g = _game()..declareRiichi(0);
      g.draw({0});
      g.declareRiichi(2);
      // 이 국(친 0 연장, 본장 1): 자리 3 이 쏘고 0 · 1 이 론. 머리는 0(3 다음).
      g.multiRon(loser: 3, payments: {0: _ron(2900), 1: _ron(1000)});
      expect(g.riichiSticks, 0);
      // A 27000 + 2900 + 본장 300 + 공탁 2000, B 24000 + 1000, C 24000 − 1000(리치), D 24000 − 2900 − 1000 − 300.
      _expectStart(g, [32200, 25000, 23000, 19800], 0);
    });

    test('한 반장 흉내: 국마다 국 시작 값이 손계산과 같다', () {
      final g = _game();
      // 동1국: 리치 없음 → A(친) 론 2900 ← C.
      _expectStart(g, [25000, 25000, 25000, 25000], 0, reason: '동1국');
      g.win(winner: 0, payment: _ron(2900), isTsumo: false, loser: 2);
      // 동1국 1본장: B 리치, 유국(B · C 텐파이).
      _expectStart(g, [27900, 25000, 22100, 25000], 0, reason: '동1국 1본장');
      g.declareRiichi(1);
      g.draw({1, 2});
      // 동2국 2본장: 공탁 1 넘어옴. D 리치, C 리치, D 론 ← A 3900(+본장 600).
      expect(g.roundLabel, '동2국 2본장');
      _expectStart(g, [26400, 25500, 23600, 23500], 1, reason: '동2국 2본장');
      g.declareRiichi(3);
      g.declareRiichi(2);
      g.win(winner: 3, payment: _ron(4500), isTsumo: false, loser: 0);
      // 동3국: A −4500, D −1000 + 4500 + 3000, C −1000.
      expect(g.roundLabel, '동3국');
      _expectStart(g, [21900, 25500, 22600, 30000], 0, reason: '동3국');
    });
  });

  group('화료 사진 리치(대국에 반영 전 · 후)', () {
    test('사진에서 읽은 리치는 저장 때 아직 반영 전 — 넣은 뒤에 불러도 같은 값', () {
      final g = _game()..declareRiichi(1); // 점수판 리치
      final before = g.handStart!;
      // "대국에 반영" 이 사진 리치(자리 2)를 넣는다.
      for (final s in g.autoRiichiCandidates({2}, winner: 0, winnerRiichi: false)) {
        g.declareRiichi(s, fromPhoto: true);
      }
      expect(g.riichiSticks, 2);
      final after = g.handStart!;
      expect(after.scores, before.scores);
      expect(after.kyotaku, before.kyotaku);
      _expectStart(g, [25000, 25000, 25000, 25000], 0);
    });
  });

  group('되돌리기', () {
    test('리치 뒤 되돌리기: 리치 전 상태와 같은 국 시작 값', () {
      final g = _game()..declareRiichi(1);
      g.draw({1});
      final start = g.handStart!;
      final cp = g.checkpoint();
      g.declareRiichi(0);
      g.rewindTo(cp);
      expect(g.riichiSeats, isEmpty);
      _expectStart(g, start.scores, start.kyotaku);
    });

    test('국 끝 되돌리기: 앞 국(리치 남은 상태)으로 돌아가면 앞 국 시작 값', () {
      final g = _game()..declareRiichi(2);
      final cp = g.checkpoint();
      g.win(winner: 0, payment: _ron(1000), isTsumo: false, loser: 3);
      _expectStart(g, [27000, 25000, 24000, 24000], 0);
      g.rewindTo(cp);
      expect(g.riichiSeats, {2});
      _expectStart(g, [25000, 25000, 25000, 25000], 0);
    });

    test('GameStore 흐름(mutate · rewind · redo)과 저장 왕복', () {
      SharedPreferences.setMockInitialValues({});
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
      addTearDown(() {
        if (gameStore.current != null) gameStore.discardCurrent();
      });
      gameStore.mutate((g) => g.declareRiichi(3));
      gameStore.mutate((g) => g.draw({3}));
      gameStore.mutate((g) => g.declareRiichi(0));
      final g = gameStore.current!;
      _expectStart(g, [24000, 24000, 24000, 27000], 1);
      gameStore.rewind();
      expect(g.riichiSeats, isEmpty);
      _expectStart(g, [24000, 24000, 24000, 27000], 1);
      gameStore.redo();
      expect(g.riichiSeats, {0});
      _expectStart(g, [24000, 24000, 24000, 27000], 1);
      final loaded = Game.fromJson(jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>);
      _expectStart(loaded, [24000, 24000, 24000, 27000], 1);
    });
  });

  group('중간부터 · 기록 정정', () {
    test('중간부터 시작한 대국의 공탁은 넘어온 공탁', () {
      final g = Game.resumed(
        id: 'r',
        startedAt: DateTime(2026, 11, 22),
        settings: const GameSettings(),
        names: const ['A', 'B', 'C', 'D'],
        scores: const [31000, 20000, 25000, 22000],
        roundWind: 1,
        roundNumber: 3,
        honba: 1,
        riichiSticks: 2,
      );
      _expectStart(g, [31000, 20000, 25000, 22000], 2);
      g.declareRiichi(1);
      _expectStart(g, [31000, 20000, 25000, 22000], 2);
    });

    test('국 중 정정으로 봉을 이 국 리치 수보다 적게 고치면 모름(null)', () {
      final g = _game()..declareRiichi(1);
      g.correct(delta: const [0, 0, 0, 0], riichiSticks: 0, reason: '봉 정정');
      expect(g.riichiSeats, {1});
      expect(g.riichiSticks, 0);
      expect(g.handStart, isNull);
    });
  });
}
