// Ported from EndlessCheng/mahjong-helper (MIT)
//   util/agari_rate.go, util/agari_rate_data.go,
//   util/risk_base.go(calcTileType27 만 → agariTileType27), util/risk_data.go(tileType·TileTypeTable 만)
// Copyright (c) 2018 Σndless
// 원본 LICENSE 전문: third_party/mahjong-helper/LICENSE
//
// 텐파이 대기의 화료율(%). 자기 버림으로 스지 종류를 정하고, 표(6~10순 통계)
// · 도라 배율 · 스지 양면 ×0.91 · 후리텐(장당 5.9%) 을 합성한다.
// 위험도(risk_*)는 다른 이식이 맡으므로 여기엔 화료율에 필요한 스지 종류만 둔다.

import 'mh_player.dart';

/// 원본 `tileType`(util/risk_data.go) 가운데 수패 13 가지. 순서는 원본 iota 와 같다.
enum AgariTileType {
  noSuji5,
  noSuji46,
  noSuji37,
  noSuji28,
  noSuji19,
  halfSuji5,
  halfSuji46A, // 현물이 1·9 쪽
  halfSuji46B, // 현물이 7·3 쪽
  suji37,
  suji28,
  suji19,
  doubleSuji5,
  doubleSuji46,
}

// ---- agari_rate_data.go ----

/// 참고:「統計学」のマージャン戦術 & 知るだけで強くなる麻雀の2択
const double furitenBaseAgariRate = 5.9;
const double honorDoraAgariMulti = 35.0 / 48.0;
const double numberDoraAgariMulti = 26.0 / 38.0;
const double ryanmenAgariMulti = 0.91;

// 원본 TODO(그대로): 순목 기반 화료율 / 패산 읽기 / 早外·NC·다른 장황 (issue #46)

/// 수패 화료율. 6~10순 [종류][남은 장수 0~4].
/// 참고: 勝つための現代麻雀技術論
/// (suji19 의 남은 4장이 0 인 것도 원본 그대로.)
const Map<AgariTileType, List<double>> agariMap = {
  AgariTileType.noSuji19: [0, 26.3, 41.6, 50.1, 54.0],
  AgariTileType.noSuji28: [0, 19.2, 31.7, 38.2, 42.0],
  AgariTileType.noSuji37: [0, 14.8, 25.5, 32.0, 36.8],
  AgariTileType.noSuji46: [0, 11.8, 20.3, 26.7, 31.0],
  AgariTileType.noSuji5: [0, 11.8, 20.3, 26.7, 31.0],
  AgariTileType.suji19: [0, 36.1, 60.0, 67.9, 0],
  AgariTileType.suji28: [0, 24.9, 42.7, 51.2, 56.5],
  AgariTileType.suji37: [0, 17.2, 33.1, 43.5, 48.9],
  AgariTileType.doubleSuji46: [0, 16.5, 35.5, 45.4, 50.0],
  AgariTileType.doubleSuji5: [0, 16.5, 35.5, 45.4, 50.0],
  AgariTileType.halfSuji46A: [0, 12.9, 24.7, 30.9, 35.4],
  AgariTileType.halfSuji46B: [0, 12.9, 24.7, 30.9, 35.4],
  AgariTileType.halfSuji5: [0, 12.9, 24.7, 30.9, 35.4],
};

/// 자패 단기 아닌 대기(샤보) [남은 장수]. 6~10순. 참고: 勝つための現代麻雀技術論
const List<double> honorTileNonDankiAgariTable = [0, 34.0, 52.0];

/// 자패 단기 [남은 장수]. 8순. 참고:「統計学」のマージャン戦術
const List<double> honorTileDankiAgariTable = [0, 47.5, 58.0, 49.5];

// ---- risk_data.go: TileTypeTable ----

/// [수패 숫자 0~8][대응 현물 유무(0~1, 4·5·6 은 0~3)]
const List<List<AgariTileType>> _tileTypeTable = [
  [AgariTileType.noSuji19, AgariTileType.suji19],
  [AgariTileType.noSuji28, AgariTileType.suji28],
  [AgariTileType.noSuji37, AgariTileType.suji37],
  [AgariTileType.noSuji46, AgariTileType.halfSuji46B, AgariTileType.halfSuji46A, AgariTileType.doubleSuji46],
  [AgariTileType.noSuji5, AgariTileType.halfSuji5, AgariTileType.halfSuji5, AgariTileType.doubleSuji5],
  [AgariTileType.noSuji46, AgariTileType.halfSuji46A, AgariTileType.halfSuji46B, AgariTileType.doubleSuji46],
  [AgariTileType.noSuji37, AgariTileType.suji37],
  [AgariTileType.noSuji28, AgariTileType.suji28],
  [AgariTileType.noSuji19, AgariTileType.suji19],
];

/// 원본 `calcTileType27`: 자기 버림으로 만·통·삭 27 칸의 스지 종류.
List<AgariTileType> agariTileType27(List<int> discardTiles) {
  final safe = List<int>.filled(34, 0);
  for (final t in discardTiles) {
    safe[t] = 1;
  }
  final out = List<AgariTileType>.filled(27, AgariTileType.noSuji5);
  for (var i = 0; i < 3; i++) {
    for (var j = 0; j < 3; j++) {
      final idx = 9 * i + j;
      out[idx] = _tileTypeTable[j][safe[idx + 3]];
    }
    for (var j = 3; j < 6; j++) {
      final idx = 9 * i + j;
      final mix = safe[idx - 3] << 1 | safe[idx + 3];
      out[idx] = _tileTypeTable[j][mix];
    }
    for (var j = 6; j < 9; j++) {
      final idx = 9 * i + j;
      out[idx] = _tileTypeTable[j][safe[idx - 3]];
    }
  }
  return out;
}

double _tableAt(List<double> table, int left) =>
    // 원본은 범위를 넘으면 Go 런타임 패닉이다. 국사를 빼면 닿지 않는다.
    left >= 0 && left < table.length ? table[left] : 0.0;

/// 원본 `CalculateAgariRateOfEachTile`: 대기패마다 화료율(%). 남은 0 이면 0.
Map<int, double> agariRateOfEachTile(
    MhWaits waits, List<int> discardTiles, List<int> doraTiles) {
  final out = <int, double>{};

  // 후리텐이면 장수에만 기댄다.
  if (_isFuriten(waits, discardTiles)) {
    for (final e in waits.entries) {
      var rate = 0.0;
      for (var i = 0; i < e.value; i++) {
        rate = rate + furitenBaseAgariRate - rate * furitenBaseAgariRate / 100;
      }
      out[e.key] = rate;
    }
    return out;
  }

  // 자패 단기.
  if (waits.length == 1) {
    final e = waits.entries.first;
    if (e.key >= 27) {
      var rate = _tableAt(honorTileDankiAgariTable, e.value);
      if (doraTiles.contains(e.key)) {
        // 도라 대기 보정(도라 겹침 영향은 무시, 원본 주석)
        rate *= honorDoraAgariMulti;
      }
      out[e.key] = rate;
      return out;
    }
  }

  final type27 = agariTileType27(discardTiles);
  for (final e in waits.entries) {
    final tile = e.key;
    double rate;
    if (tile < 27) {
      rate = _tableAt(agariMap[type27[tile]]!, e.value);
    } else {
      rate = _tableAt(honorTileNonDankiAgariTable, e.value);
    }
    if (doraTiles.contains(tile)) {
      rate *= tile >= 27 ? honorDoraAgariMulti : numberDoraAgariMulti;
    }
    out[tile] = rate;
  }
  return out;
}

/// 원본 `CalculateAvgAgariRate`: 대기 전체 화료율(%).
double avgAgariRate(MhWaits waits,
    {List<int> discardTiles = const [], List<int> doraTiles = const []}) {
  if (_isFuriten(waits, discardTiles)) {
    var rate = 0.0;
    final n = waits.allCount;
    for (var i = 0; i < n; i++) {
      rate = rate + furitenBaseAgariRate - rate * furitenBaseAgariRate / 100;
    }
    return rate;
  }

  final each = agariRateOfEachTile(waits, discardTiles, doraTiles);
  var agariRate = 0.0;
  for (final rate in each.values) {
    agariRate = agariRate + rate - agariRate * rate / 100;
  }

  // 양면 보정: 남은 대기가 같은 수트에서 정확히 스지 관계(2장 또는 3장)일 때.
  final waitTiles = <int>[];
  for (final e in waits.entries) {
    if (e.value > 0) {
      if (e.key >= 27) return agariRate;
      waitTiles.add(e.key);
    }
  }
  if (waitTiles.length > 1) {
    final suit = waitTiles[0] ~/ 9;
    for (final t in waitTiles.skip(1)) {
      if (t ~/ 9 != suit) return agariRate;
    }
    waitTiles.sort();
    if (waitTiles.length == 2 && waitTiles[0] + 3 == waitTiles[1] ||
        waitTiles.length == 3 &&
            waitTiles[0] + 3 == waitTiles[1] &&
            waitTiles[1] + 3 == waitTiles[2]) {
      agariRate *= ryanmenAgariMulti;
    }
  }
  return agariRate;
}

bool _isFuriten(MhWaits waits, List<int> discardTiles) {
  for (final d in discardTiles) {
    if (waits.containsKey(d)) return true;
  }
  return false;
}
