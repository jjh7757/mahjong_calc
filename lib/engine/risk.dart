// Ported from EndlessCheng/mahjong-helper (MIT)
//   util/risk_base.go (전부), util/risk_wall.go (벽 · 노찬스 · 더블 노찬스),
//   util/tile.go `OutsideTiles`, core.go:308-415 `analysisTilesRisk` · `doraNum`,
//   core.go:772-850 (버림 사건 처리 중 위험도에 쓰는 상태), cli.go:161-175 `mixedRiskTable`.
// Copyright (c) 2018 Σndless — MIT License, see third_party/mahjong-helper/LICENSE
// 원본 커밋 514bb97c5a6d157fa2ed1ac804a53cb9b559d7d0.
//
// 방총 위험도(%)와 상대 텐파이율. 원본의 TODO · 임시값은 그대로 두고 `TODO(원본)` 으로 표시했다.
// 원찬스(`CalcOCSafeTiles`)는 원본이 위험도 계산에 쓰지 않아(cli 표시에만 씀) 옮기지 않았다.
library;

import 'risk_data.dart';
import 'tenpai_rate.dart';
import 'tile.dart';

export 'tenpai_rate.dart' show MeldKind;

// ---------------------------------------------------------------------------
// util/risk_wall.go
// ---------------------------------------------------------------------------

/// 원본 `WallSafeType*`. 원찬스 종류는 옮기지 않았다.
abstract final class WallSafeType {
  /// 단기 · 샤보만 진다.
  static const int doubleNoChance = 0;

  /// 단기 · 샤보 · 변짱 · 간짱(양면은 없음).
  static const int noChance = 1;
}

class WallSafeTile {
  final int tile34;
  final int safeType;
  const WallSafeTile(this.tile34, this.safeType);

  @override
  bool operator ==(Object other) => other is WallSafeTile && other.tile34 == tile34 && other.safeType == safeType;

  @override
  int get hashCode => tile34 * 8 + safeType;

  @override
  String toString() => '${Tiles.toCode(tile34)}/$safeType';
}

/// 원본 `WallSafeTileList.sort`: 345(6) 쪽을 뒤로, 같은 쪽 안에서는 종류 → 끝에서 거리 순.
/// 바꾼 점: Go `sort.Slice` 는 안정 정렬이 아니라 같은 키끼리 순서가 정해지지 않는다. 여기서는 마지막에 패 번호로 끊어 늘 같은 순서를 낸다.
void _sortWallSafeTiles(List<WallSafeTile> l) {
  int normalIndex(int tile34) {
    var idx = tile34 % 9;
    if (idx >= 5) idx = 8 - idx; // 5678 -> 3210
    return idx;
  }

  l.sort((a, b) {
    final ai = normalIndex(a.tile34);
    final bi = normalIndex(b.tile34);
    if (ai > 2 && bi <= 2 || ai <= 2 && bi > 2) return ai.compareTo(bi);
    if (a.safeType != b.safeType) return a.safeType.compareTo(b.safeType);
    if (ai != bi) return ai.compareTo(bi);
    return a.tile34.compareTo(b.tile34);
  });
}

/// 원본 `CalcDNCSafeTiles`: 남은 장수 0(벽)으로 더블 노찬스(단기 · 샤보만 짐)인 수패.
List<WallSafeTile> calcDNCSafeTiles(List<int> leftTiles34) {
  bool nc(int idx) => leftTiles34[idx] == 0;
  bool or(List<int> idx) => idx.any(nc);
  bool and(List<int> idx) => idx.every(nc);

  const safeType = WallSafeType.doubleNoChance;
  final out = <WallSafeTile>[];
  for (var i = 0; i < 3; i++) {
    // 2/3 벽의 1
    if (or([9 * i + 1, 9 * i + 2])) out.add(WallSafeTile(9 * i, safeType));
    // 3 또는 14 벽의 2
    if (nc(9 * i + 2) || and([9 * i, 9 * i + 3])) out.add(WallSafeTile(9 * i + 1, safeType));
    // 14/24/25 벽의 3 (4567 도 같은 식)
    for (var j = 2; j <= 6; j++) {
      final idx = 9 * i + j;
      if (and([idx - 2, idx + 1]) || and([idx - 1, idx + 1]) || and([idx - 1, idx + 2])) {
        out.add(WallSafeTile(idx, safeType));
      }
    }
    // 7 또는 69 벽의 8
    if (nc(9 * i + 6) || and([9 * i + 5, 9 * i + 8])) out.add(WallSafeTile(9 * i + 7, safeType));
    // 7/8 벽의 9
    if (or([9 * i + 6, 9 * i + 7])) out.add(WallSafeTile(9 * i + 8, safeType));
  }
  _sortWallSafeTiles(out);
  return out;
}

/// 원본 `CalcDNCSafeTilesWithDiscards`: 벽 + 현물로 더 정확한 더블 노찬스.
/// 원본 주석: 4 가 현물이면 1 도 단기 · 샤보만 지지만, 벽 이야기가 아니라 여기서는 다루지 않는다.
List<WallSafeTile> calcDNCSafeTilesWithDiscards(List<int> leftTiles34, List<bool> safeTiles34) {
  bool nc(int idx) => leftTiles34[idx] == 0;
  const safeType = WallSafeType.doubleNoChance;
  final out = calcDNCSafeTiles(leftTiles34);
  // 한쪽 옆이 벽이고 다른 쪽 스지가 현물이면 DNC. 예: 3 은 2 가 벽이고 6 이 현물.
  for (var i = 0; i < 3; i++) {
    for (var j = 1; j < 3; j++) {
      final idx = 9 * i + j;
      if (nc(idx - 1) && safeTiles34[idx + 3]) out.add(WallSafeTile(idx, safeType));
    }
    for (var j = 3; j < 6; j++) {
      final idx = 9 * i + j;
      if (nc(idx - 1) && safeTiles34[idx + 3] || nc(idx + 1) && safeTiles34[idx - 3]) {
        out.add(WallSafeTile(idx, safeType));
      }
    }
    for (var j = 6; j < 8; j++) {
      final idx = 9 * i + j;
      if (nc(idx + 1) && safeTiles34[idx - 3]) out.add(WallSafeTile(idx, safeType));
    }
  }
  _sortWallSafeTiles(out);
  return out;
}

/// 원본 `CalcNCSafeTiles`: 벽으로 양면이 없는(노찬스) 수패.
List<WallSafeTile> calcNCSafeTiles(List<int> leftTiles34) {
  bool nc(int idx) => leftTiles34[idx] == 0;
  bool or(List<int> idx) => idx.any(nc);
  const safeType = WallSafeType.noChance;
  final out = <WallSafeTile>[];
  for (var i = 0; i < 3; i++) {
    for (var j = 0; j < 3; j++) {
      final idx = 9 * i + j;
      if (or([idx + 1, idx + 2])) out.add(WallSafeTile(idx, safeType));
    }
    for (var j = 3; j < 6; j++) {
      final idx = 9 * i + j;
      if (or([idx - 2, idx - 1]) && or([idx + 1, idx + 2])) out.add(WallSafeTile(idx, safeType));
    }
    for (var j = 6; j < 9; j++) {
      final idx = 9 * i + j;
      if (or([idx - 2, idx - 1])) out.add(WallSafeTile(idx, safeType));
    }
  }
  _sortWallSafeTiles(out);
  return out;
}

// ---------------------------------------------------------------------------
// util/risk_base.go
// ---------------------------------------------------------------------------

/// 원본 `calcLowRiskTiles27`: 현물 · 벽으로 위험이 아주 낮은 수패(스지 계산에 "현물" 로 씀). 1 = 낮음.
/// TODO(원본): 이른 바깥패로 생긴 스지는 따로 계산해야 할 수도.
List<int> calcLowRiskTiles27(List<bool> safeTiles34, List<int> leftTiles34) {
  final low = List<int>.filled(27, 0);
  for (var i = 0; i < 27; i++) {
    if (safeTiles34[i]) low[i] = 1;
  }
  for (var i = 0; i < 3; i++) {
    if (leftTiles34[9 * i + 1] == 0) low[9 * i] = 1; // 2 벽 → 1 을 낸 것으로
    if (leftTiles34[9 * i + 2] == 0) {
      low[9 * i] = 1; // 3 벽 → 12
      low[9 * i + 1] = 1;
    }
    if (leftTiles34[9 * i + 3] == 0) {
      low[9 * i + 1] = 1; // 4 벽 → 23
      low[9 * i + 2] = 1;
    }
    if (leftTiles34[9 * i + 5] == 0) {
      low[9 * i + 6] = 1; // 6 벽 → 78
      low[9 * i + 7] = 1;
    }
    if (leftTiles34[9 * i + 6] == 0) {
      low[9 * i + 7] = 1; // 7 벽 → 89
      low[9 * i + 8] = 1;
    }
    if (leftTiles34[9 * i + 7] == 0) low[9 * i + 8] = 1; // 8 벽 → 9
  }
  return low;
}

/// 원본 `calcTileType27`: 버림만으로 수패의 스지 종류. (원본에서도 부르는 곳이 없다 — 함께 옮겨만 둠.)
List<int> calcTileType27(List<int> discardTiles) {
  final out = List<int>.filled(27, 0);
  final safe = List<int>.filled(34, 0);
  for (final t in discardTiles) {
    safe[t] = 1;
  }
  for (var i = 0; i < 3; i++) {
    for (var j = 0; j < 3; j++) {
      final idx = 9 * i + j;
      out[idx] = tileTypeTable[j][safe[idx + 3]];
    }
    for (var j = 3; j < 6; j++) {
      final idx = 9 * i + j;
      out[idx] = tileTypeTable[j][safe[idx - 3] << 1 | safe[idx + 3]];
    }
    for (var j = 6; j < 9; j++) {
      final idx = 9 * i + j;
      out[idx] = tileTypeTable[j][safe[idx - 3]];
    }
  }
  return out;
}

/// 원본 `CalculateRiskTiles34`: 순목 · 현물(리치 뒤 통과패 포함) · 노찬스 · 도라로 기본 방총률(%).
/// 이른 바깥패 · 점수는 [fixWithEarlyOutside] · [fixWithPoint] 가 뒤에서 고친다.
///
/// - [turns]: 그 상대가 버린 수(1~[maxRiskTurns]).
/// - [safeTiles34]: 현물 및 리치 뒤 통과한 패.
/// - [leftTiles34]: 내 시점에서 아직 안 보인 장수.
/// - [roundWindTile] · [playerWindTile]: 장풍 · 그 상대의 자풍(27~30).
///
/// TODO(원본): 선언패의 스지 · 같은 색 패 특수 처리. 강등(1m 벽이면 2m 을 무스지 19 급, 3m 을 무스지 28 급으로).
List<double> calculateRiskTiles34(
  int turns,
  List<bool> safeTiles34,
  List<int> leftTiles34,
  List<int> doraTiles,
  int roundWindTile,
  int playerWindTile,
) {
  final risk34 = List<double>.filled(34, 0);
  final rate = riskRate[turns];

  // 도라만 위험도를 올린다(방총률 + 실점). 더블 도라 등은 더 올라간다.
  double doraMulti(int tile, int tileType) {
    var multi = 1.0;
    for (final dora in doraTiles) {
      if (tile == dora) multi *= fixedDoraRiskRateMulti[tileType];
    }
    return multi;
  }

  // 수패 화료 꼴: 19 양면·샤보단기 / 28 +간짱 / 37 +변짱 / 456 양면×2·간짱·샤보단기.
  final low = calcLowRiskTiles27(safeTiles34, leftTiles34);
  for (var i = 0; i < 3; i++) {
    for (var j = 0; j < 3; j++) {
      final idx = 9 * i + j;
      final t = tileTypeTable[j][low[idx + 3]];
      risk34[idx] = rate[t] * doraMulti(idx, t);
      if (j == 0 && safeTiles34[idx + 3] && leftTiles34[idx] == 0) {
        risk34[idx] = 0; // (1) 양면도 샤보단기도 불가 → 안전패
      }
    }
    for (var j = 3; j < 6; j++) {
      final idx = 9 * i + j;
      final t = tileTypeTable[j][low[idx - 3] << 1 | low[idx + 3]];
      risk34[idx] = rate[t] * doraMulti(idx, t);
    }
    for (var j = 6; j < 9; j++) {
      final idx = 9 * i + j;
      final t = tileTypeTable[j][low[idx - 3]];
      risk34[idx] = rate[t] * doraMulti(idx, t);
      if (j == 8 && safeTiles34[idx - 3] && leftTiles34[idx] == 0) {
        risk34[idx] = 0; // (9) 양면도 샤보단기도 불가 → 안전패
      }
    }
    // 5 벽: 37 을 스지 37 로 본다.
    if (leftTiles34[9 * i + 4] == 0) {
      const t = RiskTileType.suji37;
      risk34[9 * i + 2] = rate[t] * doraMulti(9 * i + 2, t);
      risk34[9 * i + 6] = rate[t] * doraMulti(9 * i + 6, t);
    }
  }
  for (var i = 27; i < 34; i++) {
    if (leftTiles34[i] > 0) {
      // 그 상대의 역패 = 장풍 / 자풍 / 백발중
      final isYakuHai = i == roundWindTile || i == playerWindTile || i >= 31;
      final t = honorTileType[isYakuHai ? 1 : 0][leftTiles34[i] - 1];
      risk34[i] = rate[t] * doraMulti(i, t);
    } else {
      risk34[i] = 0; // 남은 0 장은 안전패(국사무쌍 무시)
    }
  }

  // 노찬스: 12 ≈ 스지 1(2 는 1 보다 10% 더), 3 ≈ 스지 2, 456 ≈ 양스지(원본도 "존의?").
  for (final nc in calcNCSafeTiles(leftTiles34)) {
    final idx = nc.tile34;
    switch (idx % 9 + 1) {
      case 1 || 9:
        const t = RiskTileType.suji19;
        risk34[idx] = rate[t] * doraMulti(idx, t);
      case 2 || 8:
        const t = RiskTileType.suji19;
        risk34[idx] = rate[t] * 1.1 * doraMulti(idx, t);
      case 3 || 7:
        const t = RiskTileType.suji28;
        risk34[idx] = rate[t] * doraMulti(idx, t);
      case 4 || 6:
        const t = RiskTileType.doubleSuji46;
        risk34[idx] = rate[t] * doraMulti(idx, t);
      case 5:
        const t = RiskTileType.doubleSuji5;
        risk34[idx] = rate[t] * doraMulti(idx, t);
      default:
        throw StateError('[calculateRiskTiles34] 코드 오류: ncSafeTile = $idx');
    }
  }

  // 더블 노찬스: 샤보단기만 → 스지 19 급. 남은 0 장이면 현물로(국사 무시).
  for (final dnc in calcDNCSafeTilesWithDiscards(leftTiles34, safeTiles34)) {
    final tile = dnc.tile34;
    if (leftTiles34[tile] > 0) {
      const t = RiskTileType.suji19;
      risk34[tile] = rate[t] * doraMulti(tile, t);
      // 19 가 아니면 탕야오 위험이 조금 있다: ×1.1
      final t9 = tile % 9;
      if (t9 > 0 && t9 < 8) risk34[tile] *= 1.1;
    } else {
      risk34[tile] = 0;
    }
  }

  // 현물은 0.
  for (var i = 0; i < 34; i++) {
    if (safeTiles34[i]) risk34[i] = 0;
  }
  return risk34;
}

/// 원본 `FixWithEarlyOutside`: 5 순 안(리치 전)의 바깥패 ×0.4 (참고: 科学する麻雀).
/// 같은 패가 여러 번 들어 있으면 그만큼 거듭 곱한다(원본 그대로).
List<double> fixWithEarlyOutside(List<double> risk34, List<int> discardTiles) {
  for (final t in discardTiles) {
    risk34[t] *= 0.4;
  }
  return risk34;
}

List<double> fixWithGlobalMulti(List<double> risk34, double multi) {
  for (var i = 0; i < risk34.length; i++) {
    risk34[i] *= multi;
  }
  return risk34;
}

/// 원본 `FixWithPoint`: 론 점수 / 5172(리치 일발 아님 기준).
List<double> fixWithPoint(List<double> risk34, double ronPoint) => fixWithGlobalMulti(risk34, ronPoint / ronPointRiichiHiIppatsu);

/// 원본 `CalculateLeftNoSujiTiles`: 남은 무스지 123789(최대 18 종). 적을수록 그 무스지가 위험.
List<int> calculateLeftNoSujiTiles(List<bool> safeTiles34, List<int> leftTiles34) {
  final isNoSuji = List<bool>.filled(27, false);
  for (var i = 0; i < 3; i++) {
    // 456 이 안전패인가로 스지 판단
    for (var j = 3; j < 6; j++) {
      if (!safeTiles34[9 * i + j]) {
        isNoSuji[9 * i + j - 3] = true;
        isNoSuji[9 * i + j + 3] = true;
      }
    }
    // 5 벽: 37 은 스지
    if (leftTiles34[9 * i + 4] == 0) {
      isNoSuji[9 * i + 2] = false;
      isNoSuji[9 * i + 6] = false;
    }
  }
  // 4 장 다 보인 벽
  for (var i = 0; i < 27; i++) {
    if (leftTiles34[i] == 0) isNoSuji[i] = false;
  }
  // 노찬스 안전패
  final low = calcLowRiskTiles27(safeTiles34, leftTiles34);
  for (var i = 0; i < 27; i++) {
    if (low[i] == 1) isNoSuji[i] = false;
  }
  return [
    for (var i = 0; i < 27; i++)
      if (isNoSuji[i]) i,
  ];
}

// TODO(원본, 미정): 이른 바깥패의 반스지(이른 순에 8m 을 냈을 때 3m 의 반스지 6m).
// TODO(원본, 미정): 적도라로 방총률 계산.
// TODO(원본): 도라 주변 패의 위험도를 조금 올릴 것.

/// 원본 util/tile.go `OutsideTiles`: 그 패를 이른 순에 냈을 때 바깥쪽이 되는 패.
List<int> outsideTiles(int tile) {
  if (tile >= 27) return const [];
  final out = <int>[];
  switch (tile % 9 + 1) {
    case 1 || 9:
      return const [];
    case 2 || 3 || 4:
      for (var i = tile - tile % 9; i < tile; i++) {
        out.add(i);
      }
    case 5:
      // 이른 5 → 37 이 비교적 안전 (TODO(원본): 반스지 A 46 도)
      out.addAll([tile - 2, tile + 2]);
    case 6 || 7 || 8:
      for (var i = tile - tile % 9 + 8; i > tile; i--) {
        out.add(i);
      }
  }
  return out;
}

// ---------------------------------------------------------------------------
// core.go analysisTilesRisk 를 위한 입력
// ---------------------------------------------------------------------------

/// 남의 쯔모기리가 null(모름)일 때 텐파이율(울기 상대의 "마지막 울기 뒤 데다시 수")에 어떻게 넣나.
///
/// 원본은 모든 버림의 쯔모기리를 안다. 우리 패보는 남의 것이 대부분 null 이다.
/// 이 값은 울기 상대의 텐파이율에만 영향을 준다(멘젠 다마 = 버림 수, 리치 = 100 은 상관없음).
enum UnknownTsumogiri {
  /// 손에서 낸 것으로 센다(표의 오른쪽 열 — 텐파이율이 가장 높게 나온다). **기본값.**
  ///
  /// 이유: 수비 판단에서 텐파이율을 낮게 잡으면(아래 둘) 울기 상대가 합친 위험의 문턱(텐파이율 > 15%)을
  /// 넘지 못해 통째로 빠지기 쉽다(예: 1 울기 9 순 0 열 30.11% · 6 순 0 열 13.05%). 모르는 것은 위험한 쪽으로 둔다.
  tedashi,

  /// 쯔모기리로 센다(알려진 데다시만 셈 — 하한).
  tsumogiri,

  /// 마지막 울기 뒤에 모르는 버림이 하나라도 있으면 그 행의 0 열(운 그 순)을 쓴다(가장 낮음).
  firstColumn,
}

/// 버림 한 장(모든 자리, 실제 순서대로).
class RiskDiscard {
  final int seat;
  final int tile;

  /// true 쯔모기리 · false 손에서 냄 · null 모름. 내 버림은 보지 않는다.
  final bool? tsumogiri;

  /// 리치 선언패.
  final bool riichi;
  const RiskDiscard(this.seat, this.tile, {this.tsumogiri, this.riichi = false});
}

/// 울기 한 묶음.
class RiskMeld {
  final int seat;
  final MeldKind kind;

  /// 묶음의 패 전체(가져온 패 포함, 깡은 4 장).
  final List<int> tiles;

  /// 울었을 때까지 놓인 전체 버림 수(= [RiskContext.discards] 에서 이 울기 앞의 길이).
  /// 치 · 퐁 · 대명깡은 `discards[at - 1]` 을 가져간 것이다. 가깡은 **처음 퐁한 때**, 안깡은 깡한 때.
  final int at;

  /// 가깡으로 바꾼 때(같은 기준). 일발 끊김 판정에만 쓴다. 모르면 null(= 일발에 영향 없음으로 봄).
  final int? upgradedAt;

  /// 묶음에 적5 가 있나(원본 `ContainRedFive`, 울기 상대 타점의 도라 수에 +1).
  final bool red;

  const RiskMeld(this.seat, this.kind, this.tiles, {required this.at, this.upgradedAt, this.red = false});
}

/// 한 시점의 탁자(내 차례에 본 것).
class RiskContext {
  /// 나(0~3). 자리 번호는 차례 순서(0 → 1 → 2 → 3).
  final int selfSeat;
  final int dealer;

  /// 장풍 패(27 동 · 28 남 …).
  final int roundWindTile;

  /// 지금까지의 모든 버림(실제 순서). 울려 간 패도 그대로 둔다(원본 `globalDiscardTiles` 와 같음).
  final List<RiskDiscard> discards;
  final List<RiskMeld> melds;

  /// 도라 표시패(깡도라 포함).
  final List<int> doraIndicators;

  /// 내 닫힌 손패 34칸(뽑은 패 포함). [visible34] 를 주면 쓰지 않는다.
  final List<int>? hand34;

  /// 내 시점에서 보이는 패 34칸을 직접 줄 때. null 이면 `hand34 + 울려 가지 않은 버림 + 울기 묶음 + 도라 표시패` 로 센다
  /// (원본 `leftCounts` 를 갱신하는 방식과 같은 결과).
  final List<int>? visible34;

  /// 자리별 일발 상태를 직접 줄 때(null 칸은 사건에서 헤아림, [_deriveIppatsu]).
  final List<bool?>? ippatsu;
  final UnknownTsumogiri unknownTsumogiri;

  const RiskContext({
    required this.selfSeat,
    required this.dealer,
    this.roundWindTile = Tiles.east,
    required this.discards,
    this.melds = const [],
    this.doraIndicators = const [],
    this.hand34,
    this.visible34,
    this.ippatsu,
    this.unknownTsumogiri = UnknownTsumogiri.tedashi,
  });

  /// 자리의 자풍 패. 원본 `27 + (4 - dealer + i) % 4`.
  int windTileOf(int seat) => Tiles.east + (seat - dealer) % 4;

  List<int> get doraTiles => [for (final i in doraIndicators) Tiles.doraFromIndicator(i)];

  /// 아직 안 보인 장수(원본 `leftCounts`). 음수는 0 으로 자른다(원본은 "데이터 이상" 을 찍고 음수 그대로 진행해 자패에서 터진다).
  List<int> get left34 {
    final visible = visible34 ?? _countVisible();
    return [for (var t = 0; t < 34; t++) (4 - visible[t]).clamp(0, 4)];
  }

  List<int> _countVisible() {
    final v = List<int>.filled(34, 0);
    final h = hand34;
    if (h != null) {
      for (var t = 0; t < 34; t++) {
        v[t] += h[t];
      }
    }
    final called = <int>{
      for (final m in melds)
        if (m.kind != MeldKind.ankan && m.at >= 1) m.at - 1,
    };
    for (final (g, d) in discards.indexed) {
      if (!called.contains(g)) v[d.tile]++;
    }
    for (final m in melds) {
      for (final t in m.tiles) {
        v[t]++;
      }
    }
    for (final t in doraIndicators) {
      v[t]++;
    }
    return v;
  }
}

// ---------------------------------------------------------------------------
// 결과
// ---------------------------------------------------------------------------

/// 상대 한 명에 대한 결과(원본 `riskInfo`).
class OpponentRisk {
  final int seat;

  /// 리치면 100, 아니면 [calcTenpaiRate].
  final double tenpaiRate;

  /// 그 상대의 안전패(현물 · 리치 뒤 모두의 버림 또는 동순 후리텐 · 깡한 패).
  final List<bool> safe34;

  /// 34칸 방총 위험(%) — 이 상대가 텐파이라고 칠 때.
  final List<double> risk34;

  /// 순목(1~19).
  final int turns;
  final double ronPoint;
  final bool riichi;
  final bool ippatsu;

  /// 리치 선언패가 쯔모기리였나. 모르면 null. (원본 `isTsumogiriRiichi`, 표시용)
  final bool? tsumogiriRiichi;

  /// 남은 무스지 123789. 울기 4 개(대명 단기)면 원본도 계산하지 않아 빈 목록.
  final List<int> leftNoSujiTiles;

  /// 이른 바깥패(×0.4 를 받은 패, 겹친 만큼 들어 있음).
  final List<int> earlyOutsideTiles;

  const OpponentRisk({
    required this.seat,
    required this.tenpaiRate,
    required this.safe34,
    required this.risk34,
    required this.turns,
    required this.ronPoint,
    required this.riichi,
    required this.ippatsu,
    required this.tsumogiriRiichi,
    required this.leftNoSujiTiles,
    required this.earlyOutsideTiles,
  });
}

class RiskTable {
  /// 자리별 결과. 내 자리는 null.
  final List<OpponentRisk?> bySeat;

  /// 텐파이율을 반영해 합친 34칸 위험(%) — 원본 `mixedRiskTable`.
  final List<double> mixed34;

  /// 모든 상대에게 안전패(각자의 [OpponentRisk.safe34] 가 모두 true).
  final List<bool> safeForAll34;

  /// 벽 노찬스 · 더블 노찬스(현물 반영 없이 벽만 — 원본 cli 표시와 같은 것).
  final List<WallSafeTile> noChance;
  final List<WallSafeTile> doubleNoChance;

  final List<int> left34;

  const RiskTable({
    required this.bySeat,
    required this.mixed34,
    required this.safeForAll34,
    required this.noChance,
    required this.doubleNoChance,
    required this.left34,
  });

  Iterable<OpponentRisk> get opponents => bySeat.whereType<OpponentRisk>();
}

// ---------------------------------------------------------------------------
// core.go analysisTilesRisk · cli.go mixedRiskTable
// ---------------------------------------------------------------------------

/// 원본 core.go 의 `playerInfo` 중 위험도에 쓰는 것. 버림 사건을 차례로 넣어 원본과 같은 식으로 쌓는다.
class _PlayerState {
  final List<int> discardTiles = []; // 쯔모기리는 ~패
  final List<bool?> tsumogiriKnown = [];
  int latestDiscardAtGlobal = -1;
  final List<int> earlyOutsideTiles = [];
  bool isReached = false;
  int reachTileAtGlobal = -1;
  int reachTileAt = -1;
  final List<int> meldDiscardsAt = [];
}

/// 일발: 리치 선언패가 그 사람의 마지막 버림이고, 선언 뒤 누구의 울기(안깡 · 가깡 포함)도 없을 때.
/// 원본은 사건마다 `canIppatsu` 를 켜고 끈다(core.go:593-596, 699-701, 780-783, 847-850). 북 빼기는 4 인이라 뺐다.
bool _deriveIppatsu(_PlayerState p, List<RiskMeld> melds) {
  if (!p.isReached || p.reachTileAtGlobal < 0) return false;
  if (p.reachTileAt < p.discardTiles.length - 1) return false;
  for (final m in melds) {
    if (m.at > p.reachTileAtGlobal) return false;
    final u = m.upgradedAt;
    if (u != null && u > p.reachTileAtGlobal) return false;
  }
  return true;
}

/// 원본 `playerInfo.doraNum` (북 빼기 제외).
int _doraNum(List<RiskMeld> melds, List<int> doraList) {
  var c = 0;
  for (final m in melds) {
    for (final t in m.tiles) {
      for (final d in doraList) {
        if (t == d) c++;
      }
    }
    if (m.red) c++;
  }
  return c;
}

/// 상대마다 34칸 위험 · 텐파이율, 그리고 합친 위험.
RiskTable riskOf(RiskContext ctx) {
  final left = ctx.left34;
  final doraList = ctx.doraTiles;

  // 버림 사건을 원본 core.go:815-850 순서대로 넣는다.
  final players = [for (var s = 0; s < 4; s++) _PlayerState()];
  final global = <int>[]; // 원본 globalDiscardTiles (남의 쯔모기리는 ~패)
  for (final (g, d) in ctx.discards.indexed) {
    final p = players[d.seat];
    if (d.riichi) p.isReached = true;
    final isSelf = d.seat == ctx.selfSeat;
    final enc = !isSelf && _countAsTsumogiri(d.tsumogiri, ctx.unknownTsumogiri) ? ~d.tile : d.tile;
    global.add(enc);
    p.discardTiles.add(enc);
    p.tsumogiriKnown.add(isSelf ? false : d.tsumogiri);
    p.latestDiscardAtGlobal = g;
    if (isSelf) continue; // 원본은 내 버림에서 아래를 하지 않는다(core.go:785-813).

    // 바깥패 표시
    if (!p.isReached && p.discardTiles.length <= 5) {
      p.earlyOutsideTiles.addAll(outsideTiles(d.tile));
    }
    final meldsSoFar = ctx.melds.where((m) => m.seat == d.seat && m.at <= g).length;
    if (p.isReached && p.reachTileAtGlobal == -1) {
      // 리치 선언패 표시
      p.reachTileAtGlobal = g;
      p.reachTileAt = p.discardTiles.length - 1;
    } else if (p.meldDiscardsAt.length != meldsSoFar) {
      // 울기 뒤 버림 표시. 원본 주석: 안깡 뒤 버림에도 붙고, 깡을 이어 하면 길이가 울기 수와 다를 수 있다.
      p.meldDiscardsAt.add(p.discardTiles.length - 1);
    }
  }

  int norm(int t) => t < 0 ? ~t : t;

  final bySeat = List<OpponentRisk?>.filled(4, null);
  // 원본은 자리를 상대적(0 나 · 1 하가 · 2 대면 · 3 상가)으로 돈다. 합칠 때 순서도 그대로.
  for (var rel = 1; rel < 4; rel++) {
    final seat = (ctx.selfSeat + rel) % 4;
    final p = players[seat];
    final myMelds = [for (final m in ctx.melds) if (m.seat == seat) m];

    // 안전패: 그 사람의 버림 → 리치 뒤 모두의 버림 / (리치 아니면) 그 사람 마지막 버림 뒤 모두의 버림 → 깡한 패.
    final safe = List<bool>.filled(34, false);
    for (final t in p.discardTiles) {
      safe[norm(t)] = true;
    }
    if (p.reachTileAtGlobal != -1) {
      for (final t in global.sublist(p.reachTileAtGlobal)) {
        safe[norm(t)] = true;
      }
    } else if (p.latestDiscardAtGlobal != -1) {
      for (final t in global.sublist(p.latestDiscardAtGlobal)) {
        safe[norm(t)] = true;
      }
    }
    // 678888 에서 깡하는 사람은 상상하기 어렵다(원본 주석 — 그런 경우는 막지 않음).
    for (final m in myMelds) {
      if (m.kind.isKan) safe[m.tiles.first] = true;
    }

    // 순목 = 그 사람이 버린 수
    var turns = p.discardTiles.length < maxRiskTurns ? p.discardTiles.length : maxRiskTurns;
    if (turns == 0) turns = 1;

    // TODO(원본): 계속 쯔모기리하다가 갑자기 자패를 손에서 내면 다마 / 1 향청일 가능성이 크다.
    final double tenpai;
    bool? tsumogiriRiichi;
    if (p.isReached) {
      tenpai = 100.0;
      if (p.reachTileAtGlobal >= 0) tsumogiriRiichi = p.tsumogiriKnown[p.reachTileAt];
    } else {
      var discards = p.discardTiles;
      if (ctx.unknownTsumogiri == UnknownTsumogiri.firstColumn && p.meldDiscardsAt.isNotEmpty) {
        final from = p.meldDiscardsAt.last + 1;
        final anyUnknown = from < p.tsumogiriKnown.length && p.tsumogiriKnown.sublist(from).any((k) => k == null);
        if (anyUnknown) discards = [for (final t in discards) t >= 0 ? ~t : t];
      }
      tenpai = calcTenpaiRate([for (final m in myMelds) m.kind], discards, p.meldDiscardsAt);
    }

    final isNaki = myMelds.any((m) => m.kind != MeldKind.ankan);
    final ippatsu = ctx.ippatsu?[seat] ?? _deriveIppatsu(p, ctx.melds);
    double ronPoint;
    if (ippatsu) {
      ronPoint = ronPointRiichiIppatsu;
    } else if (p.isReached) {
      ronPoint = ronPointRiichiHiIppatsu;
    } else if (isNaki) {
      // 울기 타점(아주 거칠게)
      ronPoint = ronPointOtherNakiWithDora(_doraNum(myMelds, doraList));
    } else {
      ronPoint = ronPointDama;
    }
    if (seat == ctx.dealer) ronPoint *= 1.5; // 친 ×1.5

    var risk34 = calculateRiskTiles34(turns, safe, left, doraList, ctx.roundWindTile, ctx.windTileOf(seat));
    risk34 = fixWithEarlyOutside(risk34, p.earlyOutsideTiles);
    risk34 = fixWithPoint(risk34, ronPoint);

    bySeat[seat] = OpponentRisk(
      seat: seat,
      tenpaiRate: tenpai,
      safe34: safe,
      risk34: risk34,
      turns: turns,
      ronPoint: ronPoint,
      riichi: p.isReached,
      ippatsu: ippatsu,
      tsumogiriRiichi: tsumogiriRiichi,
      // 울기 4 개면 대명 단기: 원본도 계산하지 않음.
      leftNoSujiTiles: myMelds.length < 4 ? calculateLeftNoSujiTiles(safe, left) : const [],
      earlyOutsideTiles: List.unmodifiable(p.earlyOutsideTiles),
    );
  }

  final opps = [for (var rel = 1; rel < 4; rel++) bySeat[(ctx.selfSeat + rel) % 4]!];
  return RiskTable(
    bySeat: bySeat,
    mixed34: mixedRisk34(opps),
    safeForAll34: [for (var t = 0; t < 34; t++) opps.every((o) => o.safe34[t])],
    noChance: calcNCSafeTiles(left),
    doubleNoChance: calcDNCSafeTiles(left),
    left34: left,
  );
}

bool _countAsTsumogiri(bool? known, UnknownTsumogiri policy) => known ?? (policy != UnknownTsumogiri.tedashi);

/// 원본 cli.go `mixedRiskTable`: 텐파이율 > 15% 인 상대만, x = risk · tenpai / 100, r = r + x − r·x/100.
List<double> mixedRisk34(List<OpponentRisk> opponents) {
  final out = List<double>.filled(34, 0);
  for (var i = 0; i < 34; i++) {
    var mixed = 0.0;
    for (final o in opponents) {
      if (o.tenpaiRate <= 15) continue;
      final r = o.risk34[i] * o.tenpaiRate / 100;
      mixed = mixed + r - mixed * r / 100;
    }
    out[i] = mixed;
  }
  return out;
}
