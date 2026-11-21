/// 차례별 읽기(끝 줄 순서)로 hero 의 매 순 손패를 끝 손패에서 거꾸로 복원한다(`docs/paifu_hand_restore_api_1121.md` 3-5). 순수 Dart.
///
/// `experiments/paifu_frames/handtrack/rebuild_opus.py` `--full` 을 옮긴 것:
/// - 끝 줄 = 화료 결과 손패(화료패 빼고 — 쯔모면 화료패는 마지막 뽑기). 차례마다 거꾸로 [backRow]: 끝 줄 순서의 숫자 i = 시작 줄 i번,
///   D = 뽑은 패, 빈 번호 하나 = 버린 패(강의 패). D 도 빈 번호도 없으면 쯔모기리(뽑은 패 = 버린 패).
/// - 리치 뒤 차례 = 규칙(순서 그대로, 쯔모기리). 퐁 · 치 바로 뒤 버림 = 울기로 나간 패 + 버린 패를 끝 손패 정렬이 놓을 자리에
///   끼워 짐작([backCall], 묶음만 확실 — 사건에 `guess` 표시).
/// - 읽기가 없거나(답 없음 · 한도) 모순이면 그 차례부터 앞은 손패 없음으로 두고 까닭을 메모에 남긴다.
library;

import '../../engine/tile.dart';
import '../paifu.dart';
import 'turn_agent.dart';
import 'turns.dart';

/// 끝 줄 + 끝 줄 순서 → (시작 줄, 뽑은 패, 쯔모기리인가). 순서가 온전하지 않으면 [FormatException].
({List<PaifuTile> before, PaifuTile drawn, bool tsumogiri}) backRow(List<PaifuTile> after, List<String> order, PaifuTile river) {
  final n = after.length;
  if (order.length != n) throw FormatException('끝 줄 순서가 $n장이 아님: $order');
  final before = List<PaifuTile?>.filled(n, null);
  PaifuTile? drawn;
  for (final (p, lab) in order.indexed) {
    if (lab == 'D') {
      if (drawn != null) throw FormatException('D 가 둘: $order');
      drawn = after[p];
    } else {
      final i = int.tryParse(lab);
      if (i == null || i < 1 || i > n || before[i - 1] != null) throw FormatException('끝 줄 순서가 온전하지 않음: $order');
      before[i - 1] = after[p];
    }
  }
  final gone = [
    for (var i = 0; i < n; i++)
      if (before[i] == null) i,
  ];
  if (gone.length == 1 && drawn != null) {
    before[gone.first] = river; // 손에서 냄: 빠진 번호 = 버린 패
    return (before: [for (final t in before) t!], drawn: drawn, tsumogiri: false);
  }
  if (gone.isEmpty && drawn == null) {
    return (before: [for (final t in before) t!], drawn: river, tsumogiri: true); // 쯔모기리
  }
  throw FormatException('끝 줄 순서가 온전하지 않음: $order');
}

/// 패 코드의 숫자(자패는 1z ~ 7z 의 숫자 — replay.py 와 같게).
int _num(int t) => t < 27 ? Tiles.number(t) : t - 26;

/// 끝 손패(자리 순서)에서 읽은 정렬: 무늬 순서 · 숫자 방향(experiments replay.sort_scheme).
class SortScheme {
  final List<int> suitOrder; // Tiles.suit 값
  final bool ascending;
  const SortScheme(this.suitOrder, this.ascending);

  factory SortScheme.of(List<PaifuTile> row) {
    final suits = <int>[];
    final nums = <int, List<int>>{};
    for (final t in row) {
      final s = Tiles.suit(t.tile);
      if (suits.isEmpty || suits.last != s) suits.add(s);
      (nums[s] ??= []).add(_num(t.tile));
    }
    var up = 0, down = 0;
    for (final v in nums.values) {
      for (var i = 0; i + 1 < v.length; i++) {
        if (v[i + 1] > v[i]) up++;
        if (v[i + 1] < v[i]) down++;
      }
    }
    final order = <int>[];
    for (final s in suits) {
      if (!order.contains(s)) order.add(s);
    }
    return SortScheme(order, up >= down);
  }

  /// 정렬 키(작을수록 왼쪽). 그 무늬가 끝 손패에 없으면 null.
  int? key(PaifuTile t) {
    final s = Tiles.suit(t.tile);
    final i = suitOrder.indexOf(s);
    if (i < 0) return null;
    final n = _num(t.tile);
    return i * 100 + (ascending ? n : -n);
  }
}

/// 울기 차례 거꾸로: 끝 줄 + 손에서 나간 패 → 그 앞 줄. 나간 패는 정렬이 놓을 자리에(키가 없으면 줄 끝에). 짐작.
List<PaifuTile> backCall(List<PaifuTile> after, List<PaifuTile> gone, SortScheme sch) {
  final row = [...after];
  for (final v in gone) {
    final k = sch.key(v);
    var pos = row.length;
    if (k != null) {
      final i = row.indexWhere((x) => sch.key(x) != null && sch.key(x)! > k);
      if (i >= 0) pos = i;
    }
    row.insert(pos, v);
  }
  return row;
}

/// 손패 줄 하나에 같은 패가 4장을 넘거나 같은 적5 가 둘이면 까닭.
String? _impossible(List<PaifuTile> row) {
  final c = <int, int>{}, red = <int, int>{};
  for (final t in row) {
    c[t.tile] = (c[t.tile] ?? 0) + 1;
    if (t.red) red[t.tile] = (red[t.tile] ?? 0) + 1;
  }
  for (final e in c.entries) {
    if (e.value > 4) return '${Tiles.name(e.key)} 이(가) ${e.value}장';
  }
  for (final e in red.entries) {
    if (e.value > 1) return '적${Tiles.name(e.key)} 이(가) ${e.value}장';
  }
  return null;
}

class RebuildResult {
  /// 복원한 패보(손패가 한 차례도 안 채워졌으면 원본 그대로 + 메모).
  final Paifu paifu;

  /// 차례마다 메모(차례 순서).
  final List<Map<String, dynamic>> memo;

  /// 손패를 채운 차례 수 · 끝까지(시작 손패까지) 채웠나.
  final int restored;
  final bool complete;

  /// 처음 멈춘 차례(뒤에서 셀 때)와 까닭.
  final int? failedTurn;
  final String? failReason;

  const RebuildResult({
    required this.paifu,
    required this.memo,
    required this.restored,
    required this.complete,
    this.failedTurn,
    this.failReason,
  });
}

/// 끝 줄 순서 고르기: hand 면 end_order(온전하지 않으면 k · j 로 지음), tsumogiri 면 1..n 순열인 end_order(줄을 바꾼 쯔모기리) 또는 그대로.
List<String>? orderOf(TurnReading r, int n) {
  final ident = [for (var i = 1; i <= n; i++) '$i'];
  final eo = r.endOrder;
  if (r.kind == 'hand') {
    if (fromOrder(eo, n) != null) return eo;
    final k = r.k, j = r.j;
    if (k == null || j == null || k < 1 || k > n || j < 1 || j > n) return null;
    return [
      for (var i = 1; i <= n; i++)
        if (i != k) '$i',
    ]..insert(j - 1, 'D');
  }
  if (r.kind == 'tsumogiri') {
    if (eo != null && eo.length == n && ({...eo}.length == n) && eo.every(ident.contains)) return eo;
    return ident;
  }
  return null;
}

/// 사건에서 울기로 손에서 나간 패(묶음 − 강에서 가져온 한 장).
List<PaifuTile>? callHandTiles(Paifu p, int callEvent) {
  final c = p.events[callEvent];
  final from = c.from;
  if (from == null) return null;
  PaifuTile? taken;
  for (var i = callEvent - 1; i >= 0; i--) {
    final e = p.events[i];
    if (e.type == PaifuEventType.discard && e.seat == from) {
      taken = e.tile;
      break;
    }
  }
  if (taken == null) return null;
  final rest = [...c.callTiles];
  var i = rest.indexWhere((t) => t == taken);
  if (i < 0) i = rest.indexWhere((t) => t.tile == taken!.tile);
  if (i < 0) return null;
  rest.removeAt(i);
  return rest;
}

/// [readings] = 차례 번호(RestoreTurn.index) → 읽기. [source] = `hand_source` 에 적을 값.
RebuildResult rebuildHands(Paifu p, List<RestoreTurn> turns, Map<int, TurnReading> readings, {String source = 'claude_api'}) {
  final end = endRowOf(p);
  final memo = [
    for (final t in turns)
      <String, dynamic>{'turn': t.index + 1, 'event': t.discardEvent, 'src': 'none'},
  ];
  if (end == null || turns.isEmpty) {
    return RebuildResult(paifu: p, memo: memo, restored: 0, complete: false, failReason: end == null ? '끝 손패가 없습니다' : 'hero 버림이 없습니다');
  }
  final events = [...p.events];
  final newDraws = <int, PaifuEvent>{}; // 버림 사건 번호 → 그 앞에 끼울 뽑기
  final sch = SortScheme.of(end);
  var row = [...end];
  // 쯔모 화료: 마지막 hero 버림 뒤의 뽑기 = 화료패, 그때 줄 = 끝 줄. 사건이 있으면 채우고 없으면 끝에 붙인다.
  final r = p.result!;
  PaifuEvent? winDraw;
  if (r.type == 'tsumo' && r.winner == p.hero && r.winTile != null) {
    final lastDiscard = turns.last.discardEvent;
    final i = events.lastIndexWhere((e) => e.seat == p.hero && e.type == PaifuEventType.draw);
    if (i > lastDiscard) {
      events[i] = events[i].copyWith(tile: r.winTile, hand: end);
    } else {
      winDraw = PaifuEvent(type: PaifuEventType.draw, seat: p.hero, tile: r.winTile, hand: end);
    }
  }
  var restored = 0;
  // 울기 차례를 짐작으로 끼운 뒤(그 앞 차례)는 줄 순서가 짐작이라 손패 · 뽑은 패에도 guess 를 단다.
  var guessed = false;
  int? failed;
  String? why;
  for (final t in turns.reversed) {
    final m = memo[t.index];
    final n = row.length;
    void fail(String reason) {
      failed = t.index;
      why = reason;
      m['src'] = 'failed';
      m['reason'] = reason;
      // 이 차례의 버린 뒤 손패(= 뒤 차례의 시작 줄)는 확실하다 — 그것만 남긴다.
      events[t.discardEvent] = events[t.discardEvent].copyWith(hand: row, guess: guessed ? true : null);
    }

    final r = readings[t.index];
    if (r != null) m['read'] = r.toMemo();
    if (t.kind == RestoreTurnKind.unsupported) {
      fail(t.reason ?? '복원할 수 없는 차례');
      break;
    }
    if (t.kind == RestoreTurnKind.afterCall) {
      final hand = callHandTiles(p, t.callEvent!);
      if (hand == null) {
        fail('울기로 나간 패를 정하지 못했습니다');
        break;
      }
      final before = backCall(row, [...hand, t.river], sch);
      final mid = backCall(row, [t.river], sch); // 울기 뒤 · 버리기 전
      final bad = _impossible(before);
      if (bad != null) {
        fail('모순: $bad');
        break;
      }
      events[t.discardEvent] = events[t.discardEvent].copyWith(hand: row, tsumogiri: false, guess: true);
      events[t.callEvent!] = events[t.callEvent!].copyWith(hand: mid, guess: true);
      m['src'] = 'call_guess';
      m['guess'] = true;
      guessed = true;
      restored++;
      row = before;
      continue;
    }
    List<String>? order;
    if (t.kind == RestoreTurnKind.rule) {
      order = [for (var i = 1; i <= n; i++) '$i'];
      m['src'] = 'rule';
    } else {
      if (r == null) {
        fail('읽지 않은 차례');
        break;
      }
      if (!r.answered) {
        fail('답 없음: ${r.error ?? '-'}');
        break;
      }
      order = orderOf(r, n);
      if (order == null) {
        fail('끝 줄 순서가 온전하지 않습니다: ${r.endOrder}');
        break;
      }
      m['src'] = 'api';
      if (r.unsure) m['unsure'] = true;
      if (!r.orderOk && r.kind == 'hand') m['order_from_kj'] = true;
    }
    final ({List<PaifuTile> before, PaifuTile drawn, bool tsumogiri}) b;
    try {
      b = backRow(row, order, t.river);
    } on FormatException catch (e) {
      m.remove('unsure');
      fail(e.message);
      break;
    }
    final bad = _impossible([...b.before, b.drawn]);
    if (bad != null) {
      fail('모순: $bad');
      break;
    }
    final de = t.drawEvent;
    if (de != null) {
      final old = events[de];
      if (old.tile != null && old.tile!.tile != b.drawn.tile) {
        fail('뽑은 패가 기록(${old.tile})과 다름(${b.drawn})');
        break;
      }
      events[de] = old.copyWith(tile: b.drawn, hand: b.before, guess: guessed ? true : null);
    } else {
      newDraws[t.discardEvent] =
          PaifuEvent(type: PaifuEventType.draw, seat: p.hero, tile: b.drawn, hand: b.before, guess: guessed);
    }
    events[t.discardEvent] = events[t.discardEvent].copyWith(hand: row, tsumogiri: b.tsumogiri, guess: guessed ? true : null);
    if (guessed) m['guess'] = true;
    m['order'] = order;
    m['drawn'] = b.drawn.code;
    m['tsumogiri'] = b.tsumogiri;
    restored++;
    row = b.before;
  }
  // 멈춘 차례보다 앞 차례는 손패 없음.
  if (failed != null) {
    for (final t in turns) {
      if (t.index < failed! && memo[t.index]['src'] == 'none') memo[t.index]['src'] = 'skipped';
    }
  }
  final out = <PaifuEvent>[];
  for (final (i, e) in events.indexed) {
    final d = newDraws[i];
    if (d != null) out.add(d);
    out.add(e);
  }
  if (winDraw != null) out.add(winDraw);
  final complete = failed == null;
  final restoredPaifu = restored == 0
      ? p
      : p.copyWith(
          events: out,
          startHand: complete ? row : null,
          handSource: source,
          restore: memo,
        );
  return RebuildResult(
    paifu: restoredPaifu,
    memo: memo,
    restored: restored,
    complete: complete,
    failedTurn: failed,
    failReason: why,
  );
}
