/// 사진 판독([HandReading]·[CenterReading])과 대국 기록([Game])을 합쳐 계산 입력을 만든다. 순수 Dart.
///
/// 규칙(docs/table_reading_design.md "merge 규칙"):
/// 1. 화료자는 호출 쪽이 정해 [winnerSide] 로 넘긴다(눕힌 자리 하나면 자동, 둘 이상이면 물음).
/// 2. 자풍·장풍·본장은 기록에서. 리치는 사진·기록 중 하나라도 true 면 true, 어긋나면 플래그.
///    단, 울린 손패(안깡 제외)는 리치가 불가능하므로 사진·기록의 리치를 버리고 플래그만 남긴다.
///    유국으로 남은 리치봉([Game.carriedStickSeats])은 이번 판 리치의 증거가 아니다 — 그 자리는 강에 눕힌 패가 있는지로 정하고,
///    그것도 모르면 리치로 치지 않고 확인을 묻는다(추적이 봉 변화를 봤으면 리치로 보고 확인).
/// 3. 도라 표시패는 사진에서. 뒷도라 표시패도 구분하지 않고 도라 표시패로 센다(리치 화료면 점수가 같다).
/// 4. 화료패가 어떤 강의 마지막 버림패와 같으면 론(그 자리가 방총자), 없으면 쯔모, 둘 이상이면 론 + 방총자 플래그.
///    화료패가 없고 손패가 한 장 모자라면, 다른 자리 강 끝 패 중 화료가 되는 패를 화료패로 넣고 론(그 자리가 방총자).
///    화료되는 강 끝이 없으면 대기패로 정한다(2026-11-01 사용자 제안): 하나면 그 패가 화료패(강을 다 읽었으면 쯔모,
///    못 읽은 자리가 하나면 그 자리가 론, 둘 이상이면 론/쯔모를 묻는다), 여럿이면 [TableMerge.winCandidates] 로 고르게 하고,
///    없으면 손패를 잘못 읽은 것이니 판독 수정으로.
///    14장을 읽었는데 화료패 표시가 없으면 손패 마지막 장을 화료패로 보고 플래그.
/// 5. 장수가 안 맞으면 [TableMerge.hand] 는 null — 바로 판독 수정으로.
/// 6. 확신도 낮은 패는 [TableMerge.uncertain] 로.
/// 7. 사진에서 리치(횡치·리치봉)가 보인 자리는 [TableMerge.photoRiichiSeats] 로. 화료 기록 때 리치봉 자동 반영에 쓴다.
library;

import '../engine/calculator.dart' show Hand, Meld, Situation, Tiles, calculate, redTilesOf;
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

  /// 도라 표시패를 그 판의 왕패 상자도, 리치 화료자 손패 옆도 아닌 곳(선 기준 구역·가운데 칸 예비)에서 읽었다.
  /// 리치가 아니면 도라는 왕패에 남는다(사용자 관찰) — 그 밖에서 읽은 것은 격자 선에 잘려 일부만 읽혔을 수 있어
  /// 자동 반영하지 않는다(2026-10-29 사용자 결정: 바깥 띠 구조 앱 흐름 D 4회가 도라 일부만 읽힌 채 자동 반영).
  doraFallback,

  /// 게임 중 추적이 화료자의 리치봉을 그 자리 첫 버림에서 봤다(전체 4장 이하·가져감 없음) → 더블 리치로 계산.
  /// 추정이라 자동 반영하지 않고 확인을 받는다(결과 화면 상황 칩으로 바로 고칠 수 있다). 2026-10-29.
  doubleRiichiTracked,

  /// 게임 중 추적이 화료자가 리치 뒤 아직 버리지 않았고 아무도 울지 않았다고 봤다 → 일발로 계산.
  /// 버림을 놓쳤을 수 있는 추정이라 자동 반영하지 않고 확인을 받는다(결과 화면 "일발" 칩으로 고침). 2026-10-29.
  ippatsuTracked,

  /// 전판 유국으로 남은 리치봉 때문에 이번 판 리치를 정할 수 없다(강의 눕힌 패를 몰랐거나, 주인을 모르는 공탁).
  /// 자동 반영하지 않고 확인을 받는다(결과 화면 "리치" 칩, "대국에 반영" 시트의 리치봉 칩). 2026-10-30 사용자 지적.
  riichiCarried,

  /// 봉 주인의 이번 판 리치를 강의 눕힌 패로 정했다(알려 주기만 한다, 자동 반영함). 2026-10-30 사용자 결정.
  riichiFromRiver,
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

  /// 손패가 한 장 모자라고 화료패를 정하지 못했을 때 가능한 화료패(둘 이상). 하나를 골라 [HandReading.withWinTile] 로 다시 병합한다.
  final List<int> winCandidates;

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
    this.winCandidates = const [],
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
/// 손패로 화료할 수 있는 패. 손패·울기·[alsoSeen](사진에 보인 표시패)에 4장 다 보이는 패는 뺀다(사용자 제안 2026-11-01, metrics 표 1-7).
List<int> _waitTiles(List<MergedTile> closed, List<Meld> melds, {Iterable<int> alsoSeen = const []}) {
  final seen = <int, int>{};
  for (final t in [for (final c in closed) c.tile, for (final m in melds) ...m.tiles, ...alsoSeen]) {
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
  /// 게임 중 추적이 본 "가장 최근에 버린 자리"([RiverTracker.lastDiscard]). 강 끝 패가 여럿 화료될 때 이 자리를 방총자로 고른다.
  Side? loserHint,
  /// 추적이 화료자의 리치를 첫 순 리치로 봤다([TableReading.trackedDoubleRiichi] 에 화료자 자리가 있음).
  bool doubleRiichiHint = false,
  /// 추적이 화료자를 일발 후보로 봤다([TableReading.trackedIppatsu] 에 화료자 자리가 있음).
  bool ippatsuHint = false,
  /// 추적이 이번 판에 리치봉이 새로 놓인 것을 본 자리([TableReading.trackedRiichi]).
  Set<Side> trackedRiichi = const {},
  /// 봉이 남은 자리의 강에 눕힌 패가 있는지([TableReading.riverSideways]). 없는 자리는 모름.
  Map<Side, bool?> riverSideways = const {},
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
  var ronTsumoOpen = false; // 대기패로 화료패를 정했는데 못 읽은 강이 둘 이상이라 론/쯔모를 모름
  var winCandidates = const <int>[];
  final oneShort = win == null && closed.length == expected - 1;
  if (oneShort) {
    // 론한 패는 버린 사람 강 끝에 그대로 있다. 손패에 더해 화료가 되는 강 끝 패를 찾는다.
    final found = <Side>[
      if (center != null)
        for (final s in Side.values)
          if (canDealIn(s) && _completes(closed, melds, center.lastDiscardAt(s))) s,
    ];
    if (found.isNotEmpty) {
      center!;
      final hint = loserHint;
      final hinted = found.length > 1 && hint != null && found.contains(hint);
      ronFrom = found.length == 1
          ? found.single
          : (hint != null && hinted)
              ? hint
              : _nearestAfterWinner(winnerSide, found, seats);
      win = center.lastDiscardAt(ronFrom)!;
      final loserSeat = seats.seatOf(ronFrom);
      flags.add(MergeFlag(
        found.length == 1 ? MergeIssue.winFromDiscard : MergeIssue.loserAmbiguous,
        found.length == 1
            ? '손패가 ${expected - 1}장이라 ${ronFrom.label}(${game.names[loserSeat]}) 강 끝 ${Tiles.name(win.tile)} 로 론으로 봤습니다'
            : '${found.map((s) => s.label).join('·')} 강 끝 패가 모두 화료됩니다. '
                '${hinted ? _trackedNote(ronFrom, game.names[loserSeat]) : _furitenNote(ronFrom, game.names[loserSeat])}',
      ));
    } else {
      // 화료되는 강 끝이 없다. 쯔모였거나, 강 끝을 못 읽은 자리가 쏘였을 수 있다(판독이 가끔 "강 없음" 으로 답한다).
      // 화료패를 다시 읽지 않고 손패의 대기패로 정한다. 추정이라 자동 반영은 막는다(infoOnlyIssues 에 없음).
      final unread = [
        for (final s in Side.values)
          if (canDealIn(s) && center?.lastDiscardAt(s) == null) s,
      ];
      final waits = _waitTiles(closed, melds, alsoSeen: [
        if (center != null) ...[...center.doraIndicators, ...center.uraIndicators, ...center.handSideIndicators].map((t) => t.tile),
      ]);
      if (waits.length == 1) {
        final t = waits.single;
        // 수패 5 는 적도라인지 사진으로 못 봤으니 확인을 묻는다(확신도를 낮춰 노란 테두리).
        final maybeRed = Tiles.suit(t) < 3 && Tiles.number(t) == 5;
        win = ReadTile(t, conf: maybeRed ? 0.5 : 0.9);
        if (center != null && unread.length == 1) {
          ronFrom = unread.single;
          flags.add(MergeFlag(
            MergeIssue.winFromWait,
            '${ronFrom.label}(${game.names[seats.seatOf(ronFrom)]}) 강 끝을 읽지 못했지만 대기패가 ${Tiles.name(t)} 하나라 '
            '그 자리가 ${Tiles.name(t)} 로 쏘였다고 봤습니다',
          ));
        } else if (center != null && unread.isEmpty) {
          flags.add(MergeFlag(
            MergeIssue.winFromWait,
            '대기패가 ${Tiles.name(t)} 하나이고 강 끝에 없어 ${Tiles.name(t)} 쯔모로 봤습니다',
          ));
        } else {
          ronTsumoOpen = center != null;
          flags.add(MergeFlag(
            MergeIssue.winFromWait,
            '대기패가 ${Tiles.name(t)} 하나라 화료패로 봤습니다. 론이면 방총자를 골라 주세요',
          ));
        }
      } else if (waits.isNotEmpty) {
        winCandidates = waits;
        flags.add(MergeFlag(
          MergeIssue.winTileUnknown,
          '화료패를 찾지 못했습니다. 손패로 가능한 패는 ${waits.map(Tiles.name).join('·')} ${waits.length}개입니다',
        ));
      } else {
        flags.add(const MergeFlag(MergeIssue.winTileUnknown, '이 손패로 화료할 수 있는 패가 없습니다. 손패를 잘못 읽었는지 확인하세요'));
      }
    }
  }
  if (win != null) {
    closed.add(MergedTile(win.tile, red: win.red, conf: win.conf));
  } else if (closed.isNotEmpty && !oneShort) {
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
  // 유국으로 남은 봉은 그 자리 홈에 그대로 있어, 사진에 보여도 이번 판 리치라는 증거가 아니다.
  final carried = game.carriedStickSeats;
  final recordRiichi = game.riichiSeats.contains(winner);
  // 그 자리는 강에 눕힌 패(리치 선언패)로 정한다. 이번 판 패만 강에 있으니 전판과 섞이지 않는다.
  final winnerStick = center?.riichiAt(winnerSide) == true && carried.contains(winner) && !recordRiichi;
  final winnerSideways = riverSideways[winnerSide];
  final staleStick = winnerStick && (winnerSideways == false || (winnerSideways == null && !trackedRiichi.contains(winnerSide)));
  final photoRiichi = staleStick ? false : center?.riichiAt(winnerSide);
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

  // 더블리치: 추적 힌트가 있고 리치가 살아 있을 때만. 추정이라 확인 플래그.
  final doubleRiichi = riichi && doubleRiichiHint;
  if (doubleRiichi) {
    flags.add(const MergeFlag(
      MergeIssue.doubleRiichiTracked,
      '추적이 첫 버림에서 리치봉을 봤습니다 — 더블 리치로 계산했습니다. 아니면 결과 화면의 "리치" 칩을 누르세요',
    ));
  }

  // 일발: 리치가 살아 있고 추적이 리치 뒤 버림·울기를 못 봤을 때만. 추정이라 확인 플래그.
  final ippatsu = riichi && ippatsuHint;
  if (ippatsu) {
    flags.add(const MergeFlag(
      MergeIssue.ippatsuTracked,
      '추적이 리치 뒤 화료자의 버림·울기를 못 봤습니다 — 일발로 계산했습니다. 아니면 결과 화면의 "일발" 칩을 누르세요',
    ));
  }

  // 론/쯔모·방총자
  var isTsumo = false;
  int? loser;
  if (ronFrom != null) {
    loser = seats.seatOf(ronFrom);
  } else if (center == null) {
    flags.add(const MergeFlag(MergeIssue.ronTsumoUnknown, '중앙을 읽지 못해 론/쯔모를 정하지 못했습니다'));
  } else if (ronTsumoOpen) {
    flags.add(const MergeFlag(MergeIssue.ronTsumoUnknown, '강 끝을 둘 이상 읽지 못해 론/쯔모를 정하지 못했습니다'));
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
      final hint = loserHint;
      final hinted = hint != null && matches.contains(hint);
      final s = (hint != null && hinted) ? hint : _nearestAfterWinner(winnerSide, matches, seats);
      loser = seats.seatOf(s);
      flags.add(MergeFlag(
          MergeIssue.loserAmbiguous,
          '화료패 ${Tiles.name(win.tile)} 이(가) ${matches.map((s) => s.label).join('·')} 강 끝에 모두 있습니다. '
          '${hinted ? _trackedNote(s, game.names[loser]) : _furitenNote(s, game.names[loser])}'));
    }
  }

  // 봉 주인의 화료: 리치 없이 역이 없으면 리치였을 수밖에 없다. 역이 있으면 리치 없이 계산하고, 눕힌 패가 없다고 봤으면
  // 그대로 반영, 몰랐으면 확인을 묻는다.
  if (staleStick && !openHand) {
    riichi = !_winsWithoutRiichi(closed, melds, win, isTsumo, game.seatWindOf(winner), game.roundWindTile);
    if (winnerSideways == false && !riichi) {
      flags.add(const MergeFlag(
        MergeIssue.riichiFromRiver,
        '화료자 강에 눕힌 패가 없어 리치봉을 전판에 남은 것으로 보고 리치 없이 계산했습니다. 리치했으면 "리치" 칩을 누르세요',
      ));
    } else {
      flags.add(MergeFlag(
        MergeIssue.riichiCarried,
        riichi
            ? '남은 리치봉이 전판 것일 수 있지만 리치 없이는 역이 없어 리치로 계산했습니다'
            : '화료자의 리치봉이 전판 유국에서 남은 것일 수 있어 리치 없이 계산했습니다. 이번 판에 리치했으면 "리치" 칩을 누르세요',
      ));
    }
  } else if (winnerStick && winnerSideways == true && !openHand) {
    flags.add(const MergeFlag(MergeIssue.riichiFromRiver, '전판 리치봉이 남아 있지만 화료자 강에 눕힌 패가 있어 이번 판 리치로 계산했습니다'));
  }
  // 봉이 있던 자리에서 추적이 변화를 봤는데 강으로도 모른다: 새 봉일 수도, 봉을 건드린 것일 수도 있다.
  final carriedTracked = [
    for (final s in trackedRiichi)
      if (carried.contains(seats.seatOf(s)) && !game.riichiSeats.contains(seats.seatOf(s)) && riverSideways[s] == null)
        game.names[seats.seatOf(s)],
  ];
  if (carriedTracked.isNotEmpty) {
    flags.add(MergeFlag(MergeIssue.riichiCarried,
        '${carriedTracked.join('·')}: 전판 리치봉이 남아 있던 자리에서 변화를 봐서 이번 판 리치로 봤습니다. 아니면 고쳐 주세요'));
  }
  // 공탁인데 주인을 모르는 봉(중간부터 기록 등): 사진에 보인 봉이 그것일 수 있다.
  final photoUnrecorded = [
    if (center != null)
      for (final side in Side.values)
        if (center.riichiAt(side) &&
            !game.riichiSeats.contains(seats.seatOf(side)) &&
            !carried.contains(seats.seatOf(side)) &&
            !trackedRiichi.contains(side))
          game.names[seats.seatOf(side)],
  ];
  if (game.unknownSticks > 0 && photoUnrecorded.isNotEmpty) {
    flags.add(MergeFlag(MergeIssue.riichiCarried,
        '공탁 ${game.unknownSticks}개는 누구 봉인지 기록에 없어 ${photoUnrecorded.join('·')}의 리치봉이 전판 것일 수 있습니다. 확인하세요'));
  }

  // 도라·뒷도라: 사진에서 어느 쪽이 뒷도라인지 가르기 어렵고(왕패 짝의 위아래), 리치 화료면 둘 다 1판씩이라
  // 점수가 같다. 보인 앞면 표시패를 모두 도라 표시패로 센다.
  // 어디서 읽을지: 매장에서는 리치 화료면 화료자가 도라·뒷도라 표시패를 자기 손패 옆으로 가져가고, 리치가 아니면
  // 왕패에 그대로 둔다(2026-10-26 사용자 관찰). 그래서 리치면 손패 옆을, 아니면 가운데를 먼저 쓰고 비었을 때만 다른 쪽.
  // 깡이 있으면 도라 2장·뒷도라 1장처럼 홀수일 수 있어 장수 짝 검사는 하지 않는다(사용자 결정).
  final centerIndicators = [...?center?.doraIndicators, ...?center?.uraIndicators];
  final handSide = center?.handSideIndicators ?? const <ReadTile>[];
  final fromHandSide = riichi ? handSide.isNotEmpty : centerIndicators.isEmpty && handSide.isNotEmpty;
  final indicators = fromHandSide ? handSide : centerIndicators;
  final from = center?.doraFrom;
  if (!fromHandSide && (from == DoraFrom.center || from == DoraFrom.dealerZone)) {
    flags.add(MergeFlag(
        MergeIssue.doraFallback,
        '도라 표시패(${indicators.map((t) => t.code).join(' ')})를 왕패 상자 없이 '
        '${from == DoraFrom.center ? '가운데 칸' : '선 기준 구역'}에서 읽었습니다. 빠진 표시패가 없는지 확인하세요'));
  }
  final situation = Situation(
    isTsumo: isTsumo,
    seatWind: game.seatWindOf(winner),
    roundWind: game.roundWindTile,
    riichi: riichi && !doubleRiichi,
    doubleRiichi: doubleRiichi,
    ippatsu: ippatsu,
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
        redTiles: redTilesOf([for (final t in closed) if (t.red) t.tile], melds, meldRed),
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
    winCandidates: winCandidates,
    photoRiichiSeats: {
      if (center != null)
        for (final side in Side.values)
          if (center.riichi[side] == true &&
              (center.riichiConf[side] ?? 1) >= autoRiichiMinConf &&
              // 유국으로 남은 봉에 1000점을 또 걷지 않는다. 그 자리의 새 리치는 강의 눕힌 패로 정하고, 모르면 추적을 따른다.
              (!carried.contains(seats.seatOf(side)) || (riverSideways[side] ?? trackedRiichi.contains(side))))
            seats.seatOf(side),
    },
  );
}

/// 리치 없이도 이 손패가 역이 있는 화료인가. 장수가 안 맞아 모르면 true(리치를 지어내지 않는다).
bool _winsWithoutRiichi(List<MergedTile> closed, List<Meld> melds, ReadTile? win, bool isTsumo, int seatWind, int roundWind) {
  if (win == null) return true;
  try {
    return calculate(
      Hand(closedTiles: [for (final t in closed) t.tile], melds: melds, winTile: win.tile),
      Situation(isTsumo: isTsumo, seatWind: seatWind, roundWind: roundWind),
    ).isValid;
  } on ArgumentError {
    return true;
  }
}

/// 론패 후보 자리가 둘 이상일 때의 방총자. 동순 후리텐 때문에 먼저 버린 패에는 론할 수 없고, 먼저 버린 사람은
/// 화료 전까지 다음 차례가 오지 않아 강 끝이 그대로 남는다. 그래서 실제 방총자는 **화료자 다음 차례부터 세어 가장 가까운
/// 자리**다(예: 순서 A→화료자→B 에서 A·B 강 끝이 같은 패면 방총자는 B). 동시 론의 [Game.ronOrder] 와 같은 계산.
Side _nearestAfterWinner(Side winner, List<Side> candidates, SeatMap seats) =>
    seats.sideOf(Game.ronOrder(seats.seatOf(winner), candidates.map(seats.seatOf)).first);

String _trackedNote(Side loser, String name) => '게임 중 마지막으로 버린 자리가 ${loser.label}($name)라 그쪽으로 봤습니다';

String _furitenNote(Side loser, String name) =>
    '먼저 버린 패에는 론할 수 없으니(동순 후리텐) 화료자 다음 차례에 가까운 ${loser.label}($name) 로 봤습니다';

/// 눕힌 손패가 둘일 때 묻지 않고 동시 론으로 볼 수 있나(2026-10-28, 사용자 요청). 둘 다 론으로 계산돼([valid] 가 역 있는
/// 화료인지 확인), 방총자가 같은 한 사람(화료자가 아닌)이고 화료패가 같아야 한다. 하나라도 어긋나면 false → 지금처럼 묻는다.
/// 같은 패를 기다리다 론하지 않고 펼친 손패(견逃し·후리텐)는 가려내지 못하므로 결과 화면에 "한 명만 론" 되돌리기가 있다.
bool clearDoubleRon(List<TableMerge> merges, bool Function(TableMerge m) valid) {
  if (merges.length != 2) return false;
  final winners = {for (final m in merges) m.winner};
  final loser = merges.first.loser;
  if (winners.length != 2 || loser == null || winners.contains(loser)) return false;
  for (final m in merges) {
    if (m.hand == null || m.isTsumo || m.loser != loser || m.closed.isEmpty || !valid(m)) return false;
  }
  return merges.first.closed.last.tile == merges.last.closed.last.tile;
}

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
