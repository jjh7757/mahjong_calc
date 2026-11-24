import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/score.dart' show payment;
import 'package:mahjong_calc/game/game.dart';

/// 별(동호회 순위표): 화료 한 번마다 하네만 1 · 배만 2 · 삼배만 3 · 역만(헤아림 포함) 5 · 더블 10 · 트리플 15.
/// 만관 이하·유국만관 0, 동시 론은 화료자마다, 파오여도 화료자가 받는다.
/// 기대값은 규칙에서 손으로 정했다. 지불액은 실제 [payment] 로 만든다.
Game _game({int dealer = 0, int honba = 0}) => Game(
      id: 's',
      startedAt: DateTime(2026, 11, 24),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      dealer: dealer,
      honba: honba,
    );

Situation _sit({required bool dealer, required bool tsumo, int honba = 0}) =>
    Situation(isTsumo: tsumo, seatWind: dealer ? Tiles.east : Tiles.south, honba: honba);

List<int> _stars(Game g) => [for (var s = 0; s < 4; s++) g.starsOf(s)];

void main() {
  test('starsForBase 경계', () {
    expect(starsForBase(0), 0);
    expect(starsForBase(1920), 0); // 4판 30부
    expect(starsForBase(2000), 0); // 만관
    expect(starsForBase(2999), 0);
    expect(starsForBase(3000), 1); // 하네만
    expect(starsForBase(4000), 2); // 배만
    expect(starsForBase(5000), 0);
    expect(starsForBase(6000), 3); // 삼배만
    expect(starsForBase(8000), 5); // 역만 · 헤아림 역만
    expect(starsForBase(12000), 0);
    expect(starsForBase(16000), 10); // 더블 역만
    expect(starsForBase(24000), 15); // 트리플
    expect(starsForBase(48000), 30); // 역만 6개
  });

  group('실제 Payment 에서 기본점 되살리기', () {
    // (기본점, 친?, 쯔모?, 본장) → 별.
    const cases = [
      (2000, false, false, 0, 0),
      (2000, true, true, 2, 0),
      (1920, true, false, 0, 0), // 친 4판 30부 11600(올림)
      (1920, false, true, 2, 0), // 자 쯔모 2000/3900 + 본장
      (3000, false, false, 0, 1),
      (3000, true, false, 2, 1),
      (3000, false, true, 2, 1),
      (3000, true, true, 0, 1),
      (4000, true, true, 2, 2),
      (4000, false, false, 2, 2),
      (6000, false, true, 2, 3),
      (6000, true, false, 0, 3),
      (8000, false, true, 2, 5),
      (8000, true, false, 2, 5),
      (16000, true, true, 2, 10),
      (16000, false, false, 0, 10),
      (24000, false, true, 1, 15),
    ];
    for (final (base, dealer, tsumo, honba, want) in cases) {
      test('기본점 $base ${dealer ? '친' : '자'} ${tsumo ? '쯔모' : '론'} 본장 $honba → $want', () {
        final p = payment(base, _sit(dealer: dealer, tsumo: tsumo, honba: honba));
        expect(starsForPayment(p, winnerIsDealer: dealer), want);
      });
    }
  });

  group('Game.win 이 화료 사건에 별을 남긴다', () {
    test('자 론 하네만(6판) → 1', () {
      final g = _game();
      g.win(winner: 1, loser: 2, isTsumo: false, payment: paymentFor(han: 6, fu: 30, isDealer: false, isTsumo: false, honba: 0));
      expect(_stars(g), [0, 1, 0, 0]);
      expect(g.events.last.stars, [0, 1, 0, 0]);
    });

    test('친 쯔모 배만 본장 2 → 2', () {
      final g = _game(honba: 2);
      final p = paymentFor(han: 8, fu: 30, isDealer: true, isTsumo: true, honba: 2);
      expect(p.total, 24600);
      g.win(winner: 0, isTsumo: true, payment: p);
      expect(_stars(g), [2, 0, 0, 0]);
    });

    test('자 쯔모 삼배만 본장 2 → 3', () {
      final g = _game(honba: 2);
      g.win(winner: 3, isTsumo: true, payment: paymentFor(han: 11, fu: 30, isDealer: false, isTsumo: true, honba: 2));
      expect(_stars(g), [0, 0, 0, 3]);
    });

    test('친 론 만관 본장 2 · 자 론 3판 30부 → 0', () {
      final g = _game(honba: 2);
      g.win(winner: 0, loser: 1, isTsumo: false, payment: paymentFor(han: 5, fu: 30, isDealer: true, isTsumo: false, honba: 2));
      expect(_stars(g), [0, 0, 0, 0]);
      final h = _game();
      h.win(winner: 2, loser: 1, isTsumo: false, payment: paymentFor(han: 3, fu: 30, isDealer: false, isTsumo: false, honba: 0));
      expect(_stars(h), [0, 0, 0, 0]);
      // 화료 사건에는 0 으로라도 남는다.
      expect(h.events.last.stars, [0, 0, 0, 0]);
    });

    test('헤아림 역만(13판) → 5, 더블 역만 친 쯔모 → 10, 트리플 → 15', () {
      final g = _game();
      g.win(winner: 2, loser: 3, isTsumo: false, payment: paymentFor(han: 13, fu: 40, isDealer: false, isTsumo: false, honba: 0));
      expect(_stars(g), [0, 0, 5, 0]);

      final d = _game(honba: 1);
      d.win(winner: 0, isTsumo: true, payment: yakumanPaymentFor(count: 2, isDealer: true, isTsumo: true, honba: 1));
      expect(_stars(d), [10, 0, 0, 0]);

      final t = _game();
      t.win(winner: 1, loser: 0, isTsumo: false, payment: yakumanPaymentFor(count: 3, isDealer: false, isTsumo: false, honba: 0));
      expect(_stars(t), [0, 15, 0, 0]);
    });

    test('파오 역만: 화료자 5, 책임자 0 (쯔모 · 론)', () {
      final g = _game();
      final p = payment(8000, _sit(dealer: false, tsumo: true));
      final pao = payment(8000, _sit(dealer: false, tsumo: true));
      g.win(winner: 1, isTsumo: true, payment: p, paoSeat: 2, pao: pao);
      expect(g.scores, [25000, 57000, -7000, 25000]); // 파오가 실제로 걸렸는지
      expect(_stars(g), [0, 5, 0, 0]);

      final r = _game(honba: 1);
      final rp = payment(8000, _sit(dealer: false, tsumo: false, honba: 1));
      final rpao = payment(8000, _sit(dealer: false, tsumo: false));
      r.win(winner: 1, loser: 3, isTsumo: false, payment: rp, paoSeat: 2, pao: rpao);
      expect(r.scores, [25000, 57300, 9000, 8700]);
      expect(_stars(r), [0, 5, 0, 0]);
    });

    test('여러 국에 걸쳐 합산, 유국만관은 0', () {
      final g = _game();
      g.win(winner: 1, loser: 2, isTsumo: false, payment: paymentFor(han: 6, fu: 30, isDealer: false, isTsumo: false, honba: 0));
      // B 가 친이 되어 유국만관(친 연장, 본장 1).
      expect(g.dealer, 1);
      g.draw({1}, nagashi: {1});
      expect(g.events.last.stars, isNull);
      expect((g.dealer, g.honba), (1, 1));
      g.win(winner: 1, isTsumo: true, payment: paymentFor(han: 8, fu: 30, isDealer: true, isTsumo: true, honba: g.honba));
      expect(_stars(g), [0, 3, 0, 0]);
      expect(g.settle().firstWhere((r) => r.seat == 1).stars, 3);
      expect(g.settle().firstWhere((r) => r.seat == 0).stars, 0);
    });
  });

  group('동시 론', () {
    test('하네만 + 만관 → 1, 0 (본장이 있어도)', () {
      final g = _game(honba: 1);
      g.multiRon(loser: 0, payments: {
        1: payment(3000, _sit(dealer: false, tsumo: false)),
        2: payment(2000, _sit(dealer: false, tsumo: false)),
      });
      expect(_stars(g), [0, 1, 0, 0]);
    });

    test('친 하네만 + 자 배만 → 1, 2', () {
      final g = _game();
      g.multiRon(loser: 1, payments: {
        0: payment(3000, _sit(dealer: true, tsumo: false)),
        2: payment(4000, _sit(dealer: false, tsumo: false)),
      });
      expect(_stars(g), [1, 0, 2, 0]);
    });
  });

  test('되돌리기로 화료를 지우면 별도 빠진다', () {
    final g = _game();
    final c = g.checkpoint();
    g.win(winner: 1, loser: 2, isTsumo: false, payment: paymentFor(han: 8, fu: 30, isDealer: false, isTsumo: false, honba: 0));
    expect(g.starsOf(1), 2);
    g.rewindTo(c);
    expect(g.starsOf(1), 0);
    expect(g.settle().every((r) => r.stars == 0), isTrue);
  });

  test('Game.manual: 넘긴 별이 사건에 남고 정산에 나온다, 길이·음수 검사', () {
    final g = Game.manual(
      id: 'm',
      playedAt: DateTime(2026, 11, 24),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      scores: const [45000, 30000, 20000, 5000],
      stars: const [3, 0, 1, 0],
    );
    expect(_stars(g), [3, 0, 1, 0]);
    expect(g.settle().map((r) => (r.name, r.stars)).toList(), [('A', 3), ('B', 0), ('C', 1), ('D', 0)]);
    final none = Game.manual(
      id: 'n',
      playedAt: DateTime(2026, 11, 24),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      scores: const [25000, 25000, 25000, 25000],
    );
    expect(none.events.single.stars, isNull);
    expect(_stars(none), [0, 0, 0, 0]);
    expect(
        () => Game.manual(
            id: 'x', playedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D'],
            scores: const [25000, 25000, 25000, 25000], stars: const [1, 2, 3]),
        throwsArgumentError);
    expect(
        () => Game.manual(
            id: 'x', playedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D'],
            scores: const [25000, 25000, 25000, 25000], stars: const [1, -1, 0, 0]),
        throwsArgumentError);
  });

  group('JSON', () {
    test('왕복: 별이 그대로, 별 없는 사건은 키가 없다', () {
      final g = _game();
      g.declareRiichi(2);
      g.win(winner: 2, isTsumo: true, payment: paymentFor(han: 6, fu: 30, isDealer: false, isTsumo: true, honba: 0));
      final j = jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>;
      final events = (j['events'] as List).cast<Map<String, dynamic>>();
      expect(events.first.containsKey('stars'), isFalse); // 리치
      expect(events[1]['stars'], [0, 0, 1, 0]);
      final back = Game.fromJson(j);
      expect(_stars(back), [0, 0, 1, 0]);
      expect(back.events.first.stars, isNull);
    });

    test('stars 가 없는 옛 기록도 읽고 별은 0', () {
      final old = {
        'id': 'old',
        'startedAt': '2026-10-01T20:00:00.000',
        'settings': const GameSettings().toJson(),
        'names': ['A', 'B', 'C', 'D'],
        'scores': [37000, 13000, 25000, 25000],
        'roundWind': 0,
        'roundNumber': 2,
        'honba': 0,
        'riichiSticks': 0,
        'dealer': 1,
        'events': [
          {'kind': 'win', 'description': 'A 론(B) 하네만 12000', 'delta': [12000, -12000, 0, 0], 'round': '동1국'},
        ],
        'finished': false,
      };
      final g = Game.fromJson(jsonDecode(jsonEncode(old)) as Map<String, dynamic>);
      expect(g.events.single.stars, isNull);
      expect(_stars(g), [0, 0, 0, 0]);
      expect(g.settle().every((r) => r.stars == 0), isTrue);
      final e = GameEvent.fromJson({'kind': 'win', 'description': 'x', 'delta': [0, 0, 0, 0], 'round': '동1국'});
      expect(e.stars, isNull);
    });
  });
}
