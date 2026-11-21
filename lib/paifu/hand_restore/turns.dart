/// 손패 복원의 차례 나누기(`docs/paifu_hand_restore_api_1121.md` 3-1). 순수 Dart.
///
/// hero 버림마다 한 차례. 차례 창(녹화에서 볼 구간)은 패보 사건 시각(`at`, 버림 기록기가 처음 본 시각)으로 정한다:
/// - 시작 = 그 버림 직전 다른 자리 버림 시각 − 1.5초, 없으면 hero 앞 버림 + 1초, 첫 차례는 hero 버림 − 20초.
///   버림 기록기 시각은 3초 미리보기 간격이라(±3초) 시작은 hero 버림보다 적어도 3초 앞으로 둔다(앞 hero 버림 + 1초보다는 뒤).
/// - 끝 = 다음 차례 창 시작(마지막 차례는 hero 버림 + 8초). 끝이 hero 버림 + 2초보다 이르면 그것으로.
/// - 창 길이는 60초까지: 넘으면 hero 버림 + 8초 뒤 꼬리를 먼저 자르고, 그래도 길면 앞쪽을 자른다.
/// 리치 선언 다음 차례부터는 규칙(쯔모기리), 퐁 · 치 바로 뒤 버림은 짐작으로 끼운다 — 둘 다 API 를 부르지 않는다.
library;

import '../paifu.dart';

enum RestoreTurnKind {
  /// 녹화를 Claude API 로 읽는다.
  api,

  /// 리치 뒤 — 쯔모기리(규칙).
  rule,

  /// 퐁 · 치 바로 뒤 버림 — 뽑기 없음, 울기로 나간 패와 버린 패를 정렬 자리에 끼워 짐작.
  afterCall,

  /// 복원할 수 없는 차례(깡 · 종류 모르는 울기 뒤, 버림 시각 없음 등). [RestoreTurn.reason] 에 까닭.
  unsupported,
}

class RestoreTurn {
  /// hero 의 몇 번째 버림인가(0부터).
  final int index;

  /// 그 버림 사건 번호(events 안).
  final int discardEvent;

  /// 이 차례의 hero 뽑기 사건 번호(있으면). 버림만 적은 패보는 없다 — 복원이 새로 끼운다.
  final int? drawEvent;

  /// [RestoreTurnKind.afterCall] 이면 그 울기 사건 번호.
  final int? callEvent;

  final RestoreTurnKind kind;

  /// 차례를 시작할 때 줄 장수(13 − 3 × 앞선 울기 수).
  final int n;

  /// 버린 패.
  final PaifuTile river;

  /// 버림 시각과 차례 창(epoch ms). 시각을 모르면 null.
  final int? discardMs, startMs, endMs;

  /// [RestoreTurnKind.unsupported] 의 까닭.
  final String? reason;

  const RestoreTurn({
    required this.index,
    required this.discardEvent,
    required this.kind,
    required this.n,
    required this.river,
    this.drawEvent,
    this.callEvent,
    this.discardMs,
    this.startMs,
    this.endMs,
    this.reason,
  });

  bool get usesApi => kind == RestoreTurnKind.api;
}

const int _beforeOther = 1500;
const int _afterPrevHero = 1000;
const int _firstLead = 20000;
const int _minLead = 3000;
const int _lastTail = 8000;
const int _minTail = 2000;
const int _maxWindow = 60000;

/// hero 버림마다 차례 하나(사건 순서).
List<RestoreTurn> planTurns(Paifu p) {
  final hero = p.hero;
  final ev = p.events;
  final discards = [
    for (final (i, e) in ev.indexed)
      if (e.type == PaifuEventType.discard && e.seat == hero) i,
  ];

  // 1) 종류 · 장수 · 시작(창 끝은 다음 차례 시작이라 두 번에 나눔).
  final starts = <int?>[];
  final drafts = <({RestoreTurnKind kind, int n, int? draw, int? call, String? reason})>[];
  var riichi = false;
  var calls = 0;
  var prevDiscard = -1;
  for (final d in discards) {
    int? draw, call;
    String? reason;
    var kind = RestoreTurnKind.api;
    // 앞 hero 버림 뒤 ~ 이 버림 사이의 hero 사건.
    PaifuEvent? lastHero;
    var lastHeroIndex = -1;
    for (var i = prevDiscard + 1; i < d; i++) {
      final e = ev[i];
      if (e.seat != hero) continue;
      if (e.type == PaifuEventType.draw) draw = i;
      if (e.type == PaifuEventType.call) {
        calls++;
        call = i;
      }
      lastHero = e;
      lastHeroIndex = i;
    }
    final n = 13 - 3 * (calls - (call != null ? 1 : 0));
    if (riichi) {
      kind = RestoreTurnKind.rule;
    } else if (lastHero != null && lastHero.type == PaifuEventType.call) {
      final k = lastHero.callKind ?? 'call';
      if ((k == 'pon' || k == 'chi' || k == 'call') && lastHero.callTiles.length == 3) {
        kind = RestoreTurnKind.afterCall;
        call = lastHeroIndex;
      } else {
        kind = RestoreTurnKind.unsupported;
        reason = k.contains('kan') ? '깡 뒤 차례는 아직 복원하지 못합니다' : '울기 묶음을 모르는 차례라 복원하지 못합니다';
      }
    } else if (call != null) {
      // 울고 나서 다시 뽑은 차례(깡 등) — 줄 장수가 차례 안에서 바뀐다.
      kind = RestoreTurnKind.unsupported;
      reason = '울기가 끼인 차례라 복원하지 못합니다';
    }
    if (ev[d].riichi) riichi = true;
    final heroAt = ev[d].at;
    int? start;
    if (heroAt != null) {
      int? other;
      for (var i = d - 1; i > prevDiscard; i--) {
        final e = ev[i];
        if (e.type == PaifuEventType.discard && e.seat != hero && e.at != null) {
          other = e.at;
          break;
        }
      }
      final prevAt = prevDiscard >= 0 ? ev[prevDiscard].at : null;
      if (other != null) {
        start = other - _beforeOther;
      } else if (prevAt != null) {
        start = prevAt + _afterPrevHero;
      } else {
        start = heroAt - _firstLead;
      }
      if (start > heroAt - _minLead) start = heroAt - _minLead;
      if (prevAt != null && start < prevAt + _afterPrevHero && prevAt + _afterPrevHero < heroAt) start = prevAt + _afterPrevHero;
    } else if (kind == RestoreTurnKind.api) {
      kind = RestoreTurnKind.unsupported;
      reason = '버림 시각이 없어 녹화에서 차례를 찾지 못합니다';
    }
    starts.add(start);
    drafts.add((kind: kind, n: n, draw: draw, call: kind == RestoreTurnKind.afterCall ? call : null, reason: reason));
    prevDiscard = d;
  }

  // 2) 창 끝.
  final out = <RestoreTurn>[];
  for (var t = 0; t < discards.length; t++) {
    final d = discards[t];
    final heroAt = ev[d].at;
    int? start = starts[t], end;
    if (heroAt != null && start != null) {
      int? next;
      for (var u = t + 1; u < discards.length && next == null; u++) {
        next = starts[u];
      }
      end = next ?? heroAt + _lastTail;
      if (end < heroAt + _minTail) end = heroAt + _minTail;
      if (end - start > _maxWindow) {
        // 먼저 hero 버림 + 8초 뒤 꼬리를 자르고, 그래도 길면 앞쪽을 자른다(hero 의 뽑기 · 버림이 창에 남게).
        final keep = heroAt + _lastTail > start + _maxWindow ? heroAt + _lastTail : start + _maxWindow;
        if (end > keep) end = keep;
        if (end - start > _maxWindow) start = end - _maxWindow;
      }
    }
    final dr = drafts[t];
    out.add(RestoreTurn(
      index: t,
      discardEvent: d,
      drawEvent: dr.draw,
      callEvent: dr.call,
      kind: dr.kind,
      n: dr.n,
      river: ev[d].tile!,
      discardMs: heroAt,
      startMs: start,
      endMs: end,
      reason: dr.reason,
    ));
  }
  return out;
}

/// hero 의 끝 줄(마지막 버림 뒤 손패): 화료면 결과 손패(화료패 빼고), 유국이라도 손패가 적혀 있으면 그것. 모르면 null.
List<PaifuTile>? endRowOf(Paifu p) {
  final r = p.result;
  if (r == null || r.hand == null || r.hand!.isEmpty) return null;
  if (r.winner == p.hero || (r.type == 'draw' && r.winner == null)) return r.hand;
  return null;
}
