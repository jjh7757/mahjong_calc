import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/engine/shanten.dart';
import 'package:mahjong_calc/engine/tile.dart';

List<int> cnt(String s) => toCounts(parseTiles(s).tiles);
int t(String code) => Tiles.parse(code);

List<(int, int)> pairsOf(Ukeire u) => [for (final x in u.tiles) (x.tile, x.left)];

/// 136장 패산에서 n 장.
List<int> randomHand(Random r, int n) {
  final wall = <int>[
    for (var t = 0; t < 34; t++) ...[t, t, t, t]
  ]..shuffle(r);
  return toCounts(wall.take(n));
}

/// 보이는 패: 손에 든 것과 합쳐 4장 이하로 아무렇게나.
List<int> randomVisible(Random r, List<int> hand) => [
      for (var t = 0; t < 34; t++) r.nextInt(5 - hand[t]),
    ];

void main() {
  group('유효패', () {
    test('샤보 1z·2z', () {
      final u = ukeireOf(cnt('123m456p789s1122z'));
      expect(u.shanten, 0);
      expect(pairsOf(u), [(t('1z'), 2), (t('2z'), 2)]);
      expect(u.total, 4);
      expect(u.liveKinds, 2);
    });

    test('국사 13면', () {
      final u = ukeireOf(cnt('19m19p19s1234567z'));
      expect(u.shanten, 0);
      expect(u.tiles.map((x) => x.tile), kokushiYaochu);
      expect(u.tiles.every((x) => x.left == 3), isTrue);
      expect(u.total, 39);
    });

    test('구련 9면', () {
      final u = ukeireOf(cnt('1112345678999m'));
      expect(u.tiles.map((x) => x.tile), List.generate(9, (i) => i));
      for (final x in u.tiles) {
        expect(x.left, (x.tile == 0 || x.tile == 8) ? 1 : 3);
      }
      expect(u.total, 23);
    });

    test('치또이 단기', () {
      final u = ukeireOf(cnt('1133m2255p4477s1z'));
      expect(pairsOf(u), [(t('1z'), 3)]);
    });

    test('visible 만큼 줄고 0 아래로 안 내려감', () {
      final vis = List<int>.filled(34, 0);
      vis[t('1z')] = 1;
      vis[t('2z')] = 5; // 일부러 넘치게
      final u = ukeireOf(cnt('123m456p789s1122z'), visible: vis);
      expect(pairsOf(u), [(t('1z'), 1), (t('2z'), 0)]);
      expect(u.total, 1);
      expect(u.liveKinds, 1);
    });

    test('입력 배열을 바꾸지 않음', () {
      final c = cnt('123m456p789s1122z');
      final v = List<int>.filled(34, 1);
      final cc = [...c];
      final vc = [...v];
      ukeireOf(c, visible: v);
      discardOptions(cnt('11123m'), melds: 3, visible: v);
      expect(c, cc);
      expect(v, vc);
    });

    test('잘못된 입력은 ArgumentError', () {
      expect(() => ukeireOf(cnt('123m456p789s11222z')), throwsArgumentError);
      expect(() => ukeireOf(cnt('123m456p789s1122z'), visible: [0]),
          throwsArgumentError);
      expect(() => discardOptions(cnt('123m456p789s1122z')), throwsArgumentError);
      expect(() => discardOptions(cnt('11123m'), melds: 2), throwsArgumentError);
    });
  });

  group('버림 후보', () {
    test('울기 3, 11123m 화료 손패: 정렬과 버린 패 한 장 덜 세기', () {
      // 1m 버림 → 1123m: 1m(4−2−버린1=1), 4m(4) = 5
      // 2m 버림 → 1113m: 2m(4−0−버린1=3), 3m(4−1=3) = 6
      // 3m 버림 → 1112m: 2m(4−1=3), 3m(4−0−버린1=3) = 6
      final opts = discardOptions(cnt('11123m'), melds: 3);
      expect(opts.map((o) => o.tile), [t('2m'), t('3m'), t('1m')]);
      expect(opts.map((o) => o.shanten), [0, 0, 0]);
      expect(pairsOf(opts[0].ukeire), [(t('2m'), 3), (t('3m'), 3)]);
      expect(pairsOf(opts[1].ukeire), [(t('2m'), 3), (t('3m'), 3)]);
      expect(pairsOf(opts[2].ukeire), [(t('1m'), 1), (t('4m'), 4)]);
      // 버린 패를 안 세는 ukeireOf 와는 1m 에서 한 장 차이
      expect(pairsOf(ukeireOf(cnt('1123m'), melds: 3)),
          [(t('1m'), 2), (t('4m'), 4)]);
    });

    test('울기 4, 11m 화료 손패: 1m 단기 2장', () {
      final opts = discardOptions(cnt('11m'), melds: 4);
      expect(opts.length, 1);
      expect(opts[0].shanten, 0);
      expect(pairsOf(opts[0].ukeire), [(t('1m'), 2)]);
    });

    test('14장 화료 손패도 예외 없이', () {
      final opts = discardOptions(cnt('123m456p789s11222z'));
      expect(opts.first.shanten, 0);
      expect(opts.length, 11); // 손에 있는 종류 수
      // 2z 버림 → 1z·2z 샤보, 2z 는 손 2 + 버림 1 → 1장
      final d2z = opts.firstWhere((o) => o.tile == t('2z'));
      expect(pairsOf(d2z.ukeire), [(t('1z'), 2), (t('2z'), 1)]);
    });

    test('visible 을 주면 정렬이 그 값으로', () {
      final vis = List<int>.filled(34, 0);
      vis[t('4m')] = 4;
      final opts = discardOptions(cnt('11123m'), melds: 3, visible: vis);
      expect(opts.map((o) => o.tile), [t('2m'), t('3m'), t('1m')]);
      expect(opts[2].ukeire.total, 1);
      expect(opts[2].ukeire.liveKinds, 1);
    });

    test('무작위: 각 후보 = ukeireOf(버린 뒤, visible + 버린 패), 정렬 순서', () {
      final r = Random(7);
      var n = 0;
      for (var m = 0; m <= 4; m++) {
        for (var i = 0; i < 60; i++) {
          final h = randomHand(r, 14 - 3 * m);
          final vis = i.isEven ? randomVisible(r, h) : null;
          final opts = discardOptions(h, melds: m, visible: vis);
          final kinds = [
            for (var d = 0; d < 34; d++)
              if (h[d] > 0) d
          ];
          expect(opts.map((o) => o.tile).toSet(), kinds.toSet());
          for (final o in opts) {
            final after = [...h];
            after[o.tile]--;
            final v2 = [...(vis ?? List<int>.filled(34, 0))];
            v2[o.tile]++;
            final u = ukeireOf(after, melds: m, visible: v2);
            expect(o.shanten, u.shanten);
            expect(o.ukeire.shanten, u.shanten);
            expect(pairsOf(o.ukeire), pairsOf(u));
          }
          for (var j = 1; j < opts.length; j++) {
            final a = opts[j - 1];
            final b = opts[j];
            final ok = a.shanten < b.shanten ||
                (a.shanten == b.shanten &&
                    (a.ukeire.total > b.ukeire.total ||
                        (a.ukeire.total == b.ukeire.total && a.tile < b.tile)));
            expect(ok, isTrue, reason: '$a / $b');
          }
          expect(shanten(h, melds: m), opts.first.shanten);
          n++;
        }
      }
      expect(n, 300);
    });
  });

  test('속도(보고용, 단정 없음): discardOptions 1,000번', () {
    final r = Random(99);
    final hands = [for (var i = 0; i < 1000; i++) randomHand(r, 14)];
    final cold = Stopwatch()..start();
    for (final h in hands) {
      discardOptions(h);
    }
    cold.stop();
    final warm = Stopwatch()..start();
    for (final h in hands) {
      discardOptions(h);
    }
    warm.stop();
    // ignore: avoid_print
    print('discardOptions 1,000번: 처음 ${cold.elapsedMilliseconds}ms, '
        '캐시 덥힌 뒤 ${warm.elapsedMilliseconds}ms');
  });
}

const kokushiYaochu = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];
