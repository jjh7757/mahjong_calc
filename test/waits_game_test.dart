import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/score.dart' show basePoints;
import 'package:mahjong_calc/engine/waits.dart';
import 'package:mahjong_calc/game/game.dart';

void main() {
  group('대기패', () {
    test('양면 대기 두 장', () {
      // 123m 456p 789s 23m 55p → 1m, 4m 대기
      final w = findWaits(parseTiles('123m456p789s23m55p').tiles, const [],
          const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(w.map((x) => Tiles.toCode(x.tile)).toList(), ['1m', '4m']);
      expect(w.every((x) => x.ron.isValid), isTrue); // 핑후
    });

    test('역 없는 대기는 론은 무효, 쯔모는 멘젠 쯔모로 유효', () {
      // 123m 456p 789s 24m 55p → 3m 간짱 대기, 멘젠이라 쯔모만 역
      final w = findWaits(parseTiles('123m456p789s24m55p').tiles, const [],
          const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(w.length, 1);
      expect(Tiles.toCode(w.first.tile), '3m');
      expect(w.first.ron.isValid, isFalse);
      expect(w.first.tsumo.isValid, isTrue);
    });

    test('국사무쌍 13면', () {
      final w = findWaits(parseTiles('19m19p19s1234567z').tiles, const [],
          const Situation(isTsumo: false));
      expect(w.length, 13);
    });

    test('노텐이면 빈 목록', () {
      final w = findWaits(parseTiles('159m159p159s123z4z').tiles, const [],
          const Situation(isTsumo: false));
      expect(w, isEmpty);
    });

    test('울었을 때 손패 장수', () {
      final w = findWaits(parseTiles('456p789s23m55s').tiles,
          [Meld.chi(Tiles.parse('2m'))], const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(w.map((x) => Tiles.toCode(x.tile)).toList(), ['1m', '4m']);
    });
  });

  group('대국', () {
    Game newGame({GameSettings settings = const GameSettings()}) => Game(
          id: 'g',
          startedAt: DateTime(2026, 10, 22),
          settings: settings,
          names: const ['A', 'B', 'C', 'D'],
        );

    test('자 론: 방총자만 지불, 친 유지 안 함', () {
      final g = newGame();
      g.win(winner: 1, loser: 2, isTsumo: false,
          payment: paymentFor(han: 3, fu: 40, isDealer: false, isTsumo: false, honba: 0));
      expect(g.scores, [25000, 30200, 19800, 25000]);
      expect(g.dealer, 1);
      expect(g.roundNumber, 2);
      expect(g.honba, 0);
    });

    test('친 쯔모: 각자 지불, 연장 + 본장', () {
      final g = newGame();
      g.win(winner: 0, isTsumo: true,
          payment: paymentFor(han: 4, fu: 30, isDealer: true, isTsumo: true, honba: 0));
      // 4판 30부 친 쯔모 3900 올
      expect(g.scores, [25000 + 11700, 21100, 21100, 21100]);
      expect(g.dealer, 0);
      expect(g.honba, 1);
      expect(g.roundLabel, '동1국 1본장');
    });

    test('리치봉과 본장이 화료자에게', () {
      final g = newGame();
      g.declareRiichi(3);
      expect(g.scores[3], 24000);
      expect(g.riichiSticks, 1);
      g.draw({3}); // 3만 텐파이: +3000, 나머지 -1000, 본장 1, 친 교체
      expect(g.scores, [24000, 24000, 24000, 27000]);
      expect(g.honba, 1);
      expect(g.dealer, 1);
      g.win(winner: 2, loser: 0, isTsumo: false,
          payment: paymentFor(han: 1, fu: 30, isDealer: false, isTsumo: false, honba: g.honba));
      // 1000 + 300(본장) + 1000(공탁)
      expect(g.scores[2], 24000 + 1300 + 1000);
      expect(g.scores[0], 24000 - 1300);
      expect(g.riichiSticks, 0);
      expect(g.honba, 0);
    });

    test('유국 때 입력한 리치는 공탁에 남아 다음 국으로', () {
      final g = newGame();
      g.declareRiichi(1); // 유국 창에서 고른 새 리치
      g.draw({1, 2}); // 1·2 텐파이: +1500, 0·3 -1500
      expect(g.scores, [23500, 25500, 26500, 23500]); // 1: -1000(리치) +1500
      expect(g.riichiSticks, 1);
      expect(g.riichiSeats, isEmpty);
      expect(g.events.map((e) => e.kind), ['riichi', 'draw']);
    });

    test('유국만관(자): 친 4000·자 2000씩, 노텐 벌점·본장 없음, 공탁 그대로', () {
      final g = newGame();
      g.declareRiichi(3);
      g.honba = 2;
      g.draw({0, 3}, nagashi: {1}); // 친(0) 텐파이 → 연장
      expect(g.scores, [21000, 33000, 23000, 22000]); // 3: 리치 -1000, 만관 -2000
      expect(g.riichiSticks, 1);
      expect(g.dealer, 0);
      expect(g.honba, 3);
      expect(g.events.last.description, contains('유국만관'));
    });

    test('유국만관(친)과 자가 같이 나오면 둘 다 받는다', () {
      final g = newGame();
      g.draw({}, nagashi: {0, 2}); // 친: 4000×3, 자(2): 친 4000 + 2000×2
      expect(g.scores, [25000 + 12000 - 4000, 25000 - 4000 - 2000, 25000 - 4000 + 8000, 25000 - 4000 - 2000]);
      expect(g.dealer, 1);
    });

    test('유국 전원 노텐이면 점수 이동 없음, 친 교체', () {
      final g = newGame();
      g.draw({});
      expect(g.scores, [25000, 25000, 25000, 25000]);
      expect(g.dealer, 1);
      expect(g.honba, 1);
    });

    test('국 진행: 동4 다음은 남1', () {
      final g = newGame();
      for (var i = 0; i < 4; i++) {
        g.draw({});
      }
      expect(g.roundWind, 1);
      expect(g.roundNumber, 1);
      expect(g.dealer, 0);
    });

    test('정산: 우마 20-10, 오카 20, 오사육입', () {
      final g = newGame();
      g.scores.setAll(0, [42300, 28600, 17500, 11600]);
      final s = g.settle();
      expect(s.map((x) => x.name).toList(), ['A', 'B', 'C', 'D']);
      // A: (42300-30000)=12.3→12 +20 +20(오카) = 52
      // B: -1.4→-1 +10 = 9
      // C: -12.5→-12(500 이하 버림) -10 = -22
      // D: -18.4→-18 -20 = -38  (합 1 — 오사육입 오차는 룰대로 둔다)
      expect(s[0].score, 52);
      expect(s[1].score, 9);
      expect(s[2].score, -22);
      expect(s[3].score, -38);
    });

    test('정산 동점은 기동 자리 순', () {
      final g = newGame();
      g.scores.setAll(0, [25000, 25000, 25000, 25000]);
      final s = g.settle();
      expect(s.map((x) => x.seat).toList(), [0, 1, 2, 3]);
      expect(s[0].score, -5 + 20 + 20);
    });

    test('직렬화 왕복', () {
      final g = newGame();
      g.declareRiichi(0);
      g.win(winner: 0, isTsumo: true,
          payment: paymentFor(han: 2, fu: 30, isDealer: true, isTsumo: true, honba: 0));
      final back = Game.fromJson(g.toJson());
      expect(back.scores, g.scores);
      expect(back.events.length, 2);
      expect(back.honba, 1);
    });

    test('역만 지불액', () {
      final p = yakumanPaymentFor(count: 1, isDealer: false, isTsumo: false, honba: 0);
      expect(p.ron, 32000);
      expect(basePoints(13, 30, RuleSet.standard).base, 8000);
    });
  });
}
