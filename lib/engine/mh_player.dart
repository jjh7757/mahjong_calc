// Ported from EndlessCheng/mahjong-helper (MIT)
//   util/model/player_info.go, util/model/tile.go, util/tile.go(MhWaits·패 도우미),
//   util/util.go(InDelta·Equal)
// Copyright (c) 2018 Σndless
// 원본 LICENSE 전문: third_party/mahjong-helper/LICENSE
//
// 버림 평가 이식(improve.dart · agari_rate.dart · hand_value.dart ·
// discard_rank.dart)이 함께 쓰는 바탕. 원본의 MhPlayerInfo 는 탐색 중에 손패·
// 남은 패·자기 버림을 제자리에서 바꿨다가 되돌린다. 여기서도 같은 방식이다.

import 'dart:collection';

import 'calculator.dart';
import 'shanten.dart';

/// 원본 `Waits`(map[패]남은 장수). 남은 장수 0 인 패도 키로 남는다
/// (후리텐 판정에 종류가 필요해서, 원본 주석 그대로).
///
/// 원본은 Go map 이라 순회 순서가 매번 다르다. 여기서는 넣은 순서(탐색이
/// 0→33 으로 넣으므로 패 번호 오름차순)를 지킨다.
class MhWaits {
  final LinkedHashMap<int, int> _m = LinkedHashMap<int, int>();

  MhWaits();

  MhWaits.from(Map<int, int> m) {
    final keys = m.keys.toList()..sort();
    for (final k in keys) {
      _m[k] = m[k]!;
    }
  }

  int? operator [](int tile) => _m[tile];
  void operator []=(int tile, int left) => _m[tile] = left;
  bool containsKey(int tile) => _m.containsKey(tile);
  int get length => _m.length;
  bool get isEmpty => _m.isEmpty;
  Iterable<int> get tiles => _m.keys;
  Iterable<MapEntry<int, int>> get entries => _m.entries;

  /// 원본 `AllCount`.
  int get allCount {
    var c = 0;
    for (final v in _m.values) {
      c += v;
    }
    return c;
  }

  /// 원본 `AvailableTiles`: 남은 장수가 1 이상인 패, 오름차순.
  List<int> get availableTiles =>
      [for (final e in _m.entries) if (e.value > 0) e.key]..sort();

  Map<int, int> toMap() => Map<int, int>.of(_m);

  @override
  String toString() =>
      '$allCount [${(_m.keys.toList()..sort()).map(Tiles.toCode).join(' ')}]';
}

/// 원본 `InDelta`.
bool mhInDelta(double a, double b, double delta) => (a - b).abs() < delta;

/// 원본 `Equal`(eps 1e-5). NaN 이 끼면 false — 원본 Go 와 같다.
bool mhEqual(double a, double b) => mhInDelta(a, b, 1e-5);

/// 원본 `isYaochupai`.
bool mhIsYaochupai(int tile) {
  if (tile >= 27) return true;
  final t = tile % 9;
  return t == 0 || t == 8;
}

/// 원본 `isIsolatedTile`: [tiles34](13장) 에 [tile] 을 놓으면 고립패인지.
bool mhIsIsolatedTile(int tile, List<int> tiles34) {
  if (tile >= 27) return tiles34[tile] == 0;
  final t = tile % 9;
  final l = tile - t + (t - 2 > 0 ? t - 2 : 0);
  final r = tile - t + (t + 2 < 8 ? t + 2 : 8);
  for (var i = l; i <= r; i++) {
    if (tiles34[i] > 0) return false;
  }
  return true;
}

int mhCountTiles34(List<int> tiles34) {
  var c = 0;
  for (final x in tiles34) {
    c += x;
  }
  return c;
}

/// 원본 `CountPairsOfTiles34`.
int mhCountPairs34(List<int> tiles34) {
  var c = 0;
  for (final x in tiles34) {
    if (x >= 2) c++;
  }
  return c;
}

/// 원본 `CalculateShanten`(국사 빼고, 13장 이상일 때만 치또이).
///
/// 원본은 자기 일반형 알고리즘(shanten_base.go)을 쓰지만 여기서는 우리
/// [shantenOf] 의 일반형·치또이를 쓴다. 울기 수는 장수에서 거꾸로 셈한다
/// (원본도 `numberMelds = (14 − 장수) / 3`).
int mhShanten(List<int> tiles34) {
  final n = mhCountTiles34(tiles34);
  final melds = (14 - n) ~/ 3;
  final s = shantenOf(tiles34, melds: melds);
  final c = s.chiitoitsu;
  if (n >= 13 && c != null && c < s.standard) return c;
  return s.standard;
}

/// 원본 `IsAgari`(국사 빼고). 3k+2 장.
bool mhIsAgari(List<int> tiles34) => mhShanten(tiles34) == -1;

/// 원본 `model.DoraTile`(사마 아님).
int doraTileOf(int indicator) => Tiles.doraFromIndicator(indicator);

/// 원본 `model.PlayerInfo` 가운데 버림 평가에 쓰는 것.
///
/// 원본 규칙 가정(그대로 옮김):
/// - 적5 는 손패·울기 안의 수만큼 도라 1 씩(`CountDora` 가 `NumRedFives` 를 더함).
/// - 친 여부([isParent])와 자풍([selfWindTile])은 따로 받는다. 우리 계산기는
///   자풍 = 동 이면 친으로 보므로, 점수는 기본점에서 원본 식으로 다시 낸다
///   (hand_value.dart `_pointOf`).
class MhPlayerInfo {
  /// 닫힌 손패 34칸(울기 제외). 탐색 중 제자리에서 바뀐다.
  final List<int> handTiles34;
  final List<Meld> melds;

  /// 도라 표시패가 가리키는 실제 도라(겹치면 여러 번).
  final List<int> doraTiles;

  /// 우리 계산기에 넘길 도라 표시패. [doraTiles] 와 같은 순서.
  final List<int> doraIndicators;

  /// 만·통·삭 적5 개수(손패 + 울기).
  final List<int> numRedFives;

  final int roundWindTile;
  final int selfWindTile;
  final bool isParent;

  /// 자기 버림. 후리텐·스지 종류에 쓴다. 탐색 중 버린 패가 뒤에 붙었다 빠진다.
  final List<int> discardTiles;

  /// 남은 패(4 − 손패 − 보이는 패). 탐색 중 제자리에서 바뀐다.
  final List<int> leftTiles34;

  /// 남은 쯔모 수(원본 `LeftDrawTilesCount`, 출력용).
  final int leftDrawTilesCount;

  /// 이미 리치했는지(원본 `IsRiichi`). 버림 평가에서는 보통 false.
  final bool isRiichi;

  /// 점수 계산 캐시(같은 손·화료패·쯔모 여부·리치 여부·적5 수).
  final Map<String, ScoreResult> pointCache = {};

  MhPlayerInfo({
    required this.handTiles34,
    this.melds = const [],
    List<int> doraIndicators = const [],
    List<int>? numRedFives,
    this.roundWindTile = Tiles.east,
    this.selfWindTile = Tiles.east,
    this.isParent = false,
    List<int>? discardTiles,
    required this.leftTiles34,
    this.leftDrawTilesCount = 0,
    this.isRiichi = false,
  })  : doraIndicators = List.of(doraIndicators),
        doraTiles = [for (final i in doraIndicators) doraTileOf(i)],
        numRedFives = numRedFives == null ? [0, 0, 0] : List.of(numRedFives),
        discardTiles = discardTiles == null ? [] : List.of(discardTiles);

  /// 원본 `IsNaki`(안깡은 울기 아님).
  bool get isNaki => melds.any((m) => m.isOpen);

  /// 원본 `IsFuriten`: 자기 버림에 대기패가 있으면.
  bool isFuriten(MhWaits waits) {
    for (final d in discardTiles) {
      if (waits.containsKey(d)) return true;
    }
    return false;
  }

  /// 원본 `CountDora`(뽑기 도라 없음).
  int countDora() {
    var count = 0;
    for (final d in doraTiles) {
      count += handTiles34[d];
      for (final m in melds) {
        for (final t in m.tiles) {
          if (t == d) count++;
        }
      }
    }
    for (final n in numRedFives) {
      count += n;
    }
    return count;
  }

  int get redFiveTotal => numRedFives[0] + numRedFives[1] + numRedFives[2];

  /// 원본 `IsOnlyRedFive`: 손에 든 그 5 가 전부 적5 인지.
  /// (원본 그대로 `NumRedFives` 에 울기 안의 적5 도 들어 있는 채로 비교한다.)
  bool isOnlyRedFive(int tile) =>
      tile < 27 &&
      tile % 9 == 4 &&
      handTiles34[tile] > 0 &&
      handTiles34[tile] == numRedFives[tile ~/ 9];

  /// 원본 `DiscardTile`.
  void discardTile(int tile, bool isRedFive) {
    handTiles34[tile]--;
    if (isRedFive) numRedFives[tile ~/ 9]--;
    discardTiles.add(tile);
  }

  /// 원본 `UndoDiscardTile`.
  void undoDiscardTile(int tile, bool isRedFive) {
    discardTiles.removeLast();
    handTiles34[tile]++;
    if (isRedFive) numRedFives[tile ~/ 9]++;
  }
}
