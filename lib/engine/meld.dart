import 'tile.dart';

/// 부른 묶음 종류.
enum MeldType { chi, pon, kan }

/// 부른 묶음(멘칸·펑·깡). 안깡은 [isOpen] 이 false 인 깡이다.
class Meld {
  final MeldType type;

  /// 정렬된 패. 치는 3장, 펑 3장, 깡 4장.
  final List<int> tiles;

  /// 남의 패로 만들었는지. 안깡만 false.
  final bool isOpen;

  Meld._(this.type, List<int> tiles, this.isOpen)
      : tiles = List.unmodifiable([...tiles]..sort());

  /// 치. [lowest] 는 가장 낮은 패.
  factory Meld.chi(int lowest) {
    if (lowest >= 27 || Tiles.number(lowest) > 7) {
      throw ArgumentError('치를 만들 수 없는 패: ${Tiles.toCode(lowest)}');
    }
    return Meld._(MeldType.chi, [lowest, lowest + 1, lowest + 2], true);
  }

  factory Meld.pon(int tile) => Meld._(MeldType.pon, [tile, tile, tile], true);

  /// 대명깡·가깡.
  factory Meld.openKan(int tile) =>
      Meld._(MeldType.kan, [tile, tile, tile, tile], true);

  /// 안깡.
  factory Meld.closedKan(int tile) =>
      Meld._(MeldType.kan, [tile, tile, tile, tile], false);

  int get first => tiles.first;
  bool get isKan => type == MeldType.kan;
  bool get isSequence => type == MeldType.chi;

  @override
  String toString() {
    final body = tiles.map(Tiles.toCode).join(' ');
    return isOpen ? '[$body]' : '($body)';
  }
}
