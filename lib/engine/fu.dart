import 'decompose.dart';
import 'hand.dart';
import 'tile.dart';

/// 부수 내역 한 줄.
class FuItem {
  final String label;
  final int fu;
  const FuItem(this.label, this.fu);

  @override
  String toString() => '$label $fu';
}

class FuResult {
  final int total;
  final List<FuItem> items;
  const FuResult(this.total, this.items);
}

/// 부수를 계산한다. [isPinfu] 는 역 판정에서 핑후가 성립했는지.
FuResult calculateFu(
  Hand hand,
  Decomposition d,
  Situation sit,
  RuleSet rules, {
  required bool isPinfu,
}) {
  if (d.shape == HandShape.kokushi) {
    return const FuResult(0, [FuItem('역만', 0)]);
  }
  if (d.shape == HandShape.chiitoitsu) {
    return const FuResult(25, [FuItem('치또이쯔', 25)]);
  }
  if (isPinfu) {
    return sit.isTsumo
        ? const FuResult(20, [FuItem('핑후 쯔모', 20)])
        : const FuResult(30, [FuItem('기본', 20), FuItem('멘젠 론', 10)]);
  }

  final items = <FuItem>[const FuItem('기본', 20)];
  final closed = hand.isClosed;

  if (closed && !sit.isTsumo) items.add(const FuItem('멘젠 론', 10));
  if (sit.isTsumo) items.add(const FuItem('쯔모', 2));

  for (var i = 0; i < d.sets.length; i++) {
    final s = d.sets[i];
    if (!s.isTriplet) continue;
    final outer = Tiles.isTerminalOrHonor(s.tile);
    final ronCompleted =
        !sit.isTsumo && i == d.winSetIndex && d.wait == WaitType.shanpon;
    final concealed = !s.isCalled && !ronCompleted;
    var fu = outer ? 4 : 2;
    if (concealed) fu *= 2;
    if (s.isKan) fu *= 4;
    final kind = s.isKan
        ? (concealed ? '안깡' : '깡')
        : (concealed ? '암각' : '명각');
    items.add(FuItem('${Tiles.name(s.tile)} $kind', fu));
  }

  final pairTile = d.pair.tile;
  var pairFu = 0;
  if (Tiles.isDragon(pairTile)) pairFu = 2;
  final isSeat = pairTile == sit.seatWind;
  final isRound = pairTile == sit.roundWind;
  if (isSeat && isRound) {
    pairFu = rules.doubleWindPairFu;
  } else if (isSeat || isRound) {
    pairFu = 2;
  }
  if (pairFu > 0) items.add(FuItem('${Tiles.name(pairTile)} 머리', pairFu));

  switch (d.wait) {
    case WaitType.kanchan:
      items.add(const FuItem('간짱 대기', 2));
      break;
    case WaitType.penchan:
      items.add(const FuItem('변짱 대기', 2));
      break;
    case WaitType.tanki:
      items.add(const FuItem('단기 대기', 2));
      break;
    case WaitType.ryanmen:
    case WaitType.shanpon:
      break;
  }

  var total = items.fold<int>(0, (sum, it) => sum + it.fu);
  if (!closed && total == 20) {
    items.add(const FuItem('울고 핑후형 보정', 10));
    total = 30;
  }
  final rounded = (total + 9) ~/ 10 * 10;
  if (rounded != total) items.add(FuItem('올림', rounded - total));
  return FuResult(rounded, items);
}
