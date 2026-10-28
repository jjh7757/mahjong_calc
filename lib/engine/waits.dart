import 'calculator.dart';
import 'decompose.dart';

/// 대기패 하나와 그 패로 화료했을 때의 점수.
class Wait {
  final int tile;

  /// 론 기준 결과. 역이 없으면 [ScoreResult.isValid] 가 false.
  final ScoreResult ron;

  /// 쯔모 기준 결과.
  final ScoreResult tsumo;

  const Wait(this.tile, this.ron, this.tsumo);

  bool get hasYaku => ron.isValid || tsumo.isValid;
}

/// 13장(손패 + 부른 묶음) 기준으로 화료 가능한 패를 전부 찾는다.
///
/// [closedTiles] 는 13 - 3 × 묶음 수 장이어야 한다. 이미 4장 다 보이는 패는 제외한다.
/// 점수는 [situation] 의 론/쯔모를 각각 덮어써서 두 가지로 계산한다.
List<Wait> findWaits(
  List<int> closedTiles,
  List<Meld> melds,
  Situation situation, {
  RuleSet rules = RuleSet.standard,
  int redCount = 0,
}) {
  final expected = 13 - 3 * melds.length;
  if (closedTiles.length != expected) {
    throw ArgumentError('손패는 $expected 장이어야 합니다 (현재 ${closedTiles.length} 장)');
  }
  final visible = toCounts([...closedTiles, for (final m in melds) ...m.tiles]);
  final waits = <Wait>[];
  for (var t = 0; t < Tiles.count; t++) {
    if (visible[t] >= 4) continue;
    final hand = Hand(
      closedTiles: [...closedTiles, t],
      melds: melds,
      winTile: t,
      redCount: redCount,
    );
    if (decompose(hand).isEmpty) continue;
    final ron = calculate(hand, _with(situation, isTsumo: false), rules: rules);
    final tsumo = calculate(hand, _with(situation, isTsumo: true), rules: rules);
    waits.add(Wait(t, ron, tsumo));
  }
  return waits;
}

Situation _with(Situation s, {required bool isTsumo}) => Situation(
      isTsumo: isTsumo,
      seatWind: s.seatWind,
      roundWind: s.roundWind,
      riichi: s.riichi,
      doubleRiichi: s.doubleRiichi,
      ippatsu: s.ippatsu,
      lastTile: s.lastTile,
      rinshan: isTsumo && s.rinshan,
      chankan: !isTsumo && s.chankan,
      firstTurnWin: s.firstTurnWin,
      doraIndicators: s.doraIndicators,
      uraIndicators: s.uraIndicators,
      honba: s.honba,
    );
