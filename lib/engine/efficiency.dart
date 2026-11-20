import 'shanten.dart';
import 'tile.dart';

/// 유효패 한 종류와 남은 장수.
class UkeireTile {
  final int tile;

  /// 남은 장수 = max(0, 4 − 손에 든 수 − 보이는 수).
  final int left;

  const UkeireTile(this.tile, this.left);

  @override
  String toString() => '${Tiles.toCode(tile)}×$left';
}

/// 13 − 3 × 울기 수 장 손패의 유효패.
class Ukeire {
  /// 뽑기 전 샹텐.
  final int shanten;

  /// 샹텐을 1 줄이는 패 전부(패 번호 오름차순). 남은 장수 0 인 것도 넣는다.
  final List<UkeireTile> tiles;

  const Ukeire(this.shanten, this.tiles);

  /// 남은 장수 합.
  int get total => tiles.fold(0, (s, u) => s + u.left);

  /// 남은 장수가 1장 이상인 종류 수.
  int get liveKinds => tiles.where((u) => u.left > 0).length;

  @override
  String toString() => 'Ukeire(샹텐 $shanten, $total장: ${tiles.join(' ')})';
}

/// [counts] 는 34칸 닫힌 손패 개수, `13 − 3 × melds` 장.
///
/// [visible] 은 내 닫힌 손패 밖에 보이는 패 34칸 개수(네 자리 강, 모든 울기 묶음,
/// 도라 표시패). null 이면 전부 0.
Ukeire ukeireOf(List<int> counts, {int melds = 0, List<int>? visible}) {
  final seen = _visibleOrZero(visible);
  _checkSum(counts, melds, 13);
  return _ukeire(counts, melds, seen);
}

/// 버림 후보 하나.
class DiscardOption {
  final int tile;

  /// 버린 뒤 샹텐.
  final int shanten;

  /// 버린 뒤 유효패. 버린 패 한 장이 강에 보이는 것으로 센다.
  final Ukeire ukeire;

  const DiscardOption(this.tile, this.shanten, this.ukeire);

  @override
  String toString() => '${Tiles.toCode(tile)} 버림 → $ukeire';
}

/// [counts] 는 `14 − 3 × melds` 장. 손에 있는 패 종류마다 하나씩.
/// 정렬: 버린 뒤 샹텐 오름차순 → 유효패 장수 내림차순 → 패 번호 오름차순.
List<DiscardOption> discardOptions(List<int> counts,
    {int melds = 0, List<int>? visible}) {
  final seen = _visibleOrZero(visible);
  _checkSum(counts, melds, 14);
  final work = [...counts];
  final options = <DiscardOption>[];
  for (var d = 0; d < Tiles.count; d++) {
    if (work[d] == 0) continue;
    work[d]--;
    // 버린 패 한 장이 강에 보이게 된다.
    final after = [...seen];
    after[d]++;
    final u = _ukeire(work, melds, after);
    options.add(DiscardOption(d, u.shanten, u));
    work[d]++;
  }
  options.sort((a, b) {
    if (a.shanten != b.shanten) return a.shanten - b.shanten;
    final ta = a.ukeire.total;
    final tb = b.ukeire.total;
    if (ta != tb) return tb - ta;
    return a.tile - b.tile;
  });
  return options;
}

Ukeire _ukeire(List<int> counts, int melds, List<int> seen) {
  final base = shanten(counts, melds: melds);
  final work = [...counts];
  final tiles = <UkeireTile>[];
  for (var t = 0; t < Tiles.count; t++) {
    // 5번째 장은 없다.
    if (work[t] >= 4) continue;
    work[t]++;
    final s = shanten(work, melds: melds);
    work[t]--;
    if (s < base) {
      final left = 4 - work[t] - seen[t];
      tiles.add(UkeireTile(t, left > 0 ? left : 0));
    }
  }
  return Ukeire(base, List.unmodifiable(tiles));
}

/// [full] 은 울기 없을 때 장수(13 또는 14).
void _checkSum(List<int> counts, int melds, int full) {
  if (melds < 0 || melds > 4) {
    throw ArgumentError('울기 수는 0~4: $melds');
  }
  if (counts.length != Tiles.count) {
    throw ArgumentError('개수 배열은 34칸이어야 합니다 (현재 ${counts.length})');
  }
  final expected = full - 3 * melds;
  var sum = 0;
  for (final c in counts) {
    sum += c;
  }
  if (sum != expected) {
    throw ArgumentError('닫힌 패는 $expected 장이어야 합니다 (현재 $sum 장)');
  }
}

List<int> _visibleOrZero(List<int>? visible) {
  if (visible == null) return List<int>.filled(Tiles.count, 0);
  if (visible.length != Tiles.count) {
    throw ArgumentError('보이는 패 배열은 34칸이어야 합니다 (현재 ${visible.length})');
  }
  for (final v in visible) {
    if (v < 0) throw ArgumentError('보이는 패 개수가 음수: $v');
  }
  return visible;
}
