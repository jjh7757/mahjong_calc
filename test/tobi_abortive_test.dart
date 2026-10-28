import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/score.dart' show payment;
import 'package:mahjong_calc/game/game.dart';

Game _game({List<int>? scores}) => Game(
      id: 't',
      startedAt: DateTime(2026, 10, 27),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      scores: scores,
    );

void main() {
  group('토비', () {
    test('점수가 0 미만이 되면 anyBusted, 마이너스는 그대로', () {
      final g = _game(scores: [25000, 7000, 25000, 25000]);
      expect(g.anyBusted, isFalse);
      // 자 역만 론 32000: B 7000 → -25000
      g.win(winner: 2, loser: 1, isTsumo: false, payment: payment(8000, const Situation(isTsumo: false, seatWind: Tiles.south)));
      expect(g.scores[1], -25000);
      expect(g.anyBusted, isTrue);
      expect(g.bustedSeats, [1]);
      // 정산은 마이너스 점수 그대로 한다.
      final last = g.settle().firstWhere((s) => s.seat == 1);
      expect(last.points, -25000);
      expect(last.rank, 4);
    });

    test('정확히 0 은 토비가 아니다', () {
      final g = _game(scores: [25000, 1000, 25000, 25000]);
      g.win(winner: 2, loser: 1, isTsumo: false, payment: payment(250, const Situation(isTsumo: false, seatWind: Tiles.south)));
      expect(g.scores[1], 0);
      expect(g.anyBusted, isFalse);
    });

    test('노텐 벌점으로도 토비', () {
      final g = _game(scores: [25000, 500, 25000, 25000]);
      g.draw({0});
      expect(g.scores[1], -500);
      expect(g.bustedSeats, [1]);
    });

    test('둘이 마이너스면 낮은 점수부터', () {
      final g = _game(scores: [-100, -3000, 50000, 25000]);
      expect(g.bustedSeats, [1, 0]);
    });
  });

  group('도중 유국', () {
    test('구종구패: 점수 그대로, 친 유지, 본장 +1, 공탁 유지', () {
      final g = _game()..declareRiichi(2);
      expect(g.riichiSticks, 1);
      g.abortiveDraw('구종구패');
      expect(g.scores, [25000, 25000, 24000, 25000]);
      expect(g.dealer, 0);
      expect(g.honba, 1);
      expect(g.riichiSticks, 1);
      expect(g.riichiSeats, isEmpty);
      expect(g.events.last.description, '도중 유국 (구종구패)');
    });

    test('사가리치: 점수판에 없던 리치를 공탁에 넣고 도중 유국', () {
      final g = _game()..declareRiichi(0);
      g.fourRiichiDraw();
      expect(g.scores, [24000, 24000, 24000, 24000]);
      expect(g.riichiSticks, 4);
      expect(g.honba, 1);
      expect(g.dealer, 0);
      expect(g.events.last.description, '도중 유국 (사가리치)');
    });

    test('사가리치: 1000점 미만인 사람은 리치를 넣지 않는다', () {
      final g = _game(scores: [25000, 500, 25000, 25000]);
      g.fourRiichiDraw();
      expect(g.scores[1], 500);
      expect(g.riichiSticks, 3);
      expect(g.anyBusted, isFalse);
    });

    test('사유 목록', () {
      expect(Game.abortiveReasons, ['구종구패', '사풍연타', '사깡산료', '사가리치']);
    });
  });

  group('아가리야메·텐파이야메(작혼식: 자동)', () {
    // 반장전 남4국: 장풍 1, 4국, 친 = 자리 3.
    Game lastRound({List<int>? scores, GameSettings settings = const GameSettings()}) => Game(
          id: 'l',
          startedAt: DateTime(2026, 10, 27),
          settings: settings,
          names: const ['A', 'B', 'C', 'D'],
          scores: scores,
          roundWind: 1,
          roundNumber: 4,
          dealer: 3,
        );
    final dealerTsumo = payment(1000, const Situation(isTsumo: true, seatWind: Tiles.east)); // 친 2000 올(+6000)

    test('올라스 친 쯔모로 1위면 종료, 국은 그대로', () {
      final g = lastRound(scores: [26000, 24000, 20000, 30000]);
      expect(g.isLastRound, isTrue);
      g.win(winner: 3, isTsumo: true, payment: dealerTsumo);
      expect(g.scores[3], 36000);
      expect(g.endedBy, '아가리야메');
      expect(g.isOver, isTrue);
      expect(g.roundLabel, '남4국'); // 연장(본장 +1) 하지 않음
      expect(g.events.last.kind, 'end');
      expect(g.endNote, contains('D 1위'));
    });

    test('친이 1위가 아니면 평소처럼 연장', () {
      final g = lastRound(scores: [40000, 20000, 20000, 20000]);
      g.win(winner: 3, isTsumo: true, payment: dealerTsumo);
      expect(g.endedBy, isNull);
      expect(g.honba, 1);
      expect(g.dealer, 3);
    });

    test('1위라도 반환점 미만이면 끝나지 않는다(서입)', () {
      final g = lastRound(scores: [26000, 26000, 25000, 23000]);
      g.win(winner: 3, isTsumo: true, payment: dealerTsumo);
      expect(g.scores[3], 29000);
      expect(g.rankOf(3), 1);
      expect(g.endedBy, isNull);
      expect(g.honba, 1);
    });

    test('올라스가 아니면 적용 없음', () {
      final g = Game(
        id: 'e',
        startedAt: DateTime(2026, 10, 27),
        settings: const GameSettings(),
        names: const ['A', 'B', 'C', 'D'],
        scores: [20000, 20000, 20000, 40000],
        roundWind: 1,
        roundNumber: 3,
        dealer: 2,
      );
      g.win(winner: 2, isTsumo: true, payment: dealerTsumo);
      expect(g.endedBy, isNull);
    });

    test('텐파이야메: 유국에 친 텐파이·벌점 정산 뒤 1위면 종료', () {
      final g = lastRound(scores: [31000, 23000, 16000, 30000]);
      g.draw({3}); // 친 혼자 텐파이 +3000 → 33000, A 30000
      expect(g.scores, [30000, 22000, 15000, 33000]);
      expect(g.endedBy, '텐파이야메');
      expect(g.roundLabel, '남4국');
    });

    test('텐파이야메: 벌점 뒤에도 2위면 연장', () {
      final g = lastRound(scores: [40000, 20000, 10000, 30000]);
      g.draw({0, 3}); // 둘 다 +1500
      expect(g.endedBy, isNull);
      expect(g.honba, 1);
      expect(g.dealer, 3);
    });

    test('동점이면 기동 자리가 앞선다', () {
      // 유국 뒤 A 31000 = D 31000 이면 A(자리 0) 가 1위라 끝나지 않는다.
      final g = lastRound(scores: [32000, 24000, 17000, 28000]);
      g.draw({3}); // A 31000, D 31000
      expect(g.scores[3], 31000);
      expect(g.rankOf(3), 2);
      expect(g.endedBy, isNull);
    });

    test('설정을 끄면 적용 없음', () {
      final g = lastRound(
          scores: [26000, 24000, 20000, 30000], settings: const GameSettings(agariYame: false, tenpaiYame: false));
      g.win(winner: 3, isTsumo: true, payment: dealerTsumo);
      expect(g.endedBy, isNull);
      expect(g.honba, 1);
    });

    test('동시 론에 친이 끼어 1위면 종료', () {
      final g = lastRound(scores: [20000, 25000, 25000, 30000]);
      g.multiRon(
        loser: 0,
        payments: {
          3: payment(1000, const Situation(isTsumo: false, seatWind: Tiles.east)),
          1: payment(1000, const Situation(isTsumo: false, seatWind: Tiles.south)),
        },
        summaries: const {3: '1판 30부', 1: '1판 30부'},
      );
      expect(g.endedBy, '아가리야메');
    });

    test('JSON 왕복에 endedBy·설정이 남는다', () {
      final g = lastRound(scores: [26000, 24000, 20000, 30000]);
      g.win(winner: 3, isTsumo: true, payment: dealerTsumo);
      final back = Game.fromJson(g.toJson());
      expect(back.endedBy, '아가리야메');
      expect(back.settings.agariYame, isTrue);
      expect(Game.fromJson(g.toJson()..['settings'] = (g.toJson()['settings'] as Map)..remove('agariYame')).settings.agariYame, isTrue);
    });
  });

  group('정규 종료·서입·연장전 종료(작혼식)', () {
    Game at({required int wind, required int number, required int dealer, List<int>? scores, GameSettings settings = const GameSettings()}) =>
        Game(
          id: 'o',
          startedAt: DateTime(2026, 10, 27),
          settings: settings,
          names: const ['A', 'B', 'C', 'D'],
          scores: scores,
          roundWind: wind,
          roundNumber: number,
          dealer: dealer,
        );
    final ron1000 = payment(1000, const Situation(isTsumo: false, seatWind: Tiles.south)); // 자 론 4000
    final tsumo1000 = payment(1000, const Situation(isTsumo: true, seatWind: Tiles.south)); // 자 쯔모 1000/2000

    test('남4국에 자가 화료해 1위가 반환점 이상이면 종료, 국은 그대로', () {
      final g = at(wind: 1, number: 4, dealer: 3, scores: [28000, 24000, 24000, 24000]);
      g.win(winner: 0, loser: 1, isTsumo: false, payment: ron1000);
      expect(g.scores[0], 32000);
      expect(g.endedBy, '종료');
      expect(g.isOver, isTrue);
      expect(g.roundLabel, '남4국');
      expect(g.events.last.description, '종료 — 1위 A 32000');
      expect(g.endLabel, '대국 종료');
    });

    test('남4국 뒤 1위가 반환점 미만이면 서입(서1국), 기록에 남는다', () {
      final g = at(wind: 1, number: 4, dealer: 3, scores: [26000, 25000, 25000, 24000]);
      g.win(winner: 0, loser: 1, isTsumo: false, payment: payment(300, const Situation(isTsumo: false, seatWind: Tiles.south))); // 1000
      expect(g.scores[0], 27200);
      expect(g.endedBy, isNull);
      expect(g.isOvertime, isTrue);
      expect(g.roundLabel, '서1국');
      expect(g.dealer, 0);
      expect(g.events.last.kind, 'note');
      expect(g.events.last.description, contains('서입'));
    });

    test('서입 뒤 매 국 끝에 누군가 반환점 이상이면 연장전 종료(친 연장이어도)', () {
      final g = at(wind: 2, number: 1, dealer: 0, scores: [29000, 25000, 24000, 22000]);
      g.win(winner: 0, isTsumo: true, payment: payment(1000, const Situation(isTsumo: true, seatWind: Tiles.east))); // 친 +6000
      expect(g.scores[0], 35000);
      expect(g.endedBy, '연장전 종료');
      expect(g.roundLabel, '서1국');
    });

    test('서4국이 친 교체로 끝나면 반환점 미만이어도 종료(북입 없음)', () {
      final g = at(wind: 2, number: 4, dealer: 3, scores: [26000, 25000, 25000, 24000]);
      g.draw({}); // 전원 노텐, 친 교체
      expect(g.endedBy, '연장전 종료');
      expect(g.roundLabel, '서4국');
    });

    test('서4국 친 텐파이 유국이고 반환점 미만이면 연장', () {
      final g = at(wind: 2, number: 4, dealer: 3, scores: [26000, 25000, 25000, 24000]);
      g.draw({3}); // D +3000 → 27000, 나머지 −1000
      expect(g.endedBy, isNull);
      expect(g.roundLabel, '서4국 1본장');
    });

    test('서입을 끄면 남4국에서 무조건 종료', () {
      final g = at(wind: 1, number: 4, dealer: 3, scores: [26000, 25000, 25000, 24000], settings: const GameSettings(overtime: false));
      g.draw({});
      expect(g.endedBy, '종료');
      expect(g.roundLabel, '남4국');
    });

    test('남4국 친 연장(화료했지만 1위 아님)은 판정하지 않는다', () {
      final g = at(wind: 1, number: 4, dealer: 3, scores: [40000, 20000, 20000, 20000]);
      g.win(winner: 3, isTsumo: true, payment: payment(1000, const Situation(isTsumo: true, seatWind: Tiles.east)));
      expect(g.endedBy, isNull);
      expect(g.roundLabel, '남4국 1본장');
    });

    test('동풍전: 동4국 뒤 반환점 미만이면 남입, 남4국이 끝나면 종료', () {
      final g = at(wind: 0, number: 4, dealer: 3, scores: [26000, 25000, 25000, 24000], settings: const GameSettings(eastOnly: true));
      g.draw({});
      expect(g.roundLabel, '남1국 1본장'); // 유국이라 본장 +1
      expect(g.events.last.description, contains('남입'));
      final g2 = at(wind: 1, number: 4, dealer: 3, scores: [26000, 25000, 25000, 24000], settings: const GameSettings(eastOnly: true));
      g2.draw({});
      expect(g2.endedBy, '연장전 종료');
    });

    test('끝날 때 남은 공탁은 1위에게', () {
      final g = at(wind: 1, number: 4, dealer: 3, scores: [31000, 24000, 24000, 21000])..declareRiichi(1);
      expect(g.riichiSticks, 1);
      g.draw({}); // 전원 노텐 → 종료(A 31000 ≥ 30000)
      expect(g.endedBy, '종료');
      expect(g.riichiSticks, 0);
      expect(g.scores[0], 32000);
      expect(g.events.last.description, '남은 공탁 1 → 1위 A');
    });

    test('도중 유국도 연장전에서는 종료 판정을 거친다(점수 변화 없으면 계속)', () {
      final g = at(wind: 2, number: 2, dealer: 1, scores: [26000, 25000, 25000, 24000]);
      g.abortiveDraw('구종구패');
      expect(g.endedBy, isNull);
      expect(g.roundLabel, '서2국 1본장');
    });

    test('아가리야메 뒤에는 정규 종료 판정이 겹치지 않는다', () {
      final g = at(wind: 1, number: 4, dealer: 3, scores: [26000, 24000, 20000, 30000]);
      g.win(winner: 3, isTsumo: true, payment: tsumo1000);
      expect(g.endedBy, '아가리야메');
      expect(g.events.where((e) => e.kind == 'end').length, 1);
    });

    test('JSON 왕복에 설정이 남고 옛 저장값은 켬', () {
      final j = const GameSettings(overtime: false).toJson();
      expect(GameSettings.fromJson(j).overtime, isFalse);
      j.remove('overtime');
      expect(GameSettings.fromJson(j).overtime, isTrue);
    });
  });
}
