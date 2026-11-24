import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/member_stats.dart';

/// 멤버 누적 성적: 정산(우마·오카) 합·순위 횟수·평균 순위·1위율·토비·명단 필터·정렬.
/// 기대값은 손으로 계산했다(오카 = (반환점 − 시작점) × 4 / 1000, 1위가 받는다).
void main() {
  // 25000 시작 · 30000 반환 · 우마 20-10 · 오사육입 → 오카 20.
  const std = GameSettings();
  // 25000 시작 · 30000 반환 · 우마 10-5 · 소수 1자리 → 오카 20.
  const decimal = GameSettings(umaBig: 10, umaSmall: 5, roundingMode: 0);

  Game manual(String id, GameSettings s, List<String> names, List<int> scores) =>
      Game.manual(id: id, playedAt: DateTime(2026, 11, 20), settings: s, names: names, scores: scores);

  // 1판: A 45000(1위 +15+20+20 = +55) · B 30000(2위 0+10 = +10) · C 20000(3위 −10−10 = −20) · D 5000(4위 −25−20 = −45).
  final g1 = manual('1', std, const ['A', 'B', 'C', 'D'], const [45000, 30000, 20000, 5000]);
  // 2판: 기동 동 D 와 남 C 가 30000 동점 → 기동 자리 D 가 1위.
  // D(1위 0+20+20 = +40) · C(2위 0+10 = +10) · B 25000(3위 −5−10 = −15) · A 15000(4위 −15−20 = −35).
  final g2 = manual('2', std, const ['D', 'C', 'B', 'A'], const [30000, 30000, 25000, 15000]);
  // 3판(소수 1자리, 우마 10-5): B 52300(1위 22.3+10+20 = +52.3) · A 31700(2위 1.7+5 = +6.7)
  // · D 17400(3위 −12.6−5 = −17.6) · C −1400(4위 −31.4−10 = −41.4, 토비).
  final g3 = manual('3', decimal, const ['B', 'A', 'D', 'C'], const [52300, 31700, 17400, -1400]);

  test('정산 확인: 오카 20 이 1위에, 동점은 기동 자리 순', () {
    expect(std.oka, 20);
    expect(g1.settle().map((r) => (r.name, r.rank, r.score)).toList(),
        [('A', 1, 55.0), ('B', 2, 10.0), ('C', 3, -20.0), ('D', 4, -45.0)]);
    expect(g2.settle().map((r) => (r.name, r.rank, r.score)).toList(),
        [('D', 1, 40.0), ('C', 2, 10.0), ('B', 3, -15.0), ('A', 4, -35.0)]);
  });

  test('세 판 누적: 합계·순위 횟수·평균 순위·1위율·4위율·토비, 합계 내림차순', () {
    final s = memberStats([g1, g2, g3]);
    expect(s.map((m) => m.name).toList(), ['B', 'A', 'D', 'C']);
    final by = {for (final m in s) m.name: m};

    // A: +55 −35 +6.7 = +26.7, 순위 1·4·2.
    expect(by['A']!.games, 3);
    expect(by['A']!.total, closeTo(26.7, 1e-9));
    expect(by['A']!.rankCounts, [1, 1, 0, 1]);
    expect(by['A']!.avgRank, closeTo(7 / 3, 1e-9));
    expect(by['A']!.topRate, closeTo(1 / 3, 1e-9));
    expect(by['A']!.lastRate, closeTo(1 / 3, 1e-9));
    expect(by['A']!.busts, 0);

    // B: +10 −15 +52.3 = +47.3, 순위 2·3·1.
    expect(by['B']!.total, closeTo(47.3, 1e-9));
    expect(by['B']!.rankCounts, [1, 1, 1, 0]);
    expect(by['B']!.avgRank, closeTo(2.0, 1e-9));
    expect(by['B']!.lastRate, 0);

    // C: −20 +10 −41.4 = −51.4, 순위 3·2·4, 3판에서 토비.
    expect(by['C']!.total, closeTo(-51.4, 1e-9));
    expect(by['C']!.rankCounts, [0, 1, 1, 1]);
    expect(by['C']!.avgRank, closeTo(3.0, 1e-9));
    expect(by['C']!.topRate, 0);
    expect(by['C']!.busts, 1);

    // D: −45 +40 −17.6 = −22.6, 순위 4·1·3.
    expect(by['D']!.total, closeTo(-22.6, 1e-9));
    expect(by['D']!.rankCounts, [1, 0, 1, 1]);
    expect(by['D']!.avgRank, closeTo(8 / 3, 1e-9));
    expect(by['D']!.busts, 0);

    // 모든 대국의 정산 합은 0.
    expect(s.fold<double>(0, (a, m) => a + m.total), closeTo(0, 1e-9));
  });

  test('only: 명단의 이름만, 대국 없는 멤버도 0 으로 들어간다', () {
    final s = memberStats([g1, g2, g3], only: const ['A', 'E']);
    expect(s.map((m) => m.name).toList(), ['A', 'E']);
    final e = s.last;
    expect(e.games, 0);
    expect(e.total, 0);
    expect(e.rankCounts, [0, 0, 0, 0]);
    expect(e.avgRank, 0);
    expect(e.topRate, 0);
    expect(e.lastRate, 0);
    expect(e.busts, 0);

    // 합계 0 인 E 는 합계 순으로 +26.7(A) 아래, −22.6(D) 위.
    final all = memberStats([g1, g2, g3], only: const ['A', 'B', 'C', 'D', 'E']);
    expect(all.map((m) => m.name).toList(), ['B', 'A', 'E', 'D', 'C']);
  });

  test('합계가 같으면 평균 순위 → 이름 순', () {
    // 우마·오카 없음, 모두 25000 → 정산은 모두 0, 순위는 기동 자리 순(S 1위 … P 4위).
    const flat = GameSettings(returnPoints: 25000, umaBig: 0, umaSmall: 0);
    final g = manual('f', flat, const ['S', 'R', 'Q', 'P'], const [25000, 25000, 25000, 25000]);
    final s = memberStats([g], only: const ['P', 'Q', 'R', 'S', 'Y', 'X']);
    expect(s.map((m) => m.total).toSet(), {0.0});
    // 대국 있는 S·R·Q·P 는 평균 순위 1·2·3·4, 대국 없는 X·Y(평균 0)는 이름 순으로 앞.
    expect(s.map((m) => m.name).toList(), ['X', 'Y', 'S', 'R', 'Q', 'P']);
  });

  test('Game.manual: 끝난 대국, 올라스, 결과 입력 사건 하나', () {
    expect(g1.finished, isTrue);
    expect(g1.isManual, isTrue);
    expect(g1.isOver, isTrue);
    expect(g1.endLabel, '직접 입력한 대국');
    expect(g1.roundLabel, '남4국');
    expect(g1.events, hasLength(1));
    expect(g1.events.single.kind, 'adjust');
    expect(g1.events.single.delta, [20000, 5000, -5000, -20000]);
    final east = manual('e', const GameSettings(eastOnly: true), const ['A', 'B', 'C', 'D'], const [25000, 25000, 25000, 25000]);
    expect(east.roundLabel, '동4국');
    // 저장했다 불러와도 직접 입력으로 남는다.
    expect(Game.fromJson(g1.toJson()).isManual, isTrue);
  });
}
