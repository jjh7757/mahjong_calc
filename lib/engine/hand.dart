import 'meld.dart';
import 'tile.dart';

/// 화료한 손패. 부른 묶음을 뺀 나머지 패 + 화료패.
class Hand {
  /// 부른 묶음을 제외한 손패(화료패 포함). 14 - 3 × 묶음 수 장.
  final List<int> closedTiles;

  /// 부른 묶음.
  final List<Meld> melds;

  /// 화료패. [closedTiles] 안에 들어 있어야 한다.
  final int winTile;

  /// 적도라 개수(손패와 묶음 전체).
  final int redCount;

  Hand({
    required List<int> closedTiles,
    this.melds = const [],
    required this.winTile,
    this.redCount = 0,
  }) : closedTiles = List.unmodifiable([...closedTiles]..sort()) {
    final expected = 14 - 3 * melds.length;
    if (this.closedTiles.length != expected) {
      throw ArgumentError(
          '손패는 $expected 장이어야 합니다 (현재 ${this.closedTiles.length} 장)');
    }
    if (!this.closedTiles.contains(winTile)) {
      throw ArgumentError('화료패 ${Tiles.toCode(winTile)} 가 손패에 없습니다');
    }
    final total = toCounts(allTiles);
    for (var t = 0; t < Tiles.count; t++) {
      if (total[t] > 4) {
        throw ArgumentError('${Tiles.name(t)} 이(가) 4장을 넘습니다');
      }
    }
  }

  /// 표기법 문자열로 손패를 만든다. 마지막 패를 화료패로 본다.
  ///
  /// 예: `Hand.parse('123m456p78s11z 9s')` → 9s 론/쯔모.
  factory Hand.parse(String closed,
      {List<Meld> melds = const [], int? redCount}) {
    final parsed = parseTiles(closed);
    if (parsed.tiles.isEmpty) throw ArgumentError('손패가 비어 있습니다');
    return Hand(
      closedTiles: parsed.tiles,
      melds: melds,
      winTile: parsed.tiles.last,
      redCount: redCount ?? parsed.redCount,
    );
  }

  /// 묶음까지 합친 전체 패(깡은 4장).
  List<int> get allTiles => [...closedTiles, for (final m in melds) ...m.tiles];

  /// 멘젠인지(부른 묶음이 없거나 안깡뿐).
  bool get isClosed => melds.every((m) => !m.isOpen);

  List<int> get closedCounts => toCounts(closedTiles);
}

/// 화료 상황.
class Situation {
  final bool isTsumo;

  /// 자풍. [Tiles.east] ~ [Tiles.north]
  final int seatWind;

  /// 장풍.
  final int roundWind;

  final bool riichi;
  final bool doubleRiichi;
  final bool ippatsu;

  /// 해저로월(쯔모) / 하저로어(론)
  final bool lastTile;

  /// 영상개화
  final bool rinshan;

  /// 창깡
  final bool chankan;

  /// 천화(친) / 지화(자)
  final bool firstTurnWin;

  final List<int> doraIndicators;
  final List<int> uraIndicators;

  /// 본장 수. 론 +300, 쯔모 각 +100.
  final int honba;

  const Situation({
    required this.isTsumo,
    this.seatWind = Tiles.east,
    this.roundWind = Tiles.east,
    this.riichi = false,
    this.doubleRiichi = false,
    this.ippatsu = false,
    this.lastTile = false,
    this.rinshan = false,
    this.chankan = false,
    this.firstTurnWin = false,
    this.doraIndicators = const [],
    this.uraIndicators = const [],
    this.honba = 0,
  });

  bool get isDealer => seatWind == Tiles.east;
}

/// 룰 옵션.
class RuleSet {
  /// 쿠이탄(울고 탕야오) 허용
  final bool kuitan;

  /// 끌어올림 만관(4판 30부, 3판 60부 → 만관)
  final bool kiriageMangan;

  /// 13판 이상 헤아림 역만
  final bool kazoeYakuman;

  /// 더블 역만(국사 13면, 사암각 단기, 대사희, 구련 9면, 순정 등)
  final bool doubleYakuman;

  /// 연풍패(자풍 = 장풍) 머리 부수. 4 또는 2.
  final int doubleWindPairFu;

  /// 적도라 사용
  final bool redDora;

  const RuleSet({
    this.kuitan = true,
    this.kiriageMangan = false,
    this.kazoeYakuman = true,
    this.doubleYakuman = true,
    this.doubleWindPairFu = 4,
    this.redDora = true,
  });

  static const standard = RuleSet();

  RuleSet copyWith({
    bool? kuitan,
    bool? kiriageMangan,
    bool? kazoeYakuman,
    bool? doubleYakuman,
    int? doubleWindPairFu,
    bool? redDora,
  }) {
    return RuleSet(
      kuitan: kuitan ?? this.kuitan,
      kiriageMangan: kiriageMangan ?? this.kiriageMangan,
      kazoeYakuman: kazoeYakuman ?? this.kazoeYakuman,
      doubleYakuman: doubleYakuman ?? this.doubleYakuman,
      doubleWindPairFu: doubleWindPairFu ?? this.doubleWindPairFu,
      redDora: redDora ?? this.redDora,
    );
  }
}
