// lib/engine/improve.dart · hand_value.dart 시험.
// 기대값은 원본 EndlessCheng/mahjong-helper 의 util/shanten_improve_test.go
// (Test_calculateIsolatedTileValue), util/shanten_search_test.go
// (TestCalculateShantenAndWaits13), util/point_test.go 에서 옮겼고,
// 원본에 없는 것은 손으로 센 값(셈은 주석).
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/hand_value.dart';
import 'package:mahjong_calc/engine/improve.dart';
import 'package:mahjong_calc/engine/score.dart' show basePoints, yakumanPoints;

List<int> cnt(String s) => toCounts(parseTiles(s).tiles);
int t(String code) => Tiles.parse(code);

MhPlayerInfo pi13(String hand, {int round = Tiles.east, int self = Tiles.east,
    List<int> discards = const [], bool parent = false}) {
  final tiles = cnt(hand);
  return MhPlayerInfo(
    handTiles34: tiles,
    leftTiles34: [for (final c in tiles) 4 - c],
    roundWindTile: round,
    selfWindTile: self,
    discardTiles: discards,
    isParent: parent,
  );
}

void main() {
  group('원본 Test_calculateIsolatedTileValue', () {
    MhPlayerInfo pi(int self, int round, String seen) => MhPlayerInfo(
          handTiles34: List.filled(34, 0),
          selfWindTile: self,
          roundWindTile: round,
          leftTiles34: [for (final c in cnt(seen)) 4 - c],
        );
    const eps = 1e-3;
    final cases = <(double, String, int, int, String)>[
      (100, '9m', 27, 27, '2s'),
      (130, '1z', 27, 27, '2s'),
      (117, '1z', 27, 27, '2s11z'),
      (97, '2z', 27, 27, '2s'),
      (98, '3z', 27, 27, '2s'),
      (99, '4z', 27, 27, '2s'),
      (114.9, '5z', 27, 27, '2s'),
      (114.8, '6z', 27, 27, '2s'),
      (115, '7z', 27, 27, '2s'),
      (103.5, '7z', 27, 27, '2s77z'),
      (23, '7z', 27, 27, '2s777z'),
      (114, '1z', 29, 27, '2s'),
      (102.6, '1z', 29, 27, '2s11z'),
      (99, '2z', 29, 27, '2s'),
      (116, '3z', 29, 27, '2s'),
      (97, '4z', 29, 27, '2s'),
    ];
    for (final (want, tile, self, round, seen) in cases) {
      test('$tile 자풍 $self 장풍 $round 보인 $seen → $want', () {
        expect(calculateIsolatedTileValue(t(tile), pi(self, round, seen)),
            closeTo(want, eps));
      });
    }
  });

  group('원본 TestCalculateShantenAndWaits13', () {
    // (손, 샹텐, 유효패 장수, 유효패)
    final cases = <(String, int, int, String)>[
      ('1122334455667z', 0, 3, '7z'),
      ('123456789m 1135s', 0, 4, '4s'),
      ('123456789m 1134s', 0, 8, '2s 5s'),
      ('3456m 3456s 44456p', 1, 61, '1m 2m 3m 4m 5m 6m 7m 8m 4p 7p 1s 2s 3s 4s 5s 6s 7s 8s'),
      ('123456789m 1234z', 2, 12, '1z 2z 3z 4z'),
      ('11357m 13579p 135s', 3, 32, '4m 6m 2p 4p 6p 8p 2s 4s'),
      // 울기(장수로 울기 수를 셈)
      ('5p', 0, 3, '5p'),
      ('1234p', 0, 6, '1p 4p'),
      ('5555m', 1, 132,
          '1m 2m 3m 4m 6m 7m 8m 9m 1p 2p 3p 4p 5p 6p 7p 8p 9p 1s 2s 3s 4s 5s 6s 7s 8s 9s 1z 2z 3z 4z 5z 6z 7z'),
      ('1234z', 2, 12, '1z 2z 3z 4z'),
    ];
    for (final (hand, shanten, count, tiles) in cases) {
      test(hand, () {
        final (s, waits) = calculateShantenAndWaits13(cnt(hand), null);
        expect(s, shanten);
        expect(waits.allCount, count);
        expect((waits.tiles.toList()..sort()).map(Tiles.toCode).join(' '), tiles);
      });
    }
  });

  group('속도 점수·탐색 깊이(손으로 셈)', () {
    test('speedScore: 유효패 8 · 전진 뒤 6 · 남은 100장', () {
      // p2 = 0.08, p1 = 0.06, q = 1 − p
      // sumP2 = 0.92(1 − 0.92^10)/0.08 = 6.504533, sumP1 = 0.94(1 − 0.94^10)/0.06 = 7.228363
      // p2·p1·(sumP2 − sumP1)/(q2 − q1) × 100 = 17.371930
      final r = Hand13AnalysisResult(
        tiles34: List.filled(34, 0),
        leftTiles34: [for (var i = 0; i < 34; i++) i < 25 ? 4 : 0],
        isNaki: false,
        shanten: 1,
        waits: MhWaits.from({0: 4, 3: 4}),
        nextShantenWaitsCountMap: const {},
        improves: const {},
        improveWayCount: 0,
        avgImproveWaitsCount: 8,
        yakuTypes: {},
        doraCount: 0,
      )..avgNextShantenWaitsCount = 6;
      expect(r.speedScore(), closeTo(17.371930466, 1e-6));
      // 유효패 = 전진 뒤면 0/0 → NaN(원본 Go 와 같음, 고치지 않음)
      r.avgNextShantenWaitsCount = 8;
      expect(r.speedScore().isNaN, isTrue);
    });

    test('_stopShanten: 3 이상은 한 층, 그 아래는 두 층', () {
      expect(stopShanten(4), 3);
      expect(stopShanten(3), 2);
      expect(stopShanten(2), 0);
      expect(stopShanten(1), -1);
      expect(stopShanten(0), -2);
    });

    test('양면 vs 간짱 텐파이: 유효패 장수와 화료율', () {
      // 34m 양면: 2m·5m 각 4장 = 8. 13m 간짱: 2m 4장.
      final ryan = calculateShantenWithImproves13(pi13('123456789p 34m 55s'));
      final kan = calculateShantenWithImproves13(pi13('123456789p 13m 55s'));
      expect(ryan.waits.toMap(), {t('2m'): 4, t('5m'): 4});
      expect(kan.waits.toMap(), {t('2m'): 4});
      // 양면: 2m 무스지28[4] 42.0 ⊕ 5m 무스지5[4] 31.0 = 59.98, ×0.91 = 54.5818
      expect(ryan.avgAgariRate, closeTo(54.5818, 1e-9));
      // 간짱: 2m 무스지28[4] = 42.0
      expect(kan.avgAgariRate, closeTo(42.0, 1e-9));
    });
  });

  group('원본 point_test.go(점수 식)', () {
    test('TestCalcPointRon', () {
      int ron(int han, int fu, int ym, bool parent) => pointRonFromBase(
          ym > 0 ? yakumanPoints(ym).base : basePoints(han, fu, RuleSet.standard).base,
          parent);
      expect(ron(1, 110, 0, false), 3600);
      expect(ron(3, 40, 0, false), 5200);
      expect(ron(3, 50, 0, false), 6400);
      expect(ron(3, 60, 0, false), 7700);
      expect(ron(3, 70, 0, false), 8000);
      expect(ron(3, 40, 0, true), 7700);
      expect(ron(4, 30, 0, true), 11600);
      expect(ron(4, 40, 0, true), 12000);
      for (var n = 1; n <= 6; n++) {
        expect(ron(0, 0, n, false), 32000 * n);
        expect(ron(0, 0, n, true), 48000 * n);
      }
    });

    test('TestCalcPointTsumoSum', () {
      int ts(int han, int fu, bool parent) =>
          pointTsumoSumFromBase(basePoints(han, fu, RuleSet.standard).base, parent);
      expect(ts(1, 110, false), 3600);
      expect(ts(3, 40, false), 5200);
      expect(ts(3, 50, false), 6400);
      expect(ts(3, 60, false), 7900);
      expect(ts(3, 70, false), 8000);
      expect(ts(3, 40, true), 7800);
      expect(ts(4, 40, true), 12000);
    });

    test('TestCalcRonPointWithHands(다마 론, 자, 장풍·자풍 남)', () {
      int pt(String hand, String win) {
        final p = pi13(hand, round: Tiles.south, self: Tiles.south);
        return calcPoint(p, t(win), isTsumo: false, isRiichi: false).point;
      }

      expect(pt('11m 112233445566z', '1m'), 12000); // 치또이 혼노두 혼일색
      expect(pt('345m 345s 334455p 44z', '3m'), 7700); // 핑후 이페코 삼색
      expect(pt('333m 333s 333345p 11z', '3m'), 2600); // 삼색동각
      expect(pt('22334455m 234s 234p', '3m'), 8000); // 높은 점수 쪽: 이페코 삼색 탕야오
      expect(pt('234m 333p 55666777z', '3m'), 12000); // 산안커 역패 역패 소삼원
      expect(pt('123445566789m 11z', '3m'), 12000); // 이페코 일통 혼일색
      expect(pt('123m 123999s 11155z', '3m'), 3200); // 찬타
      expect(pt('334455m 667788s 77z', '3m'), 5200); // 량페코
      expect(pt('334455m 667788s 44z', '3m'), 7700); // 핑후 량페코
      expect(pt('123m 123999s 11789p', '3m'), 5200); // 준찬타
      expect(pt('345m 12355789s 222z', '3m'), 2600); // 역패 역패(연풍)
      expect(pt('11122345678999m', '3m'), 32000); // 구련
      expect(pt('11122345678999m', '2m'), 64000); // 순정 구련
      expect(pt('11122233344455z', '5z'), 160000); // 대사희 자일색 사암각 단기
    });

    test('TestCalcRonPointWithHands(리치 론, 도라 0~12, 자·친)', () {
      const child = [1300, 2600, 5200, 8000, 8000, 12000, 12000, 16000, 16000, 16000, 24000, 24000, 32000];
      const parent = [2000, 3900, 7700, 12000, 12000, 18000, 18000, 24000, 24000, 24000, 36000, 36000, 48000];
      for (var dora = 0; dora < 13; dora++) {
        for (final isParent in [false, true]) {
          final p = MhPlayerInfo(
            handTiles34: cnt('345m 222789p 333s 66z'),
            leftTiles34: List.filled(34, 0),
            numRedFives: [dora, 0, 0], // 원본도 판 수를 맞추려고 적5 수를 늘림
            roundWindTile: Tiles.south,
            selfWindTile: Tiles.west,
            isParent: isParent,
          );
          expect(calcPoint(p, t('3m'), isTsumo: false, isRiichi: true).point,
              (isParent ? parent : child)[dora],
              reason: '도라 $dora 친 $isParent');
        }
      }
    });

    test('CalcAvgRiichiPoint(남장 남가)', () {
      double avg(String hand, {List<int> discards = const []}) {
        final p = pi13(hand, round: Tiles.south, self: Tiles.south, discards: discards);
        final (_, waits) = calculateShantenAndWaits13(p.handTiles34, null);
        return calcAvgRiichiPoint(p, waits).avgPoint;
      }

      expect(avg('34m 123567p 12355s'), closeTo(3700, 1)); // 리치 핑후
      expect(avg('13m 123567p 12355s'), closeTo(7500, 1)); // 리치 삼색
      expect(avg('12366m 234p 345s 55z'), closeTo(4291, 1)); // 리치 백
      expect(avg('45678m 123p 56799s', discards: [t('9m')]), closeTo(4070, 1)); // 후리텐 리치
    });
  });

  group('기대 타점·국수지(손으로 셈)', () {
    test('fixedRiichiPoint: 자 2000(2판) → ×3700/2000, 친 2900 → 자 환산 구간', () {
      PointResult pr(int point, int han, bool parent) => PointResult(
          point: point, han: han, fu: 30, yakumanTimes: 0, isParent: parent, winTile: 0, yaku: const []);
      // 2000 − 100 = 1900 ≤ 2000 → 2000 × 3700/2000 = 3700
      expect(pr(2000, 2, false).fixedRiichiPoint(false), closeTo(3700, 1e-9));
      // 친 2900 / 1.5 = 1933.3, −100 = 1833.3 ≤ 2000 → ×1.85 = 3576.67, ×1.5 = 5365
      expect(pr(2900, 2, true).fixedRiichiPoint(false), closeTo(5365, 1e-6));
      // 후리텐 ×1.1
      expect(pr(2000, 2, false).fixedRiichiPoint(true), closeTo(4070, 1e-9));
      // 만관 4판 8000: 7900 ≤ 8000 → ×9130/8000
      expect(pr(8000, 4, false).fixedRiichiPoint(false), closeTo(9130, 1e-9));
    });

    test('국수지: 화료율/100 × (점수 + 1500) − 1500', () {
      // 리치가 있으면 리치: 0.5 × 7500 − 1500 = 2250
      expect(mixedRoundPoint(avgAgariRate: 50, riichiPoint: 6000, damaPoint: 3900), 2250);
      // 리치 0 이면 다마: 0.4 × 5400 − 1500 = 660
      expect(mixedRoundPoint(avgAgariRate: 40, riichiPoint: 0, damaPoint: 3900), closeTo(660, 1e-9));
    });

    test('단기 자패 대기: 다마는 역 없음, 리치만 점수', () {
      // 123m 456p 789s 234s 1z(남장 남가): 1z 단기, 다마는 역 없음 → damaPoint 0
      final r = calculateShantenWithImproves13(
          pi13('123m 456p 789s 234s 1z', round: Tiles.south, self: Tiles.south));
      expect(r.shanten, 0);
      expect(r.waits.toMap(), {t('1z'): 3});
      expect(r.damaPoint, 0);
      expect(r.damaWaits.isEmpty, isTrue);
      // 자패 단기 3장 49.5%, 리치 1판 40부 1300 → 2730 구간: 1300 × 2730/1300 = 2730
      expect(r.avgAgariRate, closeTo(49.5, 1e-9));
      expect(r.riichiPoint, closeTo(2730, 1e-9));
      expect(r.mixedRoundPoint, closeTo(0.495 * (2730 + 1500) - 1500, 1e-9));
    });
  });
}
