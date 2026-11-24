/// 멤버별 누적 성적. 순수 Dart, UI 의존 없음.
library;

import 'game.dart';

/// 한 멤버의 누적 성적.
class MemberStat {
  final String name;

  /// 대국 수.
  final int games;

  /// 정산 점수(우마·오카 포함, 천점 단위) 합. 소수 한 자리로 반올림해 둔다.
  final double total;

  /// 1~4위 횟수(길이 4).
  final List<int> rankCounts;

  /// 토비(최종 점수 < 0) 횟수.
  final int busts;

  /// 별 합([Settlement.stars]).
  final int stars;

  /// 최고 최종 점수(정산 전 점수). 대국이 없으면 null.
  final int? best;

  const MemberStat({
    required this.name,
    required this.games,
    required this.total,
    required this.rankCounts,
    required this.busts,
    this.stars = 0,
    this.best,
  });

  /// 평별(대국당 별). 대국이 없으면 0.
  double get avgStars => games == 0 ? 0 : stars / games;

  /// 평균 순위. 대국이 없으면 0.
  double get avgRank {
    if (games == 0) return 0;
    var sum = 0;
    for (var r = 0; r < 4; r++) {
      sum += (r + 1) * rankCounts[r];
    }
    return sum / games;
  }

  /// 1위율(0~1). 대국이 없으면 0.
  double get topRate => games == 0 ? 0 : rankCounts[0] / games;

  /// 1,2위율(0~1, 연대율). 대국이 없으면 0.
  double get top2Rate => games == 0 ? 0 : (rankCounts[0] + rankCounts[1]) / games;

  /// 4위율(0~1). 대국이 없으면 0.
  double get lastRate => games == 0 ? 0 : rankCounts[3] / games;
}

double _round1(double v) => (v * 10).round() / 10;

/// [games] 의 정산([Game.settle]) 결과를 이름별로 모은다.
///
/// [only] 가 있으면 그 이름들만 내고, 대국이 없는 이름도 0 으로 넣는다(등록 멤버 순위표).
/// 정렬은 정산 점수 합 내림차순 → 평균 순위 오름차순 → 이름.
/// 한 대국에 같은 이름이 둘이면 각각 센다(입력 화면에서 막으므로 실제로는 없다).
List<MemberStat> memberStats(Iterable<Game> games, {Iterable<String>? only}) {
  final filter = only?.toSet();
  final count = <String, int>{};
  final total = <String, double>{};
  final ranks = <String, List<int>>{};
  final busts = <String, int>{};
  final stars = <String, int>{};
  final best = <String, int>{};

  void ensure(String n) {
    count.putIfAbsent(n, () => 0);
    total.putIfAbsent(n, () => 0);
    ranks.putIfAbsent(n, () => List.filled(4, 0));
    busts.putIfAbsent(n, () => 0);
    stars.putIfAbsent(n, () => 0);
  }

  if (filter != null) filter.forEach(ensure);
  for (final g in games) {
    for (final r in g.settle()) {
      if (filter != null && !filter.contains(r.name)) continue;
      ensure(r.name);
      count[r.name] = count[r.name]! + 1;
      total[r.name] = _round1(total[r.name]! + r.score);
      ranks[r.name]![r.rank - 1]++;
      if (r.points < 0) busts[r.name] = busts[r.name]! + 1;
      stars[r.name] = stars[r.name]! + r.stars;
      final b = best[r.name];
      if (b == null || r.points > b) best[r.name] = r.points;
    }
  }

  final out = [
    for (final n in count.keys)
      MemberStat(
        name: n,
        games: count[n]!,
        total: total[n]!,
        rankCounts: ranks[n]!,
        busts: busts[n]!,
        stars: stars[n]!,
        best: best[n],
      ),
  ];
  out.sort((a, b) {
    final t = b.total.compareTo(a.total);
    if (t != 0) return t;
    final r = a.avgRank.compareTo(b.avgRank);
    if (r != 0) return r;
    return a.name.compareTo(b.name);
  });
  return out;
}
