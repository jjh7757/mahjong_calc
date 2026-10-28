import 'dart:math' as math;

import 'hand.dart';

/// 점수 한계 구간.
enum Limit {
  none(''),
  mangan('만관'),
  haneman('하네만'),
  baiman('배만'),
  sanbaiman('삼배만'),
  kazoeYakuman('헤아림 역만'),
  yakuman('역만');

  const Limit(this.label);
  final String label;
}

class BasePoints {
  final int base;
  final Limit limit;
  const BasePoints(this.base, this.limit);
}

/// 판·부 → 기본점.
BasePoints basePoints(int han, int fu, RuleSet rules) {
  if (han >= 13 && rules.kazoeYakuman) {
    return const BasePoints(8000, Limit.kazoeYakuman);
  }
  if (han >= 11) return const BasePoints(6000, Limit.sanbaiman);
  if (han >= 8) return const BasePoints(4000, Limit.baiman);
  if (han >= 6) return const BasePoints(3000, Limit.haneman);
  if (han >= 5) return const BasePoints(2000, Limit.mangan);
  final raw = fu * math.pow(2, han + 2).toInt();
  if (raw >= 2000) return const BasePoints(2000, Limit.mangan);
  if (rules.kiriageMangan &&
      ((han == 4 && fu == 30) || (han == 3 && fu == 60))) {
    return const BasePoints(2000, Limit.mangan);
  }
  return BasePoints(raw, Limit.none);
}

/// 역만 기본점. [count] 는 역만 배수 합.
BasePoints yakumanPoints(int count) =>
    BasePoints(8000 * count, Limit.yakuman);

/// 지불액.
class Payment {
  /// 론일 때 방총자가 내는 금액. 쯔모면 0.
  final int ron;

  /// 쯔모일 때 친이 내는 금액(화료자가 친이면 0).
  final int tsumoFromDealer;

  /// 쯔모일 때 자가 각각 내는 금액.
  final int tsumoFromNonDealer;

  /// 화료자가 받는 총액.
  final int total;

  const Payment({
    required this.ron,
    required this.tsumoFromDealer,
    required this.tsumoFromNonDealer,
    required this.total,
  });

  /// 화면 표시용. 예: `8000`, `2000 / 4000`, `4000 올`
  String get display {
    if (ron > 0) return '$ron';
    if (tsumoFromDealer == 0) return '$tsumoFromNonDealer 올';
    return '$tsumoFromNonDealer / $tsumoFromDealer';
  }
}

int _ceil100(int v) => (v + 99) ~/ 100 * 100;

Payment payment(int base, Situation sit) {
  final honba = sit.honba;
  if (!sit.isTsumo) {
    final ron = _ceil100(base * (sit.isDealer ? 6 : 4)) + honba * 300;
    return Payment(
        ron: ron, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: ron);
  }
  if (sit.isDealer) {
    final each = _ceil100(base * 2) + honba * 100;
    return Payment(
        ron: 0,
        tsumoFromDealer: 0,
        tsumoFromNonDealer: each,
        total: each * 3);
  }
  final fromDealer = _ceil100(base * 2) + honba * 100;
  final fromOthers = _ceil100(base) + honba * 100;
  return Payment(
      ron: 0,
      tsumoFromDealer: fromDealer,
      tsumoFromNonDealer: fromOthers,
      total: fromDealer + fromOthers * 2);
}
