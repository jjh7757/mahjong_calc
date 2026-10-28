import 'dart:math';

import '../engine/calculator.dart';
import '../engine/score.dart' show basePoints, payment;

/// 퀴즈 한 문제: 손패·상황과 정답.
class QuizProblem {
  final Hand hand;
  final Situation situation;
  final ScoreResult answer;

  const QuizProblem(this.hand, this.situation, this.answer);
}

/// 무작위로 "역이 있는 보통 손패"를 만든다. 역만은 제외한다.
class QuizGenerator {
  final Random _rng;
  final RuleSet rules;

  QuizGenerator({int? seed, this.rules = RuleSet.standard}) : _rng = Random(seed);

  QuizProblem next() {
    for (var attempt = 0; attempt < 300; attempt++) {
      final p = _tryOnce();
      if (p != null) return p;
    }
    throw StateError('문제를 만들지 못했습니다');
  }

  QuizProblem? _tryOnce() {
    final counts = List<int>.filled(Tiles.count, 0);
    final closedSets = <List<int>>[];
    final melds = <Meld>[];
    final meldCount = _rng.nextDouble() < 0.3 ? _rng.nextInt(2) + 1 : 0;

    for (var i = 0; i < 4; i++) {
      final set = _randomSet(counts);
      if (set == null) return null;
      if (i < meldCount) {
        melds.add(set[0] == set[1] ? Meld.pon(set[0]) : Meld.chi(set[0]));
      } else {
        closedSets.add(set);
      }
    }
    int pair;
    var tries = 0;
    do {
      pair = _rng.nextInt(Tiles.count);
      if (++tries > 50) return null;
    } while (counts[pair] > 2);
    counts[pair] += 2;

    final closed = [for (final s in closedSets) ...s, pair, pair];
    final winTile = closed[_rng.nextInt(closed.length)];
    var red = 0;
    if (rules.redDora &&
        _rng.nextDouble() < 0.3 &&
        closed.any((t) => t < 27 && Tiles.number(t) == 5)) {
      red = 1;
    }

    final hand = Hand(closedTiles: closed, melds: melds, winTile: winTile, redCount: red);
    final isClosed = melds.isEmpty;
    final isTsumo = _rng.nextBool();
    final riichi = isClosed && _rng.nextDouble() < 0.6;

    final doraIndicators = <int>[];
    if (_rng.nextDouble() < 0.7) {
      final total = toCounts(hand.allTiles);
      for (var t = 0; t < 30; t++) {
        final cand = _rng.nextInt(Tiles.count);
        if (total[cand] < 4) {
          doraIndicators.add(cand);
          break;
        }
      }
    }

    final sit = Situation(
      isTsumo: isTsumo,
      seatWind: Tiles.east + _rng.nextInt(4),
      roundWind: Tiles.east + _rng.nextInt(2),
      riichi: riichi,
      ippatsu: riichi && _rng.nextDouble() < 0.15,
      doraIndicators: doraIndicators,
      honba: _rng.nextDouble() < 0.3 ? _rng.nextInt(3) + 1 : 0,
    );

    final result = calculate(hand, sit, rules: rules);
    if (!result.isValid || result.isYakuman) return null;
    if (result.han >= 8 && _rng.nextDouble() < 0.7) return null;
    return QuizProblem(hand, sit, result);
  }

  /// 순자 또는 커쯔 하나. 4장 제한을 지킨다.
  List<int>? _randomSet(List<int> counts) {
    for (var i = 0; i < 30; i++) {
      if (_rng.nextDouble() < 0.65) {
        final suit = _rng.nextInt(3);
        final start = suit * 9 + _rng.nextInt(7);
        final seq = [start, start + 1, start + 2];
        if (seq.every((t) => counts[t] < 4)) {
          for (final t in seq) {
            counts[t]++;
          }
          return seq;
        }
      } else {
        final t = _rng.nextInt(Tiles.count);
        if (counts[t] <= 1) {
          counts[t] += 3;
          return [t, t, t];
        }
      }
    }
    return null;
  }
}

/// 점수 보기(정답 포함, 섞여 있음). 론은 방총자 지불액, 쯔모는 "자/친" 또는 "올".
/// 오답은 정답 근처의 판·부 조합으로 만든다.
List<String> scoreChoices(QuizProblem p, Random rng, {int count = 4, RuleSet rules = RuleSet.standard}) {
  final correct = p.answer.payment.display;
  const fus = [20, 25, 30, 40, 50, 60, 70];
  final pool = <String>{};
  var guard = 0;
  while (pool.length < count - 1 && guard++ < 300) {
    final han = max(1, p.answer.han + rng.nextInt(5) - 2);
    final fu = fus[rng.nextInt(fus.length)];
    final d = payment(basePoints(han, fu, rules).base, p.situation).display;
    if (d != correct) pool.add(d);
  }
  return [...pool, correct]..shuffle(rng);
}
