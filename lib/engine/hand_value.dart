// Ported from EndlessCheng/mahjong-helper (MIT)
//   util/point.go(CalcPointRon · CalcPointTsumoSum · CalcAvgPoint · CalcAvgRiichiPoint),
//   util/point_data.go(fixedRiichiPoint), util/shanten_improve.go(mixedRoundPoint)
// Copyright (c) 2018 Σndless
// 원본 LICENSE 전문: third_party/mahjong-helper/LICENSE
//
// 텐파이 손의 기대 타점(대기마다 화료율로 가중평균)과 국수지.
//
// 바꾼 것: 원본 `CalcPoint`(자기 역·부 계산)는 옮기지 않고 우리 calculator.dart
// 의 [calculate] 로 역·판·부·기본점을 낸다. 점수는 그 기본점에서 원본
// `CalcPointRon`/`CalcPointTsumoSum` 식으로 다시 낸다(친 여부를 자풍과 따로 받기
// 때문). 원본은 일발·뒷도라·해저 등을 넣지 않으므로 여기서도 넣지 않는다.
//
// 원본 TODO(그대로): 대삼원·대사희 파오 / 남은 4장 미만이면 리치 불가 /
// 1000점 미만이면 리치 불가 / 다마 쯔모 / 하네만 이상 리치 보정.

import 'agari_rate.dart';
import 'calculator.dart';
import 'mh_player.dart';

/// 원본 `roundUpPoint`.
int roundUpPoint(int point) => point == 0 ? 0 : ((point - 1) ~/ 100 + 1) * 100;

/// 원본 `CalcPointRon`(기본점에서).
int pointRonFromBase(int basicPoint, bool isParent) =>
    roundUpPoint(isParent ? 6 * basicPoint : 4 * basicPoint);

/// 원본 `CalcPointTsumoSum`(기본점에서).
int pointTsumoSumFromBase(int basicPoint, bool isParent) {
  if (isParent) return 3 * roundUpPoint(2 * basicPoint);
  return 2 * roundUpPoint(basicPoint) + roundUpPoint(2 * basicPoint);
}

/// 원본 `PointResult`.
class PointResult {
  /// 론(후리텐 다마면 쯔모 합계) 점수. 역이 없으면 0.
  final int point;

  /// 화료했을 때의 기대 점수(리치면 [fixedRiichiPoint] 보정값).
  double fixedPoint;

  final int han;
  final int fu;
  final int yakumanTimes;
  final bool isParent;
  final int winTile;

  /// 역(도라·적도라·뒷도라 제외). 원본 `yakuTypes`.
  final List<Yaku> yaku;

  /// 이 대기의 화료율(%). 원본 `agariRate`.
  double agariRate = 0;

  PointResult({
    required this.point,
    required this.han,
    required this.fu,
    required this.yakumanTimes,
    required this.isParent,
    required this.winTile,
    required this.yaku,
  }) : fixedPoint = point.toDouble();

  /// 원본 `fixedRiichiPoint`(point_data.go): 쯔모·뒷도라·일발을 넣은 리치 실점수.
  /// 참고:「統計学」のマージャン戦術
  double fixedRiichiPoint(bool isFuriten) {
    var ronPoint = point.toDouble();
    if (isParent) ronPoint /= 1.5;

    final pt = ronPoint - 100; // 친·자를 같은 구간에 넣으려고
    if (pt <= 1300) {
      ronPoint *= 2730.0 / 1300.0;
    } else if (pt <= 2000) {
      ronPoint *= 3700.0 / 2000.0;
    } else if (pt <= 2600) {
      ronPoint *= 4900.0 / 2600.0;
    } else if (pt <= 3900) {
      ronPoint *= 6300.0 / 3900.0;
    } else if (pt <= 5200) {
      ronPoint *= 7500.0 / 5200.0;
    } else if (pt <= 7700) {
      ronPoint *= 9100.0 / 7700.0;
    } else if (pt <= 8000) {
      if (han == 4) {
        ronPoint *= 9130.0 / 8000.0;
      } else if (han == 5) {
        ronPoint *= 11200.0 / 8000.0;
      }
    } else if (pt <= 12000) {
      if (han == 6) {
        ronPoint *= 13030.0 / 12000.0;
      } else if (han == 7) {
        ronPoint *= 15000.0 / 12000.0;
      }
    } else {
      // TODO(원본): 하네만 이상 리치 타점 보정
    }

    if (isFuriten) {
      // 후리텐이면 쯔모뿐이라 타점이 조금 높다.
      const furitenRiichiPointMulti = 1.1;
      ronPoint *= furitenRiichiPointMulti;
    }

    if (isParent) ronPoint *= 1.5;
    return ronPoint;
  }
}

/// 원본 `CalcPoint` 대신: [pi] 의 손패(화료패 포함 3k+2장)로 우리 계산기를 부른다.
/// 역이 없으면 point 0.
PointResult calcPoint(MhPlayerInfo pi, int winTile,
    {required bool isTsumo, required bool isRiichi}) {
  final hand = pi.handTiles34;
  final key = StringBuffer();
  for (final c in hand) {
    key.write(c);
  }
  key
    ..write('|')
    ..write(winTile)
    ..write(isTsumo ? 't' : 'r')
    ..write(isRiichi ? 'R' : 'D')
    ..write(pi.redFiveTotal);
  final k = key.toString();
  var r = pi.pointCache[k];
  if (r == null) {
    final closed = <int>[
      for (var t = 0; t < 34; t++)
        for (var n = 0; n < hand[t]; n++) t,
    ];
    r = calculate(
      Hand(
        closedTiles: closed,
        melds: pi.melds,
        winTile: winTile,
        redCount: pi.redFiveTotal,
      ),
      Situation(
        isTsumo: isTsumo,
        seatWind: pi.selfWindTile,
        roundWind: pi.roundWindTile,
        riichi: isRiichi,
        doraIndicators: pi.doraIndicators,
      ),
    );
    pi.pointCache[k] = r;
  }
  if (!r.isValid) {
    return PointResult(
        point: 0,
        han: 0,
        fu: 0,
        yakumanTimes: 0,
        isParent: pi.isParent,
        winTile: winTile,
        yaku: const []);
  }
  final pt = isTsumo
      ? pointTsumoSumFromBase(r.basePoints, pi.isParent)
      : pointRonFromBase(r.basePoints, pi.isParent);
  return PointResult(
    point: pt,
    han: r.han,
    fu: r.fu.total,
    yakumanTimes: r.yakumanCount,
    isParent: pi.isParent,
    winTile: winTile,
    yaku: [
      for (final y in r.yaku)
        if (y.yaku != Yaku.dora &&
            y.yaku != Yaku.akaDora &&
            y.yaku != Yaku.uraDora)
          y.yaku,
    ],
  );
}

/// 원본 `CalcAvgPoint` 의 결과.
class AvgPoint {
  final double avgPoint;
  final List<PointResult> pointResults;
  const AvgPoint(this.avgPoint, this.pointResults);
}

/// 원본 `CalcAvgPoint`: 텐파이 손([pi] 13장 쪽)의 대기마다 점수를 화료율로
/// 가중평균한다. 역 없는 대기(후즈케·편대기)는 빠진다. 역이 하나도 없으면 0.
///
/// [isRiichi] 가 true 면 원본 `CalcAvgRiichiPoint` 처럼 리치를 붙이고
/// [PointResult.fixedRiichiPoint] 로 고친다.
AvgPoint calcAvgPoint(MhPlayerInfo pi, MhWaits waits, {bool isRiichi = false}) {
  final riichi = isRiichi || pi.isRiichi;
  final isFuriten = pi.isFuriten(waits);
  // 후리텐은 쯔모뿐. 리치 쪽은 보정식에 넣었으므로 다마·울기 때만 쯔모로 센다.
  final isTsumo = isFuriten && !riichi;

  final tileAgariRate = agariRateOfEachTile(waits, pi.discardTiles, pi.doraTiles);
  var sum = 0.0;
  var weight = 0.0;
  final results = <PointResult>[];
  for (final e in waits.entries) {
    final tile = e.key;
    if (e.value == 0) continue;
    pi.handTiles34[tile]++;
    final result = calcPoint(pi, tile, isTsumo: isTsumo, isRiichi: riichi);
    pi.handTiles34[tile]--;
    if (result.point == 0) continue; // 후즈케·편대기 등 역 없음은 빼고
    var pt = result.point.toDouble();
    if (riichi) {
      pt = result.fixedRiichiPoint(isFuriten);
      result.fixedPoint = pt;
    }
    final w = tileAgariRate[tile] ?? 0.0;
    sum += pt * w;
    weight += w;
    result.agariRate = w;
    results.add(result);
  }
  return AvgPoint(weight > 0 ? sum / weight : 0.0, results);
}

/// 원본 `CalcAvgRiichiPoint`. 울었으면 0.
AvgPoint calcAvgRiichiPoint(MhPlayerInfo pi, MhWaits waits) {
  if (pi.isNaki) return const AvgPoint(0, []);
  return calcAvgPoint(pi, waits, isRiichi: true);
}

/// 원본 `mixedRoundPoint`(국수지): 화료율/100·(점수 + 1500) − 1500.
/// 리치 점수가 있으면 리치, 없으면 다마(울기) 점수.
double mixedRoundPoint(
    {required double avgAgariRate,
    required double riichiPoint,
    required double damaPoint}) {
  const weight = -1500;
  if (riichiPoint > 0) {
    return avgAgariRate / 100 * (riichiPoint + 1500) + weight;
  }
  return avgAgariRate / 100 * (damaPoint + 1500) + weight;
}
