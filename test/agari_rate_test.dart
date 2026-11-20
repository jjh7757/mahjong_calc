// lib/engine/agari_rate.dart 시험. 기대값은 원본 EndlessCheng/mahjong-helper
// util/agari_rate_test.go(TestCalculateAvgAgariRate)를 그대로 옮겼다.
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/agari_rate.dart';
import 'package:mahjong_calc/engine/mh_player.dart';

MhWaits w(Map<int, int> m) => MhWaits.from(m);

void main() {
  group('원본 TestCalculateAvgAgariRate', () {
    const eps = 1e-3;
    // (기대값, 대기, 자기 버림)
    final cases = <(double, Map<int, int>, List<int>)>[
      (62.1166, {0: 4, 3: 4}, []),
      (57.715203, {0: 3, 3: 3}, []),
      (34.6678, {0: 3, 3: 4}, [0]), // 후리텐
      (65.8944, {0: 2, 9: 2}, []),
      (71.058, {0: 3, 1: 4}, []),
      (71.058, {8: 3, 7: 4}, []),
      (96.2222, {0: 1, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 9: 1}, []),
      (71.968, {9: 2, 27: 2}, []),
      (49.5, {27: 3}, []),
      (58, {27: 2}, []),
      (47.5, {27: 1}, []),
      (0, {27: 0}, []),
      (49.6629, {0: 1, 7: 2}, []),
      (51.31672, {2: 4, 5: 4}, []),
      (54.5818, {4: 4, 7: 4}, []),
      (61.744, {5: 2, 31: 2}, []),
      (48.93434, {1: 4, 4: 2}, []),
      (54.5818, {1: 4, 4: 4}, []),
    ];
    for (final (want, waits, discards) in cases) {
      test('$waits 버림 $discards → $want', () {
        expect(avgAgariRate(w(waits), discardTiles: discards), closeTo(want, eps));
      });
    }
  });

  group('손으로 센 값', () {
    test('1m·4m 양면 4·4장: (54.0 ⊕ 31.0) × 0.91', () {
      // 1m 무스지19[4] = 54.0, 4m 무스지46[4] = 31.0
      // 합성 a + b − ab/100 = 54 + 31 − 16.74 = 68.26, 스지 양면 ×0.91 = 62.1166
      final each = agariRateOfEachTile(w({0: 4, 3: 4}), const [], const []);
      expect(each[0], 54.0);
      expect(each[3], 31.0);
      expect(avgAgariRate(w({0: 4, 3: 4})), closeTo(62.1166, 1e-9));
    });

    test('후리텐 3장: 장당 5.9% 를 세 번 합성', () {
      // 5.9 → 5.9 + 5.9 − 0.3481 = 11.4519 → 11.4519 + 5.9 − 0.67566 = 16.67624
      expect(avgAgariRate(w({1: 3}), discardTiles: [1]), closeTo(16.6762379, 1e-6));
    });

    test('도라 대기 배율: 수패 26/38, 자패 단기 35/48', () {
      // 2m 무스지28[3] = 38.2 → × 26/38
      expect(agariRateOfEachTile(w({1: 3, 4: 3}), const [], const [1])[1],
          closeTo(38.2 * 26 / 38, 1e-9));
      // 동 단기 남은 2장 58.0 → × 35/48
      expect(avgAgariRate(w({27: 2}), doraTiles: [27]), closeTo(58.0 * 35 / 48, 1e-9));
    });

    test('스지 종류: 1m 버림 → 4m 반스지A, 7m 버림 → 반스지B, 둘 다 → 양스지', () {
      expect(agariTileType27([0])[3], AgariTileType.halfSuji46A);
      expect(agariTileType27([0, 6])[3], AgariTileType.doubleSuji46);
      expect(agariTileType27([6])[3], AgariTileType.halfSuji46B);
      expect(agariTileType27([3])[0], AgariTileType.suji19);
    });
  });
}
