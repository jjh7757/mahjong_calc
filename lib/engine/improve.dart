// Ported from EndlessCheng/mahjong-helper (MIT)
//   util/shanten_improve.go(Hand13AnalysisResult · speedScore · mixedRoundPoint ·
//   node13/node14 analysis · _stopShanten · CalculateShantenWithImproves13/14 ·
//   calculateIsolatedTileValue · calculateTileValue · Hand14AnalysisResult · Sort),
//   util/shanten_search.go(_search13 · _search14 · searchShanten14 ·
//   CalculateShantenAndWaits13)
// Copyright (c) 2018 Σndless
// 원본 LICENSE 전문: third_party/mahjong-helper/LICENSE
//
// 버림 평가의 몸통: 샹텐 탐색 나무를 만들고, 13장 마디마다 유효패 · 개량 ·
// 전진 뒤 유효패 · 속도 점수 · (텐파이면) 화료율 · 타점 · 국수지를 매기고,
// 14장 마디에서 버림 후보를 원본 `Sort` 순서로 줄 세운다.
//
// 원본과 다른 점(동작은 같게 두려 했다):
// - Go map 순회는 매번 순서가 다르다. 여기서는 패 번호 오름차순으로 만들고
//   원본 `sort.Slice` 의 작은 배열 경로(삽입 정렬, 12개 이하)와 같은 삽입
//   정렬로 줄 세운다. 그래서 동점일 때 원본은 실행마다 달라질 수 있고 이쪽은
//   패 번호가 작은 쪽이 앞에 남는다.
// - 샹텐은 원본 알고리즘 대신 우리 shanten.dart(일반형·치또이, 국사 빼고)를 쓴다.
// - 울기 판단(CalculateMeld)은 이번 범위가 아니라 옮기지 않았다.

import 'dart:math' as math;

import 'agari_rate.dart';
import 'calculator.dart';
import 'hand_value.dart';
import 'mh_player.dart';

export 'mh_player.dart' show MhWaits, MhPlayerInfo;

const int shantenStateAgari = -1;
const int shantenStateTenpai = 0;

// ---------------------------------------------------------------------------
// shanten_search.go

class ShantenSearchNode13 {
  final int shanten;
  final MhWaits waits;

  /// 샹텐이 앞으로 가는 쯔모 → 14장 마디. 값이 null 이면 더 안 내려간 것.
  final Map<int, ShantenSearchNode14?> children;

  ShantenSearchNode13(this.shanten, this.waits, this.children);
}

class ShantenSearchNode14 {
  final int shanten;

  /// 샹텐을 지키는 버림 → 13장 마디.
  final Map<int, ShantenSearchNode13> children;

  ShantenSearchNode14(this.shanten, this.children);
}

ShantenSearchNode13 _search13(
    int currentShanten, MhPlayerInfo pi, int stopAtShanten) {
  final waits = MhWaits();
  final children = <int, ShantenSearchNode14?>{};
  final tiles34 = pi.handTiles34;
  final left34 = pi.leftTiles34;
  final isTenpai = currentShanten == shantenStateTenpai;

  for (var i = 0; i < 34; i++) {
    if (tiles34[i] == 4) continue;
    tiles34[i]++;
    if (isTenpai) {
      // 텐파이면 화료 판정만
      if (mhIsAgari(tiles34)) {
        waits[i] = left34[i];
        children[i] = null;
      }
    } else {
      if (mhShanten(tiles34) < currentShanten) {
        // 샹텐 전진 → 유효패. 남은 0 이어도 후리텐 판정용으로 남긴다(원본 주석).
        waits[i] = left34[i];
        if (left34[i] > 0 && currentShanten - 1 >= stopAtShanten) {
          left34[i]--;
          children[i] = _search14(currentShanten - 1, pi, stopAtShanten);
          left34[i]++;
        } else {
          children[i] = null;
        }
      }
    }
    tiles34[i]--;
  }
  return ShantenSearchNode13(currentShanten, waits, children);
}

/// [targetShanten] 이 지금 샹텐 + 1 이면 샹텐 후퇴 탐색이 된다(원본 주석).
ShantenSearchNode14 _search14(
    int targetShanten, MhPlayerInfo pi, int stopAtShanten) {
  final children = <int, ShantenSearchNode13>{};
  final tiles34 = pi.handTiles34;
  for (var i = 0; i < 34; i++) {
    if (tiles34[i] == 0) continue;
    tiles34[i]--;
    if (mhShanten(tiles34) == targetShanten) {
      children[i] = _search13(targetShanten, pi, stopAtShanten);
    }
    tiles34[i]++;
  }
  return ShantenSearchNode14(targetShanten, children);
}

/// 원본 `CalculateShantenAndWaits13`: 3k+1 장의 샹텐과 유효패(남은 장수 반영),
/// 개량은 안 본다. [leftTiles34] 가 null 이면 4 − 손패.
(int, MhWaits) calculateShantenAndWaits13(
    List<int> tiles34, List<int>? leftTiles34) {
  final left = leftTiles34 ?? [for (final c in tiles34) 4 - c];
  final shanten = mhShanten(tiles34);
  final pi = MhPlayerInfo(handTiles34: tiles34, leftTiles34: left);
  final node13 = _search13(shanten, pi, shanten); // 한 층만
  return (shanten, node13.waits);
}

/// 원본 `searchShanten14`.
ShantenSearchNode14 searchShanten14(
    int shanten, MhPlayerInfo pi, int stopAtShanten) {
  if (shanten == shantenStateAgari) {
    return ShantenSearchNode14(shanten, {});
  }
  return _search14(shanten, pi, stopAtShanten);
}

// ---------------------------------------------------------------------------
// shanten_improve.go

/// 원본 `Hand13AnalysisResult`: 3k+1 장 손의 분석.
class Hand13AnalysisResult {
  /// 원 손패(복사본).
  final List<int> tiles34;

  /// 남은 패(이 마디를 분석할 때의 복사본).
  final List<int> leftTiles34;

  /// 울었는지(역 없음 판단 등).
  final bool isNaki;

  final int shanten;

  /// 유효패(남은 장수 반영). 4장 다 보이면 값 0.
  final MhWaits waits;

  /// 다마(울기)로 화료할 수 있는 대기.
  final MhWaits damaWaits = MhWaits();

  /// 유효패 → 전진 뒤 (최대) 유효패 수.
  final Map<int, int> nextShantenWaitsCountMap;

  /// 전진 뒤 (최대) 유효패 수의 가중평균(원본 195–201, 393–402).
  double avgNextShantenWaitsCount = 0;

  /// 유효패와 전진 뒤 유효패를 합친 속도 점수(원본 `speedScore`, 2샹텐 /4).
  double mixedWaitsScore = 0;

  /// 개량: 샹텐은 그대로지만 유효패가 늘어나는 쯔모 → 그때 (최대) 유효패.
  /// `improves.length` 가 개량 종류 수.
  final Map<int, MhWaits> improves;

  /// 유효패를 늘리는 쯔모-버림 경우의 수.
  final int improveWayCount;

  /// 유효패가 아닌 쯔모를 했을 때의 유효패 가중평균(개량 + 비개량, 한 순만).
  /// 개량이 없으면 유효패 수 그대로.
  /// TODO(원본): 개량을 넣은 채 전진까지 걸리는 쯔모 수 기대값(몬테카를로?)
  double avgImproveWaitsCount;

  /// 텐파이일 때 화료율(%). TODO(원본): 텐파이 전 화료율?
  double avgAgariRate = 0;

  /// 후리텐 가능성(1샹텐 0.5 · 텐파이 1). 0.5 는 원본 TODO 임시값.
  double furitenRate = 0;

  /// 역(원본 `YakuTypes`). 도라 제외.
  final Set<Yaku> yakuTypes;

  /// (울었을 때) 편대기인지.
  bool isPartWait = false;

  /// 도라 수(손패 + 울기 + 적5).
  final int doraCount;

  /// 리치 안 할 때(울기·다마) 기대 타점.
  double damaPoint = 0;

  /// 리치할 때 기대 타점.
  double riichiPoint = 0;

  /// 국수지.
  double mixedRoundPoint = 0;

  Hand13AnalysisResult({
    required this.tiles34,
    required this.leftTiles34,
    required this.isNaki,
    required this.shanten,
    required this.waits,
    required this.nextShantenWaitsCountMap,
    required this.improves,
    required this.improveWayCount,
    required this.avgImproveWaitsCount,
    required this.yakuTypes,
    required this.doraCount,
  });

  /// 원본 `speedScore`: 두 번 전진할 확률로 거칠게 본 점수(×100).
  /// p1 == p2 이면 0/0 이 되어 NaN 이 나온다 — 원본 Go 도 같다(고치지 않음).
  double speedScore() {
    final waitsCount = waits.allCount;
    if (waitsCount == 0 || avgNextShantenWaitsCount == 0) return 0;
    final leftCount = mhCountTiles34(leftTiles34).toDouble();
    final p2 = waitsCount / leftCount;
    //p2 := r.AvgImproveWaitsCount / leftCount
    final p1 = avgNextShantenWaitsCount / leftCount;
    // TODO(원본): 화료율을 쓰려면 순목을 생각해야
    final p2_ = 1 - p2, p1_ = 1 - p1;
    const leftTurns = 10.0; // math.Max(5.0, leftCount/4)
    final sumP2 = p2_ * (1 - _pow(p2_, leftTurns)) / p2;
    final sumP1 = p1_ * (1 - _pow(p1_, leftTurns)) / p1;
    final result = p2 * p1 * (sumP2 - sumP1) / (p2_ - p1_);
    return result * 100;
  }

  /// 원본 `mixedRoundPoint`.
  double computeMixedRoundPoint() => _mixedRoundPointOf(this);

  @override
  String toString() {
    final b = StringBuffer(
        '${waits.allCount} 유효패 $waits ${avgImproveWaitsCount.toStringAsFixed(2)} 개량 '
        '[${improves.length}($improveWayCount)종]');
    if (shanten >= 1) {
      b.write(' ${avgNextShantenWaitsCount.toStringAsFixed(2)} 전진뒤 '
          '(${mixedWaitsScore.toStringAsFixed(2)} 속도)');
    }
    if (avgAgariRate > 0) b.write(' [${avgAgariRate.toStringAsFixed(2)}% 화료율]');
    if (mixedRoundPoint > 0) b.write(' [국수지 ${mixedRoundPoint.round()}]');
    if (damaPoint > 0) b.write(' [다마 ${damaPoint.round()}]');
    if (riichiPoint > 0) b.write(' [리치 ${riichiPoint.round()}]');
    if (furitenRate > 0) b.write(furitenRate < 1 ? ' [후리텐 가능]' : ' [후리텐]');
    return b.toString();
  }
}

double _pow(double x, double n) => math.pow(x, n).toDouble();

double _mixedRoundPointOf(Hand13AnalysisResult r) => mixedRoundPoint(
    avgAgariRate: r.avgAgariRate,
    riichiPoint: r.riichiPoint,
    damaPoint: r.damaPoint);

Hand13AnalysisResult _analysis13(
    ShantenSearchNode13 n, MhPlayerInfo pi, bool considerImprove) {
  final tiles34 = pi.handTiles34;
  final left34 = pi.leftTiles34;
  final shanten13 = n.shanten;
  final waits = n.waits;
  final waitsCount = waits.allCount;

  final nextShantenWaitsCountMap = <int, int>{};
  final improves = <int, MhWaits>{};
  var improveWayCount = 0;
  // 쯔모마다 그 뒤 유효패 수(유효패를 뽑으면 waitsCount 로 본다)
  final maxImproveWaitsCount34 = List<int>.filled(34, waitsCount);
  var avgRoundPoint = 0.0;
  var roundPointWeight = 0;
  final yakuTypes = <Yaku>{};

  for (var i = 0; i < 34; i++) {
    // 남은 패에서 쯔모
    if (left34[i] == 0) continue;
    left34[i]--;
    tiles34[i]++;

    final node14 = n.children[i];
    if (node14 != null) {
      // 유효패: 전진 뒤 최대 유효패
      var maxNext = 0;
      for (final node13 in node14.children.values) {
        final c = node13.waits.allCount;
        if (c > maxNext) maxNext = c;
      }
      nextShantenWaitsCountMap[i] = maxNext;

      final results14 = _analysis14(node14, pi, false);
      if (results14.isNotEmpty) {
        final best = results14[0];
        // 가중: 유효패 남은 장수 × 국수지
        final w = left34[i] + 1;
        avgRoundPoint += w * best.result13.mixedRoundPoint;
        roundPointWeight += w;
        yakuTypes.addAll(best.result13.yakuTypes);
      }
    } else if (considerImprove) {
      // 유효패는 아니지만 개량일 수 있다
      for (var j = 0; j < 34; j++) {
        if (tiles34[j] == 0 || j == i) continue;
        // 적5 만 있으면 적5 를 버린다(TODO(원본): 적5 로 37 속이기)
        final isRed = pi.isOnlyRedFive(j);
        pi.discardTile(j, isRed);
        final (newShanten13, improveWaits) =
            calculateShantenAndWaits13(tiles34, left34);
        if (newShanten13 == shanten13) {
          // 유효패가 늘면 개량. TODO(원본): 타점이 올라도 개량으로
          final c = improveWaits.allCount;
          if (c > waitsCount) {
            improveWayCount++;
            if (c > maxImproveWaitsCount34[i]) {
              maxImproveWaitsCount34[i] = c;
              improves[i] = improveWaits; // 유효패가 가장 많은 개량
            }
          }
        }
        pi.undoDiscardTile(j, isRed);
      }
    }

    tiles34[i]--;
    left34[i]++;
  }

  final result13 = Hand13AnalysisResult(
    tiles34: List.of(tiles34),
    leftTiles34: List.of(left34),
    isNaki: pi.isNaki,
    shanten: shanten13,
    waits: waits,
    nextShantenWaitsCountMap: nextShantenWaitsCountMap,
    improves: improves,
    improveWayCount: improveWayCount,
    avgImproveWaitsCount: waitsCount.toDouble(),
    yakuTypes: yakuTypes,
    doraCount: pi.countDora(),
  );

  // 국수지·타점·화료율·역
  if (waitsCount > 0) {
    if (roundPointWeight > 0) {
      avgRoundPoint /= roundPointWeight;
      // (원본 주석 처리) 1샹텐 /6, 2샹텐 /18 — TODO 조정?
    }
    if (shanten13 == shantenStateTenpai) {
      // TODO(원본): 다마 쯔모
      final dama = calcAvgPoint(pi, waits);
      result13.damaPoint = dama.avgPoint;
      for (final pr in dama.pointResults) {
        result13.damaWaits[pr.winTile] = left34[pr.winTile];
      }

      if (!result13.isNaki) {
        final riichi = calcAvgRiichiPoint(pi, waits);
        result13.riichiPoint = riichi.avgPoint;
        result13.avgAgariRate = avgAgariRate(waits,
            discardTiles: pi.discardTiles, doraTiles: pi.doraTiles);
        for (final pr in riichi.pointResults) {
          result13.yakuTypes.addAll(pr.yaku);
        }
      } else {
        // 울었으면 역 없는 대기(후즈케·편대기)는 화료율에서 뺀다
        var agariRate = 0.0;
        for (final pr in dama.pointResults) {
          agariRate = agariRate + pr.agariRate - agariRate * pr.agariRate / 100;
          result13.yakuTypes.addAll(pr.yaku);
        }
        result13.avgAgariRate = agariRate;
        result13.isPartWait =
            dama.pointResults.length < waits.availableTiles.length;
      }
    }
  }

  // 3샹텐 치또이 알림
  if (pi.melds.isEmpty &&
      shanten13 == 3 &&
      mhCountPairs34(tiles34) + shanten13 == 6) {
    if (waitsCount <= 21) result13.yakuTypes.add(Yaku.chiitoitsu);
  }

  // 텐파이·1샹텐 후리텐 가능성
  if (shanten13 <= 1) {
    for (final d in pi.discardTiles) {
      if (waits.containsKey(d)) {
        result13.furitenRate = 0.5; // TODO(원본): 다듬기
        if (shanten13 == shantenStateTenpai) result13.furitenRate = 1;
      }
    }
  }

  // 국수지
  if (shanten13 == shantenStateTenpai) {
    result13.mixedRoundPoint = result13.computeMixedRoundPoint();
  } else {
    result13.mixedRoundPoint = avgRoundPoint;
  }

  // 손 속도
  if (nextShantenWaitsCountMap.isNotEmpty) {
    var sum = 0;
    var weight = 0;
    for (final e in nextShantenWaitsCountMap.entries) {
      final w = left34[e.key];
      sum += w * e.value;
      weight += w;
    }
    result13.avgNextShantenWaitsCount = sum / weight;
  }
  if (improves.isNotEmpty) {
    var sum = 0;
    var weight = 0;
    for (var i = 0; i < 34; i++) {
      final w = left34[i];
      sum += w * maxImproveWaitsCount34[i];
      weight += w;
    }
    result13.avgImproveWaitsCount = sum / weight;
  }
  result13.mixedWaitsScore = result13.speedScore();

  // 샹텐 후퇴를 알리기 쉽게 하려는 특수 처리
  if (shanten13 == 2) {
    result13.mixedWaitsScore /= 4; // TODO(원본): 조정
  }
  return result13;
}

/// 원본 `_stopShanten`: 탐색을 어디까지 내려갈지.
int stopShanten(int shanten) => shanten >= 3 ? shanten - 1 : shanten - 2;

/// 원본 `CalculateShantenWithImproves13`: 3k+1 장.
Hand13AnalysisResult calculateShantenWithImproves13(MhPlayerInfo pi) {
  final shanten = mhShanten(pi.handTiles34);
  final root = _search13(shanten, pi, stopShanten(shanten));
  return _analysis13(root, pi, true);
}

// ---- 버림 값(2샹텐 이상에서 고립 요구패 비교용) ----

const int honorRiskRoundWind = 4;
const int honorRiskYaku = 3;
const int honorRiskOtakaze = 2;
const int honorRiskSelfWind = 1;

const double doraValue = 10000;
const double doraFirstNeighbourValue = 1000;
const double doraSecondNeighbourValue = 100;
const double honoredValue = 15;

/// 원본 `calculateIsolatedTileValue`.
double calculateIsolatedTileValue(int tile, MhPlayerInfo pi) {
  var value = 100.0;

  for (final dora in pi.doraTiles) {
    if (tile == dora) value += doraValue;
    // (원본 주석 처리) 도라 이웃 가치
  }

  if (tile >= 27) {
    if (tile == pi.selfWindTile || tile == pi.roundWindTile || tile >= 31) {
      // 역패
      value += honoredValue;
      if (pi.selfWindTile == pi.roundWindTile && tile == pi.selfWindTile) {
        value += honoredValue; // 연풍
      } else if (tile == pi.selfWindTile) {
        value++; // 자풍 +1
      } else if (tile == pi.roundWindTile) {
        value--; // 장풍 −1
      }
      if (tile == 31) value -= 0.1;
      if (tile == 32) value -= 0.2;
    } else {
      // 객풍: 하가 −3, 대면 −2, 상가 −1
      for (var i = 1; i <= 3; i++) {
        var otakaze = pi.selfWindTile + i;
        if (otakaze > 30) otakaze -= 4;
        if (tile == otakaze) {
          value -= 4 - i;
          break;
        }
      }
    }
    final left = pi.leftTiles34[tile];
    if (left == 2) {
      value *= 0.9;
    } else if (left == 1) {
      value *= 0.2;
    } else if (left == 0) {
      value = 0;
    }
  }
  return value;
}

/// 원본 `calculateTileValue`: 도라 또는 도라 이웃.
double calculateTileValue(int tile, MhPlayerInfo pi) {
  var value = 0.0;
  for (final dora in pi.doraTiles) {
    if (tile == dora) {
      value += doraValue;
    } else if (dora < 27) {
      if (tile ~/ 3 != dora ~/ 3) continue; // 원본 그대로 /3(같은 세 칸 묶음)
      final t9 = tile % 9;
      final dt9 = dora % 9;
      if (t9 + 1 == dt9 || t9 - 1 == dt9) {
        value += doraFirstNeighbourValue;
      } else if (t9 + 2 == dt9 || t9 - 2 == dt9) {
        value += doraSecondNeighbourValue;
      }
    }
  }
  return value;
}

/// 원본 `Hand14AnalysisResult`: 버림 후보 하나.
class Hand14AnalysisResult {
  final int discardTile;
  final bool isDiscardDoraTile;

  /// 버린 패의 값(2샹텐 이상에서만 매김).
  double discardTileValue = 0;

  /// 버린 패가 고립 요구패인지(2샹텐 이상에서만).
  bool isIsolatedYaochuDiscardTile = false;

  final Hand13AnalysisResult result13;

  int discardHonorTileRisk = 0;
  final int leftDrawTilesCount;

  Hand14AnalysisResult({
    required this.discardTile,
    required this.isDiscardDoraTile,
    required this.result13,
    required this.leftDrawTilesCount,
  });

  @override
  String toString() => '${Tiles.toCode(discardTile)} 버림: $result13';
}

List<Hand14AnalysisResult> _analysis14(
    ShantenSearchNode14 n, MhPlayerInfo pi, bool considerImprove) {
  final results = <Hand14AnalysisResult>[];
  final keys = n.children.keys.toList()..sort();
  for (final discardTile in keys) {
    final node13 = n.children[discardTile]!;
    final isRed = pi.isOnlyRedFive(discardTile);

    // 버리고 3k+1 장을 분석. 적5 만 있으면 적5 를 버린다(TODO(원본): 적5 로 37 속이기)
    pi.discardTile(discardTile, isRed);
    final r13 = _analysis13(node13, pi, considerImprove);

    final r14 = Hand14AnalysisResult(
      discardTile: discardTile,
      isDiscardDoraTile: pi.doraTiles.contains(discardTile),
      result13: r13,
      leftDrawTilesCount: pi.leftDrawTilesCount,
    );
    results.add(r14);

    if (n.shanten >= 2) {
      if (mhIsYaochupai(discardTile) &&
          mhIsIsolatedTile(discardTile, pi.handTiles34)) {
        r14.isIsolatedYaochuDiscardTile = true;
        r14.discardTileValue = calculateIsolatedTileValue(discardTile, pi);
      } else {
        r14.discardTileValue = calculateTileValue(discardTile, pi);
      }
    }

    if (discardTile >= 27) {
      if (discardTile == pi.roundWindTile) {
        r14.discardHonorTileRisk = honorRiskRoundWind;
      } else if (discardTile >= 31) {
        r14.discardHonorTileRisk = honorRiskYaku;
      } else if (discardTile == pi.selfWindTile) {
        r14.discardHonorTileRisk = honorRiskSelfWind;
      } else {
        r14.discardHonorTileRisk = honorRiskOtakaze;
      }
    }

    pi.undoDiscardTile(discardTile, isRed);
  }
  // (원본: improveFirst 는 「종합 속도」로 대체되어 주석 처리)
  sortResults14(results, improveFirst: false);
  return results;
}

/// 원본 `Hand14AnalysisResultList.Sort` 의 less 함수.
bool _less(Hand14AnalysisResult a, Hand14AnalysisResult b, int shanten,
    bool improveFirst) {
  final ri = a.result13, rj = b.result13;
  final riWaitsCount = ri.waits.allCount, rjWaitsCount = rj.waits.allCount;

  // 유효패 0 은 무조건 뒤로(개량도 안 봄). 둘 다 0 이면 개량으로.
  if (riWaitsCount == 0 || rjWaitsCount == 0) {
    if (riWaitsCount == 0 && rjWaitsCount == 0) {
      return ri.avgImproveWaitsCount > rj.avgImproveWaitsCount;
    }
    return riWaitsCount > rjWaitsCount;
  }

  switch (shanten) {
    case 0:
      // 텐파이: 국수지(100 넘게 차이 날 때) → 화료율
      if (!mhInDelta(ri.mixedRoundPoint, rj.mixedRoundPoint, 100)) {
        return ri.mixedRoundPoint > rj.mixedRoundPoint;
      }
      if (!mhEqual(ri.avgAgariRate, rj.avgAgariRate)) {
        return ri.avgAgariRate > rj.avgAgariRate;
      }
      break;
    case 1:
      // 1샹텐: 유효패 × 국수지
      double riScore = 0, rjScore = 0;
      var skip = false;
      if (shanten >= 2 && improveFirst) {
        // (원본: 2샹텐 개량 우선 — 이 case 에서는 닿지 않음)
        skip = true;
      } else {
        // 음수면 뒤집는다
        var wi = riWaitsCount.toDouble();
        if (ri.mixedRoundPoint < 0) wi = 1 / wi;
        var wj = rjWaitsCount.toDouble();
        if (rj.mixedRoundPoint < 0) wj = 1 / wj;
        riScore = wi * ri.mixedRoundPoint;
        rjScore = wj * rj.mixedRoundPoint;
      }
      if (!skip && !mhEqual(riScore, rjScore)) return riScore > rjScore;
      break;
  }

  if (shanten >= 2) {
    // 2샹텐 이상: 고립 요구패는 값으로 따로 비교
    if (a.isIsolatedYaochuDiscardTile && b.isIsolatedYaochuDiscardTile) {
      if (a.discardTileValue != b.discardTileValue) {
        return a.discardTileValue < b.discardTileValue;
      }
    } else if (a.isIsolatedYaochuDiscardTile && a.discardTileValue < 500) {
      return true;
    } else if (b.isIsolatedYaochuDiscardTile && b.discardTileValue < 500) {
      return false;
    }
  }

  // 속도 → 유효패 → 전진 뒤 유효패 → 화료율 → 개량 → 값 낮은 패 먼저 → 좋은 패 먼저
  if (!mhEqual(ri.mixedWaitsScore, rj.mixedWaitsScore)) {
    return ri.mixedWaitsScore > rj.mixedWaitsScore;
  }
  if (riWaitsCount != rjWaitsCount) return riWaitsCount > rjWaitsCount;
  if (!mhEqual(ri.avgNextShantenWaitsCount, rj.avgNextShantenWaitsCount)) {
    return ri.avgNextShantenWaitsCount > rj.avgNextShantenWaitsCount;
  }
  if (!mhEqual(ri.avgAgariRate, rj.avgAgariRate)) {
    return ri.avgAgariRate > rj.avgAgariRate;
  }
  if (!mhEqual(ri.avgImproveWaitsCount, rj.avgImproveWaitsCount)) {
    return ri.avgImproveWaitsCount > rj.avgImproveWaitsCount;
  }
  if (a.discardTileValue != b.discardTileValue) {
    return a.discardTileValue < b.discardTileValue; // 값 낮은 패 먼저
  }

  // 좋은 패 먼저(가운데 패를 먼저 버린다)
  var idxI = a.discardTile, idxJ = b.discardTile;
  if (idxI < 27 && idxJ < 27) {
    idxI %= 9;
    if (idxI > 4) idxI = 8 - idxI;
    idxJ %= 9;
    if (idxJ > 4) idxJ = 8 - idxJ;
    return idxI > idxJ;
  }
  if (idxI < 27 || idxJ < 27) {
    return idxI < idxJ; // 수패 먼저
  }
  // 장풍 − 삼원패 − 객풍 − 자풍
  return a.discardHonorTileRisk > b.discardHonorTileRisk;
}

/// 원본 `Sort(improveFirst)`. 원본 `sort.Slice` 의 12개 이하 경로와 같은
/// 삽입 정렬(제자리).
void sortResults14(List<Hand14AnalysisResult> l, {bool improveFirst = false}) {
  if (l.length <= 1) return;
  final shanten = l[0].result13.shanten;
  for (var i = 1; i < l.length; i++) {
    for (var j = i; j > 0 && _less(l[j], l[j - 1], shanten, improveFirst); j--) {
      final t = l[j];
      l[j] = l[j - 1];
      l[j - 1] = t;
    }
  }
}

/// 원본 `CalculateShantenWithImproves14`의 결과.
class Improves14 {
  final int shanten;

  /// 샹텐을 지키는 버림(정렬됨).
  final List<Hand14AnalysisResult> results;

  /// 샹텐이 하나 물러나는 버림(정렬됨).
  final List<Hand14AnalysisResult> incShantenResults;

  const Improves14(this.shanten, this.results, this.incShantenResults);
}

/// 원본 `CalculateShantenWithImproves14`: 3k+2 장.
Improves14 calculateShantenWithImproves14(MhPlayerInfo pi) {
  final shanten = mhShanten(pi.handTiles34);
  final stop = stopShanten(shanten);
  final root = searchShanten14(shanten, pi, stop);
  final results = _analysis14(root, pi, true);
  final incRoot = searchShanten14(shanten + 1, pi, stop + 1);
  final incResults = _analysis14(incRoot, pi, true);
  return Improves14(shanten, results, incResults);
}
