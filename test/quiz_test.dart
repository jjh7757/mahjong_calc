import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/quiz/quiz_generator.dart';

void main() {
  test('생성기는 역 있는 보통 손패만 만든다', () {
    final g = QuizGenerator(seed: 7);
    var open = 0;
    var tsumo = 0;
    for (var i = 0; i < 100; i++) {
      final p = g.next();
      expect(p.answer.isValid, isTrue);
      expect(p.answer.isYakuman, isFalse);
      expect(p.hand.allTiles.length, 14);
      final counts = toCounts(p.hand.allTiles);
      expect(counts.every((c) => c <= 4), isTrue);
      // 정답을 다시 계산해도 같다
      final again = calculate(p.hand, p.situation);
      expect(again.payment.display, p.answer.payment.display);
      if (!p.hand.isClosed) open++;
      if (p.situation.isTsumo) tsumo++;
    }
    expect(open, greaterThan(5));
    expect(tsumo, greaterThan(20));
  });

  test('점수 보기에는 정답이 하나만 들어 있다', () {
    final g = QuizGenerator(seed: 3);
    final rng = Random(1);
    for (var i = 0; i < 30; i++) {
      final p = g.next();
      final choices = scoreChoices(p, rng);
      expect(choices.length, 4);
      expect(choices.where((c) => c == p.answer.payment.display).length, 1);
      expect(choices.toSet().length, 4);
    }
  });
}
