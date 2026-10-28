/// 사진 판독([HandReading]·[CenterReading])과 대국 기록([Game])을 합쳐 계산 입력을 만든다. 순수 Dart.
///
/// 규칙(docs/table_reading_design.md "merge 규칙"):
/// 1. 화료자는 호출 쪽이 정해 [winnerSide] 로 넘긴다(눕힌 자리 하나면 자동, 둘 이상이면 물음).
/// 2. 자풍·장풍·본장은 기록에서. 리치는 사진·기록 중 하나라도 true 면 true, 어긋나면 플래그.
///    단, 울린 손패(안깡 제외)는 리치가 불가능하므로 사진·기록의 리치를 버리고 플래그만 남긴다.
/// 3. 도라 표시패는 사진에서. 뒷도라 표시패도 구분하지 않고 도라 표시패로 센다(리치 화료면 점수가 같다).
/// 4. 화료패가 어떤 강의 마지막 버림패와 같으면 론(그 자리가 방총자), 없으면 쯔모, 둘 이상이면 론 + 방총자 플래그.
///    화료패가 없고 손패가 한 장 모자라면, 다른 자리 강 끝 패 중 화료가 되는 패를 화료패로 넣고 론(그 자리가 방총자).
///    강 끝을 못 읽은 자리가 있으면 대기패로 정한다: 못 읽은 자리가 하나이고 대기패도 하나면 그 자리가 그 패로 론,
///    아니면 후보를 적어 묻는다(화료패를 다시 읽지 않는다).
///    그래도 없으면 손패 마지막 장을 화료패로 보고 플래그.
/// 5. 장수가 안 맞으면 [TableMerge.hand] 는 null — 바로 판독 수정으로.
/// 6. 확신도 낮은 패는 [TableMerge.uncertain] 로.
/// 7. 사진에서 리치(횡치·리치봉)가 보인 자리는 [TableMerge.photoRiichiSeats] 로. 화료 기록 때 리치봉 자동 반영에 쓴다.
library;

import '../engine/calculator.dart' show Hand, Meld, Situation, Tiles;
import '../engine/decompose.dart' show decompose;
import '../game/game.dart';
import 'seat_map.dart';
import 'table_layout.dart';
import 'table_reading.dart';

enum MergeIssue {
  riichiMismatch,
  riichiImpossible,
  loserAmbiguous,
  winTileAssumed,
  winFromDiscard,
  winFromWait,
  winTileUnknown,
  ronTsumoUnknown,
  tileCountMismatch,
  meldUncertain,
  meldTracked,
  uncertainTiles,
  invalidHand,
  multiRon,
}

class MergeFlag {
  final MergeIssue issue;
  final String message;
  const MergeFlag(this.issue, this.message);
  @override
  String toString() => '${issue.name}: $message';
}

/// 손패 한 장(화료패 포함). 입력 화면의 HandTile 로 그대로 옮길 수 있다.
class MergedTile {
  final int tile;
  final bool red;
  final double conf;
  const MergedTile(this.tile, {this.red = false, this.conf = 1});
}

/// 사진 리치를 자동 반영할 최소 확신도.
const double autoRiichiMinConf = 0.6;

class TableMerge {
  final int winner;
  final Side winnerSide;
  final bool isTsumo;

  /// 방총자 자리. 쯔모거나 못 정했으면 null.
  final int? loser;

  /// 멘젠 부분 + 화료패(마지막).
  final List<MergedTile> closed;
  final List<Meld> melds;

  /// 각 울기의 적도라 수.
  final List<int> meldRed;
  final Situation situation;

  /// 장수가 맞고 유효할 때만. null 이면 판독 수정 화면으로 간다.
  final Hand? hand;

  /// [closed] 에서 확신도가 낮은 인덱스.
  final Set<int> uncertain;
  final List<MergeFlag> flags;

  /// 사진 중앙 판독에서 리치가 보인 자리(화료자 포함, 확신도 [autoRiichiMinConf] 이상).
  final Set<int> photoRiichiSeats;

  const TableMerge({
    required this.winner,
    required this.winnerSide,
    required this.isTsumo,
    required this.loser,
    required this.closed,
    required this.melds,
    required this.meldRed,
    required this.situation,
    required this.hand,
    required this.uncertain,
    required this.flags,
    this.photoRiichiSeats = const {},
  });

  int get redCount => closed.where((t) => t.red).length + meldRed.fold(0, (a, b) => a + b);
  bool hasFlag(MergeIssue i) => flags.any((f) => f.issue == i);

  /// 계산을 바로 보여주면 안 되고 수정 화면부터 가야 하는가.
  bool get needsFix => hand == null;
}

/// 울기 읽기 → 엔진 [Meld]. 정합성이 틀린 것은 가장 그럴듯하게 고치고 [fixed] 를 true 로.
({Meld meld, int red, bool fixed}) _toMeld(ReadMeld m) {
  final tiles = m.tiles.map((t) => t.tile).toList()..sort();
  final red = m.tiles.where((t) => t.red).length;
  switch (m.type) {
    case ReadMeldType.chi:
      final lowest = tiles.first;
      final ok = Tiles.suit(lowest) < 3 &&
          Tiles.number(lowest) <= 7 &&
          tiles[1] == lowest + 1 &&
          tiles[2] == lowest + 2;
      final base = ok ? lowest : (Tiles.suit(lowest) < 3 ? lowest.clamp(0, 26) : 0);
      final start = Tiles.number(base) > 7 ? base - (Tiles.number(base) - 7) : base;
      return (meld: Meld.chi(start), red: red, fixed: !ok);
    case ReadMeldType.pon:
    case ReadMeldType.kanOpen:
    case ReadMeldType.kanClosed:
      final t = _mostCommon(tiles);
      final ok = tiles.every((x) => x == t);
      final meld = switch (m.type) {
        ReadMeldType.pon => Meld.pon(t),
        ReadMeldType.kanOpen => Meld.openKan(t),
        _ => Meld.closedKan(t),
      };
      return (meld: meld, red: red, fixed: !ok);
  }
}

/// [closed](한 장 모자란 멘젠 부분)에 [tile] 을 더하면 화료형인가.
bool _completes(List<MergedTile> closed, List<Meld> melds, ReadTile? tile) {
  if (tile == null) return false;
  try {
    return decompose(Hand(
      closedTiles: [for (final t in closed) t.tile, tile.tile],
      melds: melds,
      winTile: tile.tile,
    )).isNotEmpty;
  } on ArgumentError {
    return false;
  }
}

/// [closed](한 장 모자란 멘젠 부분)의 대기패. 이미 4장 다 보인 패는 뺀다.
List<int> _waitTiles(List<MergedTile> closed, List<Meld> melds) {
  final seen = <int, int>{};
  for (final t in [for (final c in closed) c.tile, for (final m in melds) ...m.tiles]) {
    seen[t] = (seen[t] ?? 0) + 1;
  }
  return [
    for (var t = 0; t < 34; t++)
      if ((seen[t] ?? 0) < 4 && _completes(closed, melds, ReadTile(t))) t,
  ];
}

int _mostCommon(List<int> xs) {
  final n = <int, int>{};
  for (final x in xs) {
    n[x] = (n[x] ?? 0) + 1;
  }
  var best = xs.first;
  for (final e in n.entries) {
    if (e.value > n[best]!) best = e.key;
  }
  return best;
}

/// [otherWinners] 는 동시 론(더블론·트리플론)의 다른 화료자 자리. 방총자 후보에서 뺀다.
TableMerge mergeReading({
  required HandReading hand,
  required CenterReading? center,
  required Side winnerSide,
  required Game game,
  required SeatMap seats,
  Set<Side> otherWinners = const {},
  double uncertainBelow = 0.7,
  bool meldsTracked = false,
}) {
  final flags = <MergeFlag>[];
  final winner = seats.seatOf(winnerSide);
  bool canDealIn(Side s) => s != winnerSide && !otherWinners.contains(s);

  // 울기
  final melds = <Meld>[];
  final meldRed = <int>[];
  for (final m in hand.melds) {
    final r = _toMeld(m);
    melds.add(r.meld);
    meldRed.add(r.red);
    if (r.fixed || m.conf < uncertainBelow) {
      flags.add(MergeFlag(MergeIssue.meldUncertain, '울기 ${r.meld} 를 확인하세요'));
    }
  }
  if (meldsTracked && melds.isNotEmpty) {
    flags.add(MergeFlag(MergeIssue.meldTracked, '울기 ${melds.length}묶음은 게임 중 미리 읽어 둔 것입니다'));
  }
  final expected = 14 - 3 * melds.length;

  // 손패 + 화료패
  final closed = <MergedTile>[
    for (final t in hand.tiles) MergedTile(t.tile, red: t.red, conf: t.conf),
  ];
  ReadTile? win = hand.winTile;
  Side? ronFrom;
  if (win == null && center != null && closed.length == expected - 1) {
    // 론한 패는 버린 사람 강 끝에 그대로 있다. 손패에 더해 화료가 되는 강 끝 패를 찾는다.
    final found = <Side>[
      for (final s in Side.values)
        if (canDealIn(s) && _completes(closed, melds, center.lastDiscardAt(s))) s,
    ];
    if (found.isNotEmpty) {
      ronFrom = found.length == 1 ? found.single : _nearestAfterWinner(winnerSide, found, seats);
      win = center.lastDiscardAt(ronFrom)!;
      final loserSeat = seats.seatOf(ronFrom);
      flags.add(MergeFlag(
        found.length == 1 ? MergeIssue.winFromDiscard : MergeIssue.loserAmbiguous,
        found.length == 1
            ? '손패가 ${expected - 1}장이라 ${ronFrom.label}(${game.names[loserSeat]}) 강 끝 ${Tiles.name(win.tile)} 로 론으로 봤습니다'
            : '${found.map((s) => s.label).join('·')} 강 끝 패가 모두 화료됩니다. ${_furitenNote(ronFrom, game.names[loserSeat])}',
      ));
    } else {
      // 화료되는 강 끝이 없다. 강 끝을 못 읽은 자리가 쏘였을 수 있다(판독이 가끔 "강 없음" 으로 답한다).
      // 대기패가 하나이고 못 읽은 자리가 하나면 그 자리가 그 패로 론. 화료패를 다시 읽지 않고 손패로 정한다.
      final unread = [
        for (final s in Side.values)
          if (canDealIn(s) && center.lastDiscardAt(s) == null) s,
      ];
      final waits = _waitTiles(closed, melds);
      if (unread.length == 1 && waits.length == 1) {
        ronFrom = unread.single;
        final t = waits.single;
        // 수패 5 는 적도라인지 사진으로 못 봤으니 확인을 묻는다(확신도를 낮춰 노란 테두리).
        final maybeRed = Tiles.suit(t) < 3 && Tiles.number(t) == 5;
        win = ReadTile(t, conf: maybeRed ? 0.5 : 0.9);
        flags.add(MergeFlag(
          MergeIssue.winFromWait,
          '${ronFrom.label}(${game.names[seats.seatOf(ronFrom)]}) 강 끝을 읽지 못했지만 대기패가 ${Tiles.name(t)} 하나라 '
          '그 자리가 ${Tiles.name(t)} 로 쏘였다고 봤습니다',
        ));
      } else if (unread.isNotEmpty && waits.isNotEmpty) {
        flags.add(MergeFlag(
          MergeIssue.winTileUnknown,
          '${unread.map((s) => s.label).join('·')} 강 끝을 읽지 못했습니다. '
          '${waits.map(Tiles.name).join('·')} 중 무엇으로 누가 쏘였는지 골라 주세요',
        ));
      }
    }
  }
  if (win != null) {
    closed.add(MergedTile(win.tile, red: win.red, conf: win.conf));
  } else if (closed.isNotEmpty) {
    win = hand.tiles.last;
    flags.add(const MergeFlag(MergeIssue.winTileAssumed, '화료패를 따로 찾지 못해 손패 마지막 장으로 봤습니다'));
  }

  // 확신도
  final uncertain = <int>{
    for (var i = 0; i < closed.length; i++)
      if (closed[i].conf < uncertainBelow) i,
  };
  if (uncertain.isNotEmpty) {
    flags.add(MergeFlag(MergeIssue.uncertainTiles, '확신이 낮은 패 ${uncertain.length}장'));
  }

  // 리치: 사진 ∪ 기록. 울린 손패면 불가능하니 버린다(사진이 옆 자리 횡치를 잘못 본 경우가 흔하다).
  final photoRiichi = center?.riichiAt(winnerSide);
  final recordRiichi = game.riichiSeats.contains(winner);
  final openHand = melds.any((m) => m.isOpen);
  var riichi = (photoRiichi ?? false) || recordRiichi;
  if (openHand && riichi) {
    riichi = false;
    flags.add(MergeFlag(
      MergeIssue.riichiImpossible,
      '울린 손패라 리치가 불가능합니다. ${recordRiichi ? '기록' : '사진'}의 리치를 무시했습니다',
    ));
  } else if (photoRiichi != null && photoRiichi != recordRiichi) {
    flags.add(MergeFlag(
      MergeIssue.riichiMismatch,
      photoRiichi
          ? '사진에는 리치(횡치)가 보이는데 기록에는 없습니다. 반영할 때 리치봉을 자동으로 넣습니다'
          : '기록에는 리치인데 사진에서 횡치를 못 찾았습니다',
    ));
  }

  // 론/쯔모·방총자
  var isTsumo = false;
  int? loser;
  if (ronFrom != null) {
    loser = seats.seatOf(ronFrom);
  } else if (center == null) {
    flags.add(const MergeFlag(MergeIssue.ronTsumoUnknown, '중앙을 읽지 못해 론/쯔모를 정하지 못했습니다'));
  } else if (win != null) {
    final matches = <Side>[
      for (final s in Side.values)
        if (canDealIn(s) && center.lastDiscardAt(s)?.tile == win.tile) s,
    ];
    if (matches.length == 1) {
      loser = seats.seatOf(matches.first);
    } else if (matches.isEmpty) {
      isTsumo = true;
    } else {
      final s = _nearestAfterWinner(winnerSide, matches, seats);
      loser = seats.seatOf(s);
      flags.add(MergeFlag(
          MergeIssue.loserAmbiguous,
          '화료패 ${Tiles.name(win.tile)} 이(가) ${matches.map((s) => s.label).join('·')} 강 끝에 모두 있습니다. '
          '${_furitenNote(s, game.names[loser])}'));
    }
  }

  // 도라·뒷도라: 사진에서 어느 쪽이 뒷도라인지 가르기 어렵고(왕패 짝의 위아래), 리치 화료면 둘 다 1판씩이라
  // 점수가 같다. 보인 앞면 표시패를 모두 도라 표시패로 센다.
  // 어디서 읽을지: 매장에서는 리치 화료면 화료자가 도라·뒷도라 표시패를 자기 손패 옆으로 가져가고, 리치가 아니면
  // 왕패에 그대로 둔다(2026-10-26 사용자 관찰). 그래서 리치면 손패 옆을, 아니면 가운데를 먼저 쓰고 비었을 때만 다른 쪽.
  // 깡이 있으면 도라 2장·뒷도라 1장처럼 홀수일 수 있어 장수 짝 검사는 하지 않는다(사용자 결정).
  final centerIndicators = [...?center?.doraIndicators, ...?center?.uraIndicators];
  final handSide = center?.handSideIndicators ?? const <ReadTile>[];
  final indicators = riichi
      ? (handSide.isNotEmpty ? handSide : centerIndicators)
      : (centerIndicators.isNotEmpty ? centerIndicators : handSide);
  final situation = Situation(
    isTsumo: isTsumo,
    seatWind: game.seatWindOf(winner),
    roundWind: game.roundWindTile,
    riichi: riichi,
    doraIndicators: [for (final d in indicators) d.tile],
    honba: game.honba,
  );

  // 손패 만들기
  Hand? engineHand;
  if (closed.length != expected) {
    flags.add(MergeFlag(MergeIssue.tileCountMismatch,
        '손패가 $expected장이어야 하는데 ${closed.length}장 읽혔습니다'));
  } else {
    try {
      engineHand = Hand(
        closedTiles: closed.map((t) => t.tile).toList(),
        melds: melds,
        winTile: win!.tile,
        redCount: closed.where((t) => t.red).length + meldRed.fold(0, (a, b) => a + b),
      );
    } on ArgumentError catch (e) {
      flags.add(MergeFlag(MergeIssue.invalidHand, e.message.toString()));
    }
  }

  return TableMerge(
    winner: winner,
    winnerSide: winnerSide,
    isTsumo: isTsumo,
    loser: loser,
    closed: closed,
    melds: melds,
    meldRed: meldRed,
    situation: situation,
    hand: engineHand,
    uncertain: uncertain,
    flags: flags,
    photoRiichiSeats: {
      if (center != null)
        for (final side in Side.values)
          if (center.riichi[side] == true && (center.riichiConf[side] ?? 1) >= autoRiichiMinConf)
            seats.seatOf(side),
    },
  );
}

/// 론패 후보 자리가 둘 이상일 때의 방총자. 동순 후리텐 때문에 먼저 버린 패에는 론할 수 없고, 먼저 버린 사람은
/// 화료 전까지 다음 차례가 오지 않아 강 끝이 그대로 남는다. 그래서 실제 방총자는 **화료자 다음 차례부터 세어 가장 가까운
/// 자리**다(예: 순서 A→화료자→B 에서 A·B 강 끝이 같은 패면 방총자는 B). 동시 론의 [Game.ronOrder] 와 같은 계산.
Side _nearestAfterWinner(Side winner, List<Side> candidates, SeatMap seats) =>
    seats.sideOf(Game.ronOrder(seats.seatOf(winner), candidates.map(seats.seatOf)).first);

String _furitenNote(Side loser, String name) =>
    '먼저 버린 패에는 론할 수 없으니(동순 후리텐) 화료자 다음 차례에 가까운 ${loser.label}($name) 로 봤습니다';

/// 동시 론으로 고른 화료자들의 병합 결과를 규칙에 맞춰 고른다. 돌려주는 [kept] 는 방총자 다음 차례부터 가까운 순
/// (첫 사람이 본장·공탁을 가져가고, 머리치기면 혼자 남는다). [loser] 는 화료자들의 병합이 찾은 방총자(처음 찾은 것).
/// 쯔모로 읽힌 손패가 있으면 동시 화료가 아니므로 첫 것만 남긴다.
({List<TableMerge> kept, int? loser, List<MergeFlag> flags}) pickRonWinners(
  List<TableMerge> merges,
  GameSettings settings,
  List<String> names,
) {
  if (merges.length <= 1) return (kept: merges, loser: merges.firstOrNull?.loser, flags: const []);
  final flags = <MergeFlag>[];
  if (merges.any((m) => m.isTsumo)) {
    flags.add(MergeFlag(MergeIssue.multiRon,
        '쯔모로 읽힌 손패가 있어 ${names[merges.first.winner]} 만 계산했습니다. 동시 론이면 판독을 고쳐 주세요'));
    return (kept: [merges.first], loser: merges.first.loser, flags: flags);
  }
  final losers = {for (final m in merges) ?m.loser};
  final loser = merges.map((m) => m.loser).nonNulls.firstOrNull;
  if (losers.length > 1) {
    flags.add(MergeFlag(MergeIssue.multiRon,
        '화료자마다 방총자가 다르게 읽혔습니다(${losers.map((s) => names[s]).join('·')}). ${names[loser!]} 로 봤습니다'));
  }
  final byWinner = {for (final m in merges) m.winner: m};
  final order = loser == null ? [for (final m in merges) m.winner] : Game.ronOrder(loser, byWinner.keys);
  final kept = [for (final w in order.take(settings.maxRonWinners)) byWinner[w]!];
  final dropped = order.skip(settings.maxRonWinners).toList();
  if (dropped.isNotEmpty) {
    flags.add(MergeFlag(
      MergeIssue.multiRon,
      settings.multiRon == GameSettings.multiRonHeadBump
          ? '머리치기: 방총자에게서 가까운 ${names[kept.first.winner]} 만 인정합니다'
          : '동시 론은 ${settings.maxRonWinners}명까지라 ${dropped.map((s) => names[s]).join('·')} 은(는) 뺐습니다',
    ));
  }
  return (kept: kept, loser: loser, flags: flags);
}
