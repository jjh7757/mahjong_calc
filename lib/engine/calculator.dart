import 'decompose.dart';
import 'fu.dart';
import 'hand.dart';
import 'score.dart';
import 'tile.dart';
import 'yaku.dart';

export 'decompose.dart' show Decomposition, HandShape, WaitType;
export 'fu.dart' show FuItem, FuResult;
export 'hand.dart';
export 'meld.dart';
export 'score.dart' show Limit, Payment;
export 'tile.dart';
export 'yaku.dart' show Yaku, YakuHan;

/// 계산 결과. [error] 가 있으면 화료가 아니거나 역이 없는 것이다.
class ScoreResult {
  final String? error;
  final List<YakuHan> yaku;
  final int han;
  final FuResult fu;
  final Limit limit;
  final int basePoints;
  final Payment payment;
  final Decomposition? decomposition;

  const ScoreResult._({
    this.error,
    this.yaku = const [],
    this.han = 0,
    this.fu = const FuResult(0, []),
    this.limit = Limit.none,
    this.basePoints = 0,
    this.payment = const Payment(
        ron: 0, tsumoFromDealer: 0, tsumoFromNonDealer: 0, total: 0),
    this.decomposition,
  });

  const ScoreResult.failure(String message) : this._(error: message);

  bool get isValid => error == null;
  bool get isYakuman => limit == Limit.yakuman;

  /// 역만 배수(역만이 아니면 0).
  int get yakumanCount =>
      isYakuman ? yaku.fold(0, (sum, y) => sum + y.han) : 0;

  /// 예: `3판 40부`, `역만`, `만관`
  String get summary {
    if (!isValid) return error!;
    if (isYakuman) {
      return yakumanCount >= 2 ? '$yakumanCount배 역만' : '역만';
    }
    final hanFu = '$han판 ${fu.total}부';
    return limit == Limit.none ? hanFu : '$hanFu ${limit.label}';
  }

  @override
  String toString() =>
      '$summary ${payment.display} [${yaku.join(', ')}] $decomposition';
}

/// 파오(책임지불) 대상 역만의 기본점: 대삼원·대사희(작혼식, 사깡즈는 대상 아님). 겹친 다른 역만은 평소대로 내므로
/// 그 몫만 돌려준다. 역만이 아니거나 대상이 없으면 0.
int paoBasePoints(ScoreResult r) {
  if (!r.isYakuman) return 0;
  var n = 0;
  for (final y in r.yaku) {
    if (y.yaku == Yaku.daisangen || y.yaku == Yaku.daisuushi) n += y.han;
  }
  return yakumanPoints(n).base;
}

/// 손패와 상황으로 최고 점수를 계산한다.
/// 천화·지화는 기다림이 없으니 화료패를 어느 장으로 봐도 되어, 가장 높은 점수를 고른다.
ScoreResult calculate(Hand hand, Situation sit,
    {RuleSet rules = RuleSet.standard}) {
  if (!sit.firstTurnWin || !sit.isTsumo || hand.melds.isNotEmpty) {
    return _calculateWith(hand, sit, rules);
  }
  ScoreResult? best;
  for (final t in hand.closedTiles.toSet()) {
    final r = _calculateWith(
        Hand(closedTiles: hand.closedTiles, winTile: t, redCount: hand.redCount),
        sit,
        rules);
    if (best == null || (r.isValid && (!best.isValid || _better(r, best)))) {
      best = r;
    }
  }
  return best!;
}

/// 손패 없이 천화·지화 하나만으로 점수를 낸다. 다른 역만이 겹치면 손패를 넣어야 센다.
ScoreResult firstTurnWinOnly(Situation sit) {
  final y = sit.isDealer ? Yaku.tenhou : Yaku.chiihou;
  final bp = yakumanPoints(y.yakuman);
  return ScoreResult._(
    yaku: [YakuHan(y, y.yakuman)],
    han: 13 * y.yakuman,
    limit: bp.limit,
    basePoints: bp.base,
    payment: payment(bp.base, sit),
  );
}

ScoreResult _calculateWith(Hand hand, Situation sit, RuleSet rules) {
  final decompositions = decompose(hand);
  if (decompositions.isEmpty) {
    return const ScoreResult.failure('화료 형태가 아닙니다');
  }

  ScoreResult? best;
  for (final d in decompositions) {
    final r = _score(hand, d, sit, rules);
    if (r == null) continue;
    if (best == null || _better(r, best)) best = r;
  }
  return best ?? const ScoreResult.failure('역이 없습니다');
}

bool _better(ScoreResult a, ScoreResult b) {
  if (a.payment.total != b.payment.total) {
    return a.payment.total > b.payment.total;
  }
  if (a.han != b.han) return a.han > b.han;
  return a.fu.total > b.fu.total;
}

ScoreResult? _score(
    Hand hand, Decomposition d, Situation sit, RuleSet rules) {
  final yaku = detectYaku(hand, d, sit, rules);
  if (yaku.isEmpty) return null;

  if (yaku.first.yaku.isYakuman) {
    final count = yaku.fold<int>(0, (sum, y) => sum + y.han);
    final bp = yakumanPoints(count);
    return ScoreResult._(
      yaku: yaku,
      han: 13 * count,
      fu: calculateFu(hand, d, sit, rules, isPinfu: false),
      limit: bp.limit,
      basePoints: bp.base,
      payment: payment(bp.base, sit),
      decomposition: d,
    );
  }

  final all = [...yaku, ..._doraYaku(hand, sit, rules)];
  final han = all.fold<int>(0, (sum, y) => sum + y.han);
  final isPinfu = yaku.any((y) => y.yaku == Yaku.pinfu);
  final fu = calculateFu(hand, d, sit, rules, isPinfu: isPinfu);
  final bp = basePoints(han, fu.total, rules);
  return ScoreResult._(
    yaku: all,
    han: han,
    fu: fu,
    limit: bp.limit,
    basePoints: bp.base,
    payment: payment(bp.base, sit),
    decomposition: d,
  );
}

List<YakuHan> _doraYaku(Hand hand, Situation sit, RuleSet rules) {
  final counts = toCounts(hand.allTiles);
  final result = <YakuHan>[];

  int countDora(List<int> indicators) =>
      indicators.fold(0, (sum, i) => sum + counts[Tiles.doraFromIndicator(i)]);

  final dora = countDora(sit.doraIndicators);
  if (dora > 0) result.add(YakuHan(Yaku.dora, dora));
  if (rules.redDora && hand.redCount > 0) {
    result.add(YakuHan(Yaku.akaDora, hand.redCount));
  }
  if (sit.riichi || sit.doubleRiichi) {
    final ura = countDora(sit.uraIndicators);
    if (ura > 0) result.add(YakuHan(Yaku.uraDora, ura));
  }
  return result;
}
