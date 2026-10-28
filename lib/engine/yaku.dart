import 'decompose.dart';
import 'hand.dart';
import 'tile.dart';

/// 역 목록. [closedHan] 멘젠 판수, [openHan] 울었을 때 판수(0이면 불가).
/// 역만은 [yakuman] 이 배수(1 = 역만, 2 = 더블 역만).
enum Yaku {
  riichi('리치', 1, 0),
  doubleRiichi('더블 리치', 2, 0),
  ippatsu('일발', 1, 0),
  menzenTsumo('멘젠 쯔모', 1, 0),
  pinfu('핑후', 1, 0),
  tanyao('탕야오', 1, 1),
  iipeikou('이페코', 1, 0),
  seatWind('자풍패', 1, 1),
  roundWind('장풍패', 1, 1),
  haku('백', 1, 1),
  hatsu('발', 1, 1),
  chun('중', 1, 1),
  haitei('해저로월', 1, 1),
  houtei('하저로어', 1, 1),
  rinshan('영상개화', 1, 1),
  chankan('창깡', 1, 1),
  chanta('찬타', 2, 1),
  ittsu('일기통관', 2, 1),
  sanshokuDoujun('삼색동순', 2, 1),
  sanshokuDoukou('삼색동각', 2, 2),
  toitoi('또이또이', 2, 2),
  sanankou('산안커', 2, 2),
  sankantsu('산깡쯔', 2, 2),
  chiitoitsu('치또이쯔', 2, 0),
  honroutou('혼노두', 2, 2),
  shousangen('소삼원', 2, 2),
  honitsu('혼일색', 3, 2),
  junchan('준찬타', 3, 2),
  ryanpeikou('량페코', 3, 0),
  chinitsu('청일색', 6, 5),
  dora('도라', 1, 1),
  akaDora('적도라', 1, 1),
  uraDora('뒷도라', 1, 1),
  // 역만
  kokushi('국사무쌍', 13, 0, yakuman: 1),
  kokushi13('국사무쌍 13면 대기', 26, 0, yakuman: 2),
  suuankou('사암각', 13, 0, yakuman: 1),
  suuankouTanki('사암각 단기 대기', 26, 0, yakuman: 2),
  daisangen('대삼원', 13, 13, yakuman: 1),
  shousuushi('소사희', 13, 13, yakuman: 1),
  daisuushi('대사희', 26, 26, yakuman: 2),
  tsuuiisou('자일색', 13, 13, yakuman: 1),
  chinroutou('청노두', 13, 13, yakuman: 1),
  ryuuiisou('녹일색', 13, 13, yakuman: 1),
  chuuren('구련보등', 13, 0, yakuman: 1),
  chuuren9('순정 구련보등', 26, 0, yakuman: 2),
  suukantsu('사깡쯔', 13, 13, yakuman: 1),
  tenhou('천화', 13, 0, yakuman: 1),
  chiihou('지화', 13, 0, yakuman: 1);

  const Yaku(this.label, this.closedHan, this.openHan, {this.yakuman = 0});

  final String label;
  final int closedHan;
  final int openHan;
  final int yakuman;

  bool get isYakuman => yakuman > 0;

  /// 더블 역만을 쓰지 않을 때의 대응 역만.
  Yaku get singleYakuman {
    switch (this) {
      case Yaku.kokushi13:
        return Yaku.kokushi;
      case Yaku.suuankouTanki:
        return Yaku.suuankou;
      case Yaku.daisuushi:
        return Yaku.daisuushi;
      case Yaku.chuuren9:
        return Yaku.chuuren;
      default:
        return this;
    }
  }
}

/// 성립한 역과 그 판수. 역만이면 [han] 은 역만 배수다.
class YakuHan {
  final Yaku yaku;
  final int han;
  const YakuHan(this.yaku, this.han);

  @override
  String toString() => '${yaku.label} $han';
}

/// 론으로 완성된 커쯔는 명각으로 친다. 그 외 안 부른 커쯔·깡은 암각.
List<TileSet> concealedTriplets(Decomposition d, Situation sit) {
  final result = <TileSet>[];
  for (var i = 0; i < d.sets.length; i++) {
    final s = d.sets[i];
    if (!s.isTriplet || s.isCalled) continue;
    if (!sit.isTsumo && i == d.winSetIndex && d.wait == WaitType.shanpon) {
      continue;
    }
    result.add(s);
  }
  return result;
}

/// 한 분해에 대해 성립하는 역을 전부 찾는다. 도라는 포함하지 않는다.
/// 역만이 하나라도 있으면 역만만 돌려준다.
List<YakuHan> detectYaku(
    Hand hand, Decomposition d, Situation sit, RuleSet rules) {
  final closed = hand.isClosed;
  final all = hand.allTiles;
  final counts = toCounts(all);
  final sets = d.sets;

  final yakuman = <Yaku>[];

  if (sit.firstTurnWin && sit.isTsumo && hand.melds.isEmpty) {
    yakuman.add(sit.isDealer ? Yaku.tenhou : Yaku.chiihou);
  }

  if (d.shape == HandShape.kokushi) {
    yakuman.add(counts[hand.winTile] == 2 ? Yaku.kokushi13 : Yaku.kokushi);
  } else {
    if (all.every(Tiles.isHonor)) yakuman.add(Yaku.tsuuiisou);
    if (d.shape == HandShape.standard) {
      final triplets = sets.where((s) => s.isTriplet).toList();
      final concealed = concealedTriplets(d, sit).length;
      final dragonTriplets = triplets.where((s) => Tiles.isDragon(s.tile)).length;
      final windTriplets = triplets.where((s) => Tiles.isWind(s.tile)).length;
      final kans = sets.where((s) => s.isKan).length;

      if (closed && concealed == 4) {
        yakuman.add(
            d.wait == WaitType.tanki ? Yaku.suuankouTanki : Yaku.suuankou);
      }
      if (dragonTriplets == 3) yakuman.add(Yaku.daisangen);
      if (windTriplets == 4) {
        yakuman.add(Yaku.daisuushi);
      } else if (windTriplets == 3 && Tiles.isWind(d.pair.tile)) {
        yakuman.add(Yaku.shousuushi);
      }
      if (all.every(Tiles.isTerminal)) yakuman.add(Yaku.chinroutou);
      if (all.every(Tiles.isGreen)) yakuman.add(Yaku.ryuuiisou);
      if (kans == 4) yakuman.add(Yaku.suukantsu);
      if (hand.melds.isEmpty) {
        final chuuren = _chuuren(counts, hand.winTile);
        if (chuuren != null) yakuman.add(chuuren);
      }
    }
  }

  if (yakuman.isNotEmpty) {
    return yakuman
        .map((y) => rules.doubleYakuman ? y : y.singleYakuman)
        .map((y) => YakuHan(y, y.yakuman))
        .toList();
  }

  final found = <Yaku>[];

  // 상황역
  if (closed) {
    if (sit.doubleRiichi) {
      found.add(Yaku.doubleRiichi);
    } else if (sit.riichi) {
      found.add(Yaku.riichi);
    }
    if ((sit.riichi || sit.doubleRiichi) && sit.ippatsu) {
      found.add(Yaku.ippatsu);
    }
    if (sit.isTsumo) found.add(Yaku.menzenTsumo);
  }
  if (sit.lastTile) found.add(sit.isTsumo ? Yaku.haitei : Yaku.houtei);
  if (sit.rinshan && sit.isTsumo) found.add(Yaku.rinshan);
  if (sit.chankan && !sit.isTsumo) found.add(Yaku.chankan);

  // 패 구성만으로 정해지는 역 (치또이에도 적용)
  if (all.every(Tiles.isSimple) && (closed || rules.kuitan)) {
    found.add(Yaku.tanyao);
  }
  if (all.every(Tiles.isTerminalOrHonor)) found.add(Yaku.honroutou);
  final suits = all.where((t) => !Tiles.isHonor(t)).map(Tiles.suit).toSet();
  if (suits.length == 1) {
    found.add(all.any(Tiles.isHonor) ? Yaku.honitsu : Yaku.chinitsu);
  }

  if (d.shape == HandShape.chiitoitsu) {
    found.add(Yaku.chiitoitsu);
  } else {
    found.addAll(_standardYaku(hand, d, sit, rules));
  }

  return found
      .map((y) => YakuHan(y, closed ? y.closedHan : y.openHan))
      .where((yh) => yh.han > 0)
      .toList();
}

List<Yaku> _standardYaku(
    Hand hand, Decomposition d, Situation sit, RuleSet rules) {
  final closed = hand.isClosed;
  final all = hand.allTiles;
  final sets = d.sets;
  final seqs = sets.where((s) => s.isSequence).map((s) => s.tile).toList();
  final triplets = sets.where((s) => s.isTriplet).toList();
  final tripletTiles = triplets.map((s) => s.tile).toSet();
  final pair = d.pair;
  final found = <Yaku>[];

  bool isYakuhai(int t) =>
      Tiles.isDragon(t) || t == sit.seatWind || t == sit.roundWind;

  if (closed &&
      seqs.length == 4 &&
      !isYakuhai(pair.tile) &&
      d.wait == WaitType.ryanmen) {
    found.add(Yaku.pinfu);
  }

  if (closed) {
    var identicalPairs = 0;
    for (final t in seqs.toSet()) {
      identicalPairs += seqs.where((x) => x == t).length ~/ 2;
    }
    if (identicalPairs == 2) {
      found.add(Yaku.ryanpeikou);
    } else if (identicalPairs == 1) {
      found.add(Yaku.iipeikou);
    }
  }

  for (var s = 0; s < 3; s++) {
    final base = s * 9;
    if (seqs.contains(base) &&
        seqs.contains(base + 3) &&
        seqs.contains(base + 6)) {
      found.add(Yaku.ittsu);
      break;
    }
  }

  for (var n = 0; n < 7; n++) {
    if (seqs.contains(n) && seqs.contains(9 + n) && seqs.contains(18 + n)) {
      found.add(Yaku.sanshokuDoujun);
      break;
    }
  }
  for (var n = 0; n < 9; n++) {
    if (tripletTiles.contains(n) &&
        tripletTiles.contains(9 + n) &&
        tripletTiles.contains(18 + n)) {
      found.add(Yaku.sanshokuDoukou);
      break;
    }
  }

  if (triplets.length == 4) found.add(Yaku.toitoi);
  if (concealedTriplets(d, sit).length == 3) found.add(Yaku.sanankou);
  if (sets.where((s) => s.isKan).length == 3) found.add(Yaku.sankantsu);

  final allOuter = sets.every(_touchesTerminalOrHonor);
  if (allOuter && seqs.isNotEmpty) {
    found.add(all.any(Tiles.isHonor) ? Yaku.chanta : Yaku.junchan);
  }

  final dragonTriplets = triplets.where((s) => Tiles.isDragon(s.tile)).length;
  if (dragonTriplets == 2 && Tiles.isDragon(pair.tile)) {
    found.add(Yaku.shousangen);
  }

  for (final t in tripletTiles) {
    if (t == Tiles.white) found.add(Yaku.haku);
    if (t == Tiles.green) found.add(Yaku.hatsu);
    if (t == Tiles.red) found.add(Yaku.chun);
    if (t == sit.seatWind) found.add(Yaku.seatWind);
    if (t == sit.roundWind) found.add(Yaku.roundWind);
  }

  return found;
}

bool _touchesTerminalOrHonor(TileSet s) {
  if (s.isSequence) {
    final n = Tiles.number(s.tile);
    return n == 1 || n == 7;
  }
  return Tiles.isTerminalOrHonor(s.tile);
}

Yaku? _chuuren(List<int> counts, int winTile) {
  final suits = <int>{};
  for (var t = 0; t < Tiles.count; t++) {
    if (counts[t] > 0) {
      if (Tiles.isHonor(t)) return null;
      suits.add(Tiles.suit(t));
    }
  }
  if (suits.length != 1) return null;
  final base = suits.first * 9;
  const pattern = [3, 1, 1, 1, 1, 1, 1, 1, 3];
  for (var i = 0; i < 9; i++) {
    if (counts[base + i] < pattern[i]) return null;
  }
  final remaining = [...counts];
  remaining[winTile]--;
  var pure = true;
  for (var i = 0; i < 9; i++) {
    if (remaining[base + i] != pattern[i]) pure = false;
  }
  return pure ? Yaku.chuuren9 : Yaku.chuuren;
}
