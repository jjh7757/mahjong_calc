/// 패보의 결과(끝 손패·화료패·울기)와 사건(리치·울기)에서 점수 계산에 넣을 손패와 상황을 만든다. 순수 Dart.
library;

import '../engine/calculator.dart';
import 'paifu.dart';

/// 패보 한 국의 점수 계산.
class PaifuScore {
  final Hand hand;
  final Situation situation;
  final ScoreResult result;
  const PaifuScore(this.hand, this.situation, this.result);
}

/// 국 이름("남2국")의 장풍. 못 읽으면 동.
int roundWindOf(String round) {
  const names = ['동', '남', '서', '북'];
  for (var i = 0; i < names.length; i++) {
    if (round.startsWith(names[i])) return Tiles.east + i;
  }
  return Tiles.east;
}

/// 화료 상황. 결과에 [PaifuResult.flags] 가 적혀 있으면(앱이 화료 사진을 읽을 때 정한 값) 그대로 쓰고,
/// 없으면 사건에서 헤아린다: 리치 = 화료자의 리치 선언 버림, 더블 리치 = 그것이 첫 버림이고 그 앞에 울기가 없음,
/// 일발 = 리치 뒤 화료자가 더 버리지 않았고 그 사이 울기가 없음, 해저·하저 = 남은 패 0.
/// 영상·창깡·천화는 사건만으로는 알 수 없어 flags 가 있을 때만.
Situation situationOf(Paifu p) {
  final r = p.result!;
  final winner = r.winner!;
  final f = r.flags;
  var riichi = false, doubleRiichi = false, ippatsu = false;
  var mine = 0, afterRiichi = 0, callsSoFar = 0, callsAfterRiichi = 0;
  for (final e in p.events) {
    if (e.type == PaifuEventType.call) {
      callsSoFar++;
      if (riichi) callsAfterRiichi++;
    } else if (e.type == PaifuEventType.discard && e.seat == winner) {
      mine++;
      if (riichi) {
        afterRiichi++;
      } else if (e.riichi) {
        riichi = true;
        doubleRiichi = mine == 1 && callsSoFar == 0;
      }
    }
  }
  ippatsu = riichi && afterRiichi == 0 && callsAfterRiichi == 0;
  final isTsumo = r.type == 'tsumo';
  return Situation(
    isTsumo: isTsumo,
    seatWind: Tiles.east + p.windOf(winner),
    roundWind: roundWindOf(p.round),
    riichi: f?['riichi'] ?? (riichi && !doubleRiichi),
    doubleRiichi: f?['double_riichi'] ?? doubleRiichi,
    ippatsu: f?['ippatsu'] ?? ippatsu,
    lastTile: f?['last_tile'] ?? (p.states.last.wallLeft == 0),
    rinshan: f?['rinshan'] ?? false,
    chankan: f?['chankan'] ?? false,
    firstTurnWin: f?['first_turn'] ?? false,
    doraIndicators: [for (final t in p.doraIndicators) t.tile],
    uraIndicators: [for (final t in p.uraIndicators) t.tile],
    honba: p.honba,
  );
}

/// 결과의 울기 묶음 → 엔진 묶음. 모르는 꼴이면 null.
Meld? _meldOf(PaifuResultMeld m) {
  if (m.tiles.isEmpty) return null;
  final tiles = [for (final t in m.tiles) t.tile]..sort();
  try {
    return switch (m.kind) {
      'chi' => Meld.chi(tiles.first),
      'pon' => Meld.pon(tiles.first),
      'kan' => Meld.openKan(tiles.first),
      'ankan' => Meld.closedKan(tiles.first),
      _ => null,
    };
  } on ArgumentError {
    return null;
  }
}

/// 화료로 끝났고 끝 손패·화료패가 적힌 패보면 점수를 낸다. 유국이거나 손패가 없으면 null.
/// 손패 장수가 안 맞는 등 계산할 수 없는 기록도 null(재생 화면은 결과 화면을 띄우지 않는다).
PaifuScore? scoreOf(Paifu p, {RuleSet rules = RuleSet.standard}) {
  final r = p.result;
  if (r == null || r.winner == null || r.hand == null || r.winTile == null) return null;
  if (r.type != 'ron' && r.type != 'tsumo') return null;
  final melds = <Meld>[];
  for (final m in r.melds) {
    final e = _meldOf(m);
    if (e == null) return null;
    melds.add(e);
  }
  final all = [...r.hand!, r.winTile!, for (final m in r.melds) ...m.tiles];
  final reds = [
    for (final t in all)
      if (t.red) t.tile,
  ];
  final Hand hand;
  try {
    hand = Hand(
      closedTiles: [for (final t in r.hand!) t.tile, r.winTile!.tile],
      melds: melds,
      winTile: r.winTile!.tile,
      redCount: reds.length,
      redTiles: reds,
    );
  } on ArgumentError {
    return null;
  }
  final sit = situationOf(p);
  return PaifuScore(hand, sit, calculate(hand, sit, rules: rules));
}
