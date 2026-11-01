/// 자리 판독으로 손패를 못 정했을 때 넓은 구역 판독(`/v2/seatwide`)으로 채우는 규칙. 순수 Dart.
///
/// 자리 크롭은 떼어 둔 화료패·모서리 백 3장을 놓친다. 넓은 구역은 패를 더 찾지만 표시패도 함께 찾으므로 장수·패 모양으로 고른다
/// (2026-11-01, 사용자 규칙 "탁자 위 표시패는 리치의 도라 + 뒷도라라 2장 이상", metrics 표 1-6·1-7, 개발 세트로 정한 값).
/// - 자리 판독이 14장 화료형이거나, 13장 텐파이이고 강 끝 패로 화료되면 부르지 않는다.
/// - 13장 텐파이: 펠트 위 외톨이 낱장이 하나이고 더해서 화료형이면 그 패가 떼어 둔 화료패. 아니면 그대로(화료패 후보 창으로).
/// - 그 밖: 넓은 구역의 손패 줄 + 외톨이 → 낱장 조합 중 화료형이 하나뿐인 것 → 낱장 없이 텐파이 → 낱장 조합 중 텐파이가 하나뿐인 것
///   순으로 받고, 다 아니면 자리 판독 그대로. 낱장은 표시패가 섞여 있어 조합이 여럿이면 고르지 않는다.
library;

import '../engine/calculator.dart' show Tiles;
import 'observation.dart';
import 'table_reading.dart';

/// `/v2/seatwide` 응답. [row] 는 뒷면으로 읽은 칸이 있으면 null.
class WideRead {
  final List<ReadTile>? row;
  final List<ReadTile> lone;
  final List<ReadTile> grouped;

  /// 줄보다 위(강 높이)에 둘만 붙어 놓인 패 — 리치 화료자가 탁자에 내놓은 도라·뒷도라 표시패 짝(서버 `pair`). [grouped] 에도 들어 있다.
  final List<ReadTile> pairs;
  final List<ObservedMeld> melds;
  final bool unanimous;
  const WideRead({this.row, this.lone = const [], this.grouped = const [], this.pairs = const [], this.melds = const [], this.unanimous = false});

  factory WideRead.fromJson(Map<String, dynamic> j) {
    final rawRow = (j['row'] as List<dynamic>?) ?? const [];
    final row = [for (final t in rawRow) if (t is Map<String, dynamic>) ?ReadTile.fromJson(t)];
    final lone = <ReadTile>[], grouped = <ReadTile>[], pairs = <ReadTile>[];
    for (final s in (j['singles'] as List<dynamic>?) ?? const []) {
      if (s is! Map<String, dynamic>) continue;
      final t = ReadTile.fromJson(s);
      if (t == null) continue;
      (s['lone'] == true ? lone : grouped).add(t);
      if (s['pair'] == true) pairs.add(t);
    }
    return WideRead(
      row: rawRow.isNotEmpty && row.length == rawRow.length ? row : null,
      lone: lone,
      grouped: grouped,
      pairs: pairs,
      melds: [
        for (final m in (j['melds'] as List<dynamic>?) ?? const [])
          if (m is Map<String, dynamic>) ?ObservedMeld.fromJson(m),
      ],
      unanimous: (j['agreement'] as Map<String, dynamic>?)?['unanimous'] == true,
    );
  }
}

bool _melds(List<int> counts, int from) {
  var i = from;
  while (i < 34 && counts[i] == 0) {
    i++;
  }
  if (i == 34) return true;
  if (counts[i] >= 3) {
    counts[i] -= 3;
    final ok = _melds(counts, i);
    counts[i] += 3;
    if (ok) return true;
  }
  if (i < 27 && Tiles.number(i) <= 7 && counts[i + 1] > 0 && counts[i + 2] > 0) {
    counts[i]--;
    counts[i + 1]--;
    counts[i + 2]--;
    final ok = _melds(counts, i);
    counts[i]++;
    counts[i + 1]++;
    counts[i + 2]++;
    return ok;
  }
  return false;
}

/// 울기를 뺀 손패 [closed] 가 화료형인가(일반형·치또이·국사).
bool closedWins(List<int> closed) {
  if (closed.length % 3 != 2) return false;
  final counts = List<int>.filled(34, 0);
  for (final t in closed) {
    counts[t]++;
  }
  if (counts.any((c) => c > 4)) return false;
  if (closed.length == 14) {
    if (counts.where((c) => c == 2).length == 7) return true;
    const orphans = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];
    if (orphans.every((t) => counts[t] >= 1) && orphans.fold(0, (a, t) => a + counts[t]) == 14) return true;
  }
  for (var p = 0; p < 34; p++) {
    if (counts[p] < 2) continue;
    counts[p] -= 2;
    final ok = _melds(counts, 0);
    counts[p] += 2;
    if (ok) return true;
  }
  return false;
}

/// [closed] 가 한 장으로 화료되는가(텐파이).
bool closedTenpai(List<int> closed) {
  if (closed.length % 3 != 1) return false;
  for (var t = 0; t < 34; t++) {
    if (closedWins([...closed, t])) return true;
  }
  return false;
}

int _meldCount(List<ObservedMeld> melds) => melds.where((m) => m.consistent).length;

List<int> _closed(SeatV2 s) => [for (final t in s.tiles) t.tile, if (s.separate case final t?) t.tile];

/// 자리 판독의 울기가 미덥지 않나: 울기가 있는데 여러 번 읽은 답이 엇갈렸거나 확신도가 낮다. 흩어진 손패를 울기로 묶으면 모양 검사를
/// 통과해 틀린 계산이 되므로(10-31 매장 175951, 세 번 읽어 한 번만 같음·울기 확신도 0) 넓은 판독의 줄과 대조한다([applyScattered]).
bool meldsDoubtful(SeatV2 seat) =>
    seat.melds.isNotEmpty && (!(seat.agreement?.unanimous ?? true) || seat.melds.any((m) => !m.consistent || m.conf < 0.7));

/// 흩어진 손패를 울기로 묶은 자리 판독을 넓은 판독의 손패 줄로 바로잡는다. 넓은 줄이 울기 없이 자리 판독의 손패·울기 패를 모두 담은
/// 한 줄이고 그 줄이 화료형(14)·텐파이(13)이면 그 줄을 손패로(울기 없음). 아니면 null(그대로).
({SeatV2 seat, String note})? applyScattered(SeatV2 seat, WideRead wide) {
  final row = wide.row;
  if (row == null || wide.melds.isNotEmpty || seat.melds.isEmpty) return null;
  final closed = _closed(seat);
  final total = closed.length + 3 * seat.melds.length;
  if (row.length != total || total != 13 && total != 14) return null;
  final left = [for (final t in row) t.tile];
  for (final t in [...closed, for (final m in seat.melds) for (final x in m.tiles) x.tile]) {
    if (!left.remove(t)) return null;
  }
  final ids = [for (final t in row) t.tile];
  if (!(total == 14 ? closedWins(ids) : closedTenpai(ids))) return null;
  return (
    seat: (
      faceUp: true,
      tiles: row,
      separate: null,
      melds: const <ObservedMeld>[],
      loose: seat.loose,
      agreement: (reads: 3, agree: wide.unanimous ? 3 : 0, unanimous: wide.unanimous, alternatives: const <String>[]),
    ),
    note: '울기로 읽힌 ${seat.melds.length}묶음이 넓은 구역에선 손패 한 줄이라 손패 ${row.length}장으로 봤습니다. 확인하세요',
  );
}

/// 자리 판독만으로 부족해 넓은 구역을 읽어야 하나. [riverEnds] 는 다른 자리 강 끝(못 읽었으면 null).
bool seatNeedsWide(SeatV2 seat, Iterable<ReadTile?> riverEnds) {
  final closed = _closed(seat);
  final total = closed.length + 3 * _meldCount(seat.melds);
  if (total == 14 && closedWins(closed)) return false;
  if (total == 13 && closedTenpai(closed)) {
    return !riverEnds.any((t) => t != null && closedWins([...closed, t.tile]));
  }
  return true;
}

/// [row] 가 [closed] 에 정확히 한 장을 더한 것이면 그 한 장, 아니면 null.
ReadTile? _rowExtra(List<ReadTile>? row, List<int> closed) {
  if (row == null || row.length != closed.length + 1) return null;
  final left = [...closed];
  ReadTile? extra;
  for (final t in row) {
    if (!left.remove(t.tile)) {
      if (extra != null) return null;
      extra = t;
    }
  }
  return extra;
}

/// 넓은 구역 판독을 자리 판독에 합친다. 바꾸지 않으면 [note] 가 null. [meldsKnown] 이면 울기는 자리 판독(추적) 것을 쓴다.
({SeatV2 seat, String? note}) applyWide(SeatV2 seat, WideRead wide, {bool meldsKnown = false}) {
  // 낱장을 더해 14장이면 마지막 낱장이 떼어 둔 패. [keepLast] 는 13장이라(론 패는 강에) 떼어 둔 패가 없다.
  SeatV2 replaced(List<ReadTile> hand, List<ObservedMeld> melds, List<ReadTile> used,
      {bool sameAgreement = false, bool keepLast = false}) {
    final left = [...wide.lone, ...wide.grouped];
    for (final u in used) {
      left.remove(u);
    }
    final split = used.isNotEmpty && !keepLast;
    return (
      faceUp: true,
      tiles: split ? hand.sublist(0, hand.length - 1) : hand,
      separate: split ? hand.last : null,
      melds: melds,
      loose: left.isNotEmpty ? left : seat.loose,
      agreement: sameAgreement
          ? seat.agreement
          : (reads: 3, agree: wide.unanimous ? 3 : 0, unanimous: wide.unanimous, alternatives: const <String>[]),
    );
  }

  final closed = _closed(seat);
  final total = closed.length + 3 * _meldCount(seat.melds);
  if (total == 13 && closedTenpai(closed)) {
    // 떼어 둔 패가 줄 가까이 있으면 넓은 구역은 줄에 붙여 읽는다(171505 3m). 넓은 줄이 자리 판독 + 정확히 한 장이면 그 패가 후보다.
    final extra = _rowExtra(wide.row, closed);
    final candidates = [...wide.lone, ?extra];
    final seen = <int>{};
    final winners = [
      for (final t in candidates)
        if (seen.add(t.tile) && closedWins([...closed, t.tile])) t,
    ];
    if (winners.length != 1) return (seat: seat, note: null);
    final lone = winners.single;
    return (
      seat: replaced([...seat.tiles, ?seat.separate, lone], seat.melds, [lone], sameAgreement: true),
      note: '손패 줄 밖 낱장 ${lone.code} 를 떼어 둔 화료패로 봤습니다. 확인하세요',
    );
  }

  final row = wide.row;
  if (row == null) return (seat: seat, note: null);
  final melds = meldsKnown ? seat.melds : [for (final m in wide.melds) if (m.consistent) m];
  final need = 14 - 3 * melds.length;
  List<int> ids(List<ReadTile> ts) => [for (final t in ts) t.tile];
  bool ok(List<ReadTile> ts) =>
      (ts.length == need && closedWins(ids(ts))) || (ts.length == need - 1 && closedTenpai(ids(ts)));
  const note = '자리 판독으로 손패를 못 정해 넓은 구역으로 다시 읽었습니다. 확인하세요';

  if (wide.lone.isNotEmpty && ok([...row, ...wide.lone])) {
    final all = [...row, ...wide.lone];
    return (seat: replaced(all, melds, wide.lone, keepLast: all.length == need - 1), note: note);
  }
  final singles = [...wide.lone, ...wide.grouped];
  // 낱장 [size] 장을 더해 [shape] 가 되는 패 조합. 같은 패로 된 조합은 하나로 친다.
  Map<String, List<ReadTile>> combos(int size, bool Function(List<int>) shape) {
    final found = <String, List<ReadTile>>{};
    void pick(int from, List<ReadTile> chosen) {
      if (chosen.length == size) {
        if (shape(ids([...row, ...chosen]))) found[(ids(chosen)..sort()).join(',')] = [...chosen];
        return;
      }
      for (var i = from; i < singles.length; i++) {
        pick(i + 1, [...chosen, singles[i]]);
      }
    }

    if (size >= 1 && size <= singles.length && singles.length <= 12) pick(0, const []);
    return found;
  }

  // 화료형 → 낱장 없이 텐파이 → 낱장을 더한 텐파이. 조합이 여럿이면 고르지 않는다.
  final wins = combos(need - row.length, closedWins);
  if (wins.length > 1) return (seat: seat, note: null);
  if (wins.length == 1) {
    final used = wins.values.single;
    return (seat: replaced([...row, ...used], melds, used), note: note);
  }
  if (ok(row)) return (seat: replaced(row, melds, const []), note: note);
  final tenpai = combos(need - 1 - row.length, closedTenpai);
  if (tenpai.length == 1) {
    final used = tenpai.values.single;
    return (seat: replaced([...row, ...used], melds, used, keepLast: true), note: note);
  }
  return (seat: seat, note: null);
}
