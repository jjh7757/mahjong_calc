import 'hand.dart';
import 'meld.dart';
import 'tile.dart';

enum SetType { sequence, triplet, kan, pair }

/// 분해된 한 묶음. 순자는 [tile] 이 가장 낮은 패.
class TileSet {
  final SetType type;
  final int tile;

  /// 남의 패로 부른 묶음(치·펑·대명깡·가깡).
  final bool isCalled;

  /// 안깡.
  final bool isClosedKan;

  const TileSet(this.type, this.tile,
      {this.isCalled = false, this.isClosedKan = false});

  bool get isSequence => type == SetType.sequence;
  bool get isTriplet => type == SetType.triplet || type == SetType.kan;
  bool get isKan => type == SetType.kan;
  bool get isPair => type == SetType.pair;

  List<int> get tiles => isSequence
      ? [tile, tile + 1, tile + 2]
      : List.filled(isPair ? 2 : (isKan ? 4 : 3), tile);

  bool contains(int t) => tiles.contains(t);

  @override
  String toString() {
    final body = tiles.map(Tiles.toCode).join('');
    if (isCalled) return '[$body]';
    if (isClosedKan) return '($body)';
    return body;
  }
}

enum HandShape { standard, chiitoitsu, kokushi }

enum WaitType { ryanmen, kanchan, penchan, shanpon, tanki }

/// 한 가지 분해 + 화료패 위치.
class Decomposition {
  final HandShape shape;

  /// 표준형이면 5개(4묶음 + 머리). 치또이는 7개 머리. 국사는 비어 있음.
  final List<TileSet> sets;

  /// 화료패가 들어 있는 묶음의 인덱스. 국사는 -1.
  final int winSetIndex;
  final WaitType wait;

  const Decomposition(this.shape, this.sets, this.winSetIndex, this.wait);

  TileSet? get winSet => winSetIndex >= 0 ? sets[winSetIndex] : null;
  TileSet get pair => sets.firstWhere((s) => s.isPair);

  @override
  String toString() => '$shape ${sets.join(' ')} wait=$wait@$winSetIndex';
}

/// 손패를 가능한 모든 방식으로 분해한다. 화료패 위치까지 구분한다.
List<Decomposition> decompose(Hand hand) {
  final results = <Decomposition>[];
  final counts = hand.closedCounts;
  final called = hand.melds.map(_fromMeld).toList();
  final needSets = 4 - hand.melds.length;

  for (final closedSets in _splitStandard(counts, needSets)) {
    final sets = [...closedSets, ...called];
    for (var i = 0; i < closedSets.length; i++) {
      final s = closedSets[i];
      if (!s.contains(hand.winTile)) continue;
      results.add(
          Decomposition(HandShape.standard, sets, i, _waitOf(s, hand.winTile)));
    }
  }

  if (hand.melds.isEmpty) {
    final seven = _chiitoitsu(counts);
    if (seven != null) {
      final idx = seven.indexWhere((s) => s.tile == hand.winTile);
      results
          .add(Decomposition(HandShape.chiitoitsu, seven, idx, WaitType.tanki));
    }
    if (_isKokushi(counts)) {
      results
          .add(const Decomposition(HandShape.kokushi, [], -1, WaitType.tanki));
    }
  }
  return results;
}

TileSet _fromMeld(Meld m) {
  switch (m.type) {
    case MeldType.chi:
      return TileSet(SetType.sequence, m.first, isCalled: true);
    case MeldType.pon:
      return TileSet(SetType.triplet, m.first, isCalled: true);
    case MeldType.kan:
      return TileSet(SetType.kan, m.first,
          isCalled: m.isOpen, isClosedKan: !m.isOpen);
  }
}

WaitType _waitOf(TileSet s, int win) {
  if (s.isPair) return WaitType.tanki;
  if (s.isTriplet) return WaitType.shanpon;
  final n = Tiles.number(s.tile);
  if (win == s.tile + 1) return WaitType.kanchan;
  if (win == s.tile) return n == 7 ? WaitType.penchan : WaitType.ryanmen;
  return n == 1 ? WaitType.penchan : WaitType.ryanmen;
}

/// 4묶음+머리 분해 전부. [needSets] 는 손패에서 찾을 묶음 수.
Iterable<List<TileSet>> _splitStandard(List<int> counts, int needSets) sync* {
  for (var p = 0; p < Tiles.count; p++) {
    if (counts[p] < 2) continue;
    final c = [...counts];
    c[p] -= 2;
    for (final sets in _splitSets(c, 0, needSets)) {
      yield [TileSet(SetType.pair, p), ...sets];
    }
  }
}

Iterable<List<TileSet>> _splitSets(List<int> c, int from, int remain) sync* {
  var i = from;
  while (i < Tiles.count && c[i] == 0) {
    i++;
  }
  if (i == Tiles.count) {
    if (remain == 0) yield const [];
    return;
  }
  if (remain == 0) return;

  if (c[i] >= 3) {
    c[i] -= 3;
    for (final rest in _splitSets(c, i, remain - 1)) {
      yield [TileSet(SetType.triplet, i), ...rest];
    }
    c[i] += 3;
  }
  if (i < 27 && Tiles.number(i) <= 7 && c[i + 1] > 0 && c[i + 2] > 0) {
    c[i]--;
    c[i + 1]--;
    c[i + 2]--;
    for (final rest in _splitSets(c, i, remain - 1)) {
      yield [TileSet(SetType.sequence, i), ...rest];
    }
    c[i]++;
    c[i + 1]++;
    c[i + 2]++;
  }
}

List<TileSet>? _chiitoitsu(List<int> counts) {
  final pairs = <TileSet>[];
  for (var t = 0; t < Tiles.count; t++) {
    if (counts[t] == 0) continue;
    if (counts[t] != 2) return null;
    pairs.add(TileSet(SetType.pair, t));
  }
  return pairs.length == 7 ? pairs : null;
}

const kokushiTiles = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];

bool _isKokushi(List<int> counts) {
  var pairFound = false;
  for (var t = 0; t < Tiles.count; t++) {
    final isYaochu = kokushiTiles.contains(t);
    if (!isYaochu) {
      if (counts[t] != 0) return false;
      continue;
    }
    if (counts[t] == 0) return false;
    if (counts[t] == 2) {
      if (pairFound) return false;
      pairFound = true;
    } else if (counts[t] != 1) {
      return false;
    }
  }
  return pairFound;
}
