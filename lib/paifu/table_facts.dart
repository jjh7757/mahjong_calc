/// 탁자 사실표: 대국 뒤 복기 대화("그때 어떻게 봤어?")의 판 하나 사실 — 네 자리 사건 전부.
///
/// 규격은 `docs/postgame_review_chat_design_1124.md` 3 · 4절(0단계). 판 중 손패가 없는 매장 판에서도 만들어지게
/// 공개 정보(강 · 울기 · 리치 · 도라 표시패)만 쓴다. 플레이어 이름 · 패보 id · 제목 · note 는 넣지 않는다.
/// 패 표기는 [Tiles.toCode](적5 도 `5m`), 자리는 바람("동 · 남 · 서 · 북", [Paifu.windOf]).
///
/// ```
/// { "version": 1,
///   "game": {round, honba, dealer_wind, dora_indicators, scores({"동": 점수, …} | null),
///            result({type, winner, loser, win_tile} | null)},
///   "events": [   // 패보 events 중 discard · call 만, 순서대로. step = events 인덱스 + 1(재생 걸음)
///     {step, wind, kind: "discard", tile, turn_of_seat, riichi, after_riichi_of: [바람…],
///      vs: [{wind, genbutsu, suji, no_chance, visible, level}]},
///     {step, wind, kind: "call", call, from, tiles: […]} ],
///   "scenes_by_seat": {"동": [{step, why}], "남": […], "서": […], "북": […]} }
/// ```
///
/// 정의(독립 Python 대조가 같은 정의로 따로 계산한다 — 바꾸면 그쪽도):
/// - `turn_of_seat`: 그 자리의 버림 수(이 버림 포함, 1부터).
/// - `after_riichi_of`: 이 사건보다 앞에 리치 선언 버림이 있는 **다른** 자리들(바람 순).
/// - 현물 집합(R, 이 사건 직전): R 이 지금까지 버린 모든 패(울려 간 것 포함) ∪ R 의 리치 선언 사건 뒤 누구든 버린 패.
/// - `suji`(수패만): 1~3 → +3, 7~9 → −3, 4~6 → ±3 둘 다가 현물 집합에 있음.
/// - `visible`: 이 사건 직전까지 공개된 같은 종류 장수 = 강(울려 간 것 빼고) + 울기 묶음 + 도라 표시패(판 끝 값).
///   이번 버림 한 장 · 손패는 넣지 않는다. 울려 간 버림 = call 의 `from` 자리의 그때 마지막 버림(묶음 쪽에서 한 번만 셈).
///   가깡(`kakan`)은 앞서 한 퐁 묶음을 바꾼다(재생 탁자 [Paifu.states] 와 같은 셈 — 퐁 3장 + 가깡 4장으로 겹쳐 세지 않음).
/// - `no_chance`(수패만): 이 패를 기다리는 양면 모양((n+1, n+2) · (n−2, n−1) 중 있는 것)이 모두 막힘(둘 중 하나의 보인 장수 == 4).
/// - `level`: 버린 사람 시점([riskContextAt] 의 `selfSeat` = 버린 자리, 손패 없음)의 엔진 위험표에서 **R 한 사람의 값**
///   (`bySeat[R].risk34 × 텐파이율 / 100` — 리치라 텐파이율 100, R 의 `safe34` 를 '안전' 표시로)을 [riskLevel] 로.
///   여러 사람을 합친 값(`mixed34` · `safeForAll34`)은 쓰지 않는다. 계산이 실패하면 null.
/// - 장면(설계서 4절, 자리마다 최대 [tableScenesMax] 개, 같은 걸음은 한 번만): ① `deal_in` 론을 맞은 자리의 마지막 버림이
///   화료패와 같으면 그 버림 → ② `risky_after_riichi` 리치 뒤 버림 중 어떤 R 에 현물이 아니고 단계가 '높음' 이상인 것,
///   (가장 높은 단계 내림차순, 같으면 걸음 순) 앞 둘 → ③ `own_riichi` 리치 선언 버림 → ④ `call` 첫 울기.
library;

import '../engine/risk.dart' show RiskTable, riskOf;
import '../engine/tile.dart';
import 'agent_facts.dart' show riskLevel, riskLevels;
import 'mh_context.dart' show riskContextAt;
import 'paifu.dart';

/// 탁자 사실표 판.
const tableFactsVersion = 1;

/// 자리마다 장면 수 상한.
const tableScenesMax = 5;

/// `risky_after_riichi` 장면 수 상한.
const tableRiskyMax = 2;

const _windNames = ['동', '남', '서', '북'];

bool _valid(int t) => t >= 0 && t < Tiles.count;

bool _seatOk(int? s) => s != null && s >= 0 && s < 4;

String _code(int t) => Tiles.toCode(t);

/// 강에 놓인 패 한 장(울려 갔나 표시).
class _River {
  final int tile;
  bool called = false;
  _River(this.tile);
}

/// 울기 묶음 하나(가깡이 퐁을 바꿀 때 종류 · 첫 패로 찾는다).
class _Meld {
  final String kind;
  final List<int> tiles;
  const _Meld(this.kind, this.tiles);
}

/// 판 하나 → 탁자 사실표(jsonEncode 가능). 예외를 밖으로 내지 않는다(위험 계산 실패는 그 칸만 null).
Map<String, dynamic> tableFacts(Paifu p) {
  String wind(int seat) => _windNames[p.windOf(seat)];
  String? windOrNull(int? seat) => _seatOk(seat) ? wind(seat!) : null;

  final dora = [
    for (final t in p.doraIndicators)
      if (_valid(t.tile)) t.tile,
  ];
  final rivers = [for (var s = 0; s < 4; s++) <_River>[]];
  final melds = [for (var s = 0; s < 4; s++) <_Meld>[]];
  final ownDiscards = [for (var s = 0; s < 4; s++) <int>[]]; // 자리별 버린 패(울려 간 것 포함)
  final allDiscards = <(int, int)>[]; // (사건 인덱스, 패) 순서대로
  final riichiAt = List<int?>.filled(4, null); // 자리별 리치 선언 버림의 사건 인덱스
  final turns = List<int>.filled(4, 0);

  List<int> visibleNow() {
    final v = List<int>.filled(Tiles.count, 0);
    for (var s = 0; s < 4; s++) {
      for (final r in rivers[s]) {
        if (!r.called && _valid(r.tile)) v[r.tile]++;
      }
      for (final m in melds[s]) {
        for (final t in m.tiles) {
          if (_valid(t)) v[t]++;
        }
      }
    }
    for (final t in dora) {
      v[t]++;
    }
    return v;
  }

  final events = <Map<String, dynamic>>[];

  for (final (i, e) in p.events.indexed) {
    if (!_seatOk(e.seat)) continue;
    switch (e.type) {
      case PaifuEventType.draw:
        break;
      case PaifuEventType.discard:
        final pt = e.tile;
        if (pt == null) continue;
        final t = pt.tile;
        final seat = e.seat;
        turns[seat]++;
        final rs = [
          for (var s = 0; s < 4; s++)
            if (s != seat && riichiAt[s] != null) s,
        ]..sort((a, b) => p.windOf(a) - p.windOf(b));
        final vs = <Map<String, dynamic>>[];
        if (rs.isNotEmpty && _valid(t)) {
          final v = visibleNow();
          RiskTable? table;
          try {
            table = riskOf(riskContextAt(p, i, selfSeat: seat, visible34: v));
          } catch (_) {
            table = null;
          }
          for (final r in rs) {
            final gen = List<bool>.filled(Tiles.count, false);
            for (final x in ownDiscards[r]) {
              if (_valid(x)) gen[x] = true;
            }
            for (final (j, x) in allDiscards) {
              if (j > riichiAt[r]! && _valid(x)) gen[x] = true;
            }
            vs.add({
              'wind': wind(r),
              'genbutsu': gen[t],
              'suji': _suji(t, gen),
              'no_chance': _noChance(t, v),
              'visible': v[t],
              'level': _levelFor(table, r, t),
            });
          }
        }
        events.add({
          'step': i + 1,
          'wind': wind(seat),
          'kind': 'discard',
          'tile': _valid(t) ? _code(t) : null,
          'turn_of_seat': turns[seat],
          'riichi': e.riichi,
          'after_riichi_of': [for (final r in rs) wind(r)],
          'vs': vs,
        });
        rivers[seat].add(_River(t));
        ownDiscards[seat].add(t);
        allDiscards.add((i, t));
        if (e.riichi && riichiAt[seat] == null) riichiAt[seat] = i;
      case PaifuEventType.call:
        final seat = e.seat;
        final from = e.from;
        // 재생 탁자(Paifu.states)와 같게: 다른 자리에서 가져왔으면 그 자리의 마지막 버림을 강에서 뺀다.
        if (_seatOk(from) && from != seat && rivers[from!].isNotEmpty) rivers[from].last.called = true;
        final kind = e.callKind ?? 'pon';
        final tiles = [for (final x in e.callTiles) x.tile];
        final meld = _Meld(kind, tiles);
        final pon = kind == 'kakan' && tiles.isNotEmpty
            ? melds[seat].indexWhere((m) => m.kind == 'pon' && m.tiles.isNotEmpty && m.tiles.first == tiles.first)
            : -1;
        if (pon >= 0) {
          melds[seat][pon] = meld;
        } else {
          melds[seat].add(meld);
        }
        events.add({
          'step': i + 1,
          'wind': wind(seat),
          'kind': 'call',
          'call': e.callKind ?? 'call',
          // 가져온 자리. 없거나 자기 자리(안깡 · 가깡)면 null — 복기 에이전트 사실표(agent_facts `_others`)와 같다.
          'from': windOrNull(from == seat ? null : from),
          'tiles': [
            for (final x in tiles)
              if (_valid(x)) _code(x),
          ],
        });
    }
  }

  final res = p.result;
  final sc = p.startScores;
  final result = res == null
      ? null
      : <String, dynamic>{
          'type': res.type,
          'winner': windOrNull(res.winner),
          'loser': windOrNull(res.loser),
          'win_tile': res.winTile == null || !_valid(res.winTile!.tile) ? null : _code(res.winTile!.tile),
        };
  return {
    'version': tableFactsVersion,
    'game': {
      'round': p.round,
      'honba': p.honba,
      'dealer_wind': windOrNull(p.dealer),
      'dora_indicators': [for (final t in dora) _code(t)],
      'scores': sc != null && sc.length == 4 ? {for (var s = 0; s < 4; s++) wind(s): sc[s]} : null,
      'result': result,
    },
    'events': events,
    'scenes_by_seat': {
      for (final w in _windNames) w: tableScenes(events, w, result),
    },
  };
}

/// 스지: 같은 수트에서 1~3 → +3, 7~9 → −3, 4~6 → ±3 둘 다가 현물 집합에 있음. 자패는 false.
bool _suji(int t, List<bool> gen) {
  if (t >= 27) return false;
  final n = Tiles.number(t);
  if (n <= 3) return gen[t + 3];
  if (n >= 7) return gen[t - 3];
  return gen[t - 3] && gen[t + 3];
}

/// 노찬스: 이 패를 기다리는 양면 모양이 모두 막힘(모양의 두 패 중 하나라도 보인 장수 == 4). 자패는 false.
bool _noChance(int t, List<int> v) {
  if (t >= 27) return false;
  final n = Tiles.number(t);
  final shapes = <(int, int)>[
    if (n <= 7) (t + 1, t + 2),
    if (n >= 3) (t - 2, t - 1),
  ];
  return shapes.isNotEmpty && shapes.every((s) => v[s.$1] == 4 || v[s.$2] == 4);
}

/// R 한 사람에 대한 위험 단계(엔진 `bySeat[R]`). 표가 없거나 그 자리 값이 없으면 null.
String? _levelFor(RiskTable? table, int r, int t) {
  if (table == null) return null;
  final o = table.bySeat[r];
  if (o == null) return null;
  final risk = o.risk34[t] * o.tenpaiRate / 100;
  if (!risk.isFinite) return null;
  return riskLevel(risk, safeForAll: o.safe34[t]);
}

/// 단계 말 → 높을수록 큰 수(없으면 −1).
int _levelRank(Object? level) => level is String ? riskLevels.indexOf(level) : -1;

/// 바람 [wind] 자리의 장면(설계서 4절). 사실표의 `events` 와 `game.result` 만 보고 고른다(사실표 JSON 만으로 다시 셀 수 있게).
///
/// 순서대로 넣고 같은 걸음은 한 번만, 최대 [tableScenesMax] 개:
/// 1. `deal_in`: 결과가 론이고 [wind] 가 맞은 자리이며, 그 자리 마지막 버림의 패가 화료패와 같으면 그 버림.
/// 2. `risky_after_riichi`: 그 자리 버림 중 `vs` 의 어떤 R 에 현물이 아니고 단계가 '높음' · '매우 높음' 인 것.
///    그 R 들 중 가장 높은 단계로 줄 세워(매우 높음 먼저, 같으면 걸음 작은 것 먼저) 앞 [tableRiskyMax] 개를 고른 뒤 넣는다
///    (앞 장면과 걸음이 겹치면 그 하나는 빠지고 다음 후보로 채우지 않는다).
/// 3. `own_riichi`: 그 자리 첫 리치 선언 버림.
/// 4. `call`: 그 자리 첫 울기.
List<Map<String, dynamic>> tableScenes(List<Map<String, dynamic>> events, String wind, Map<String, dynamic>? result) {
  final out = <Map<String, dynamic>>[];
  final used = <int>{};
  void add(int step, String why) {
    if (out.length >= tableScenesMax || used.contains(step)) return;
    used.add(step);
    out.add({'step': step, 'why': why});
  }

  final mine = [
    for (final e in events)
      if (e['kind'] == 'discard' && e['wind'] == wind) e,
  ];
  // 1. 방총.
  if (result != null && result['type'] == 'ron' && result['loser'] == wind && mine.isNotEmpty) {
    final win = result['win_tile'];
    if (win != null && mine.last['tile'] == win) add(mine.last['step'] as int, 'deal_in');
  }
  // 2. 리치 뒤 위험.
  final high = riskLevels.indexOf('높음');
  final risky = <(int, int)>[]; // (가장 높은 단계 순위, 걸음)
  for (final ev in mine) {
    var best = -1;
    for (final v in (ev['vs'] as List? ?? const []).cast<Map<String, dynamic>>()) {
      if (v['genbutsu'] == true) continue;
      final r = _levelRank(v['level']);
      if (r >= high && r > best) best = r;
    }
    if (best >= high) risky.add((best, ev['step'] as int));
  }
  risky.sort((a, b) => a.$1 != b.$1 ? b.$1 - a.$1 : a.$2 - b.$2);
  for (final (_, step) in risky.take(tableRiskyMax)) {
    add(step, 'risky_after_riichi');
  }
  // 3. 리치 선언.
  for (final ev in mine) {
    if (ev['riichi'] == true) {
      add(ev['step'] as int, 'own_riichi');
      break;
    }
  }
  // 4. 첫 울기.
  for (final e in events) {
    if (e['kind'] == 'call' && e['wind'] == wind) {
      add(e['step'] as int, 'call');
      break;
    }
  }
  return out;
}
