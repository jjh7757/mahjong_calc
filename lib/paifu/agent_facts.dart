/// 패보 복기 에이전트의 사실표: 서버 `POST /v2/review/ask` 에 질문과 함께 넘길 한 판의 숫자 전부.
///
/// 규격은 `docs/paifu_review_agent_design_1121.md` 2절. 해설 사실표([reviewFacts])와 달리 hero 버림을 거르지 않고,
/// 차례마다 버림 후보 전부(`options`)를 싣는다 — 에이전트가 아무 차례 · 아무 후보나 물을 수 있게.
/// 서버의 도구는 이 표에서 찾기만 하고 계산하지 않는다(엔진을 두 벌 두지 않음).
///
/// 패 표기는 해설 규격 A-1([Tiles.toCode], 적5 도 `5m`). 플레이어 이름 · 패보 id · 제목 · note 는 넣지 않는다.
/// 뽑기만 한 걸음 · 남의 버림 하나하나도 넣지 않는다(크기). 남의 사건은 리치 · 울기 · 화료만.
library;

import '../engine/efficiency.dart';
import '../engine/shanten.dart';
import '../engine/tile.dart';
import 'paifu.dart';
import 'paifu_review.dart';

/// 사실표 판. 서버가 `facts.version` 으로 검사한다.
const agentFactsVersion = 1;

const _windNames = ['동', '남', '서', '북'];

String _code(int t) => Tiles.toCode(t);

String _wind(Paifu p, int seat) => _windNames[p.windOf(seat)];

String? _windOrNull(Paifu p, int? seat) => seat == null || seat < 0 || seat > 3 ? null : _wind(p, seat);

/// 2절의 사실표(Map). jsonEncode 가능해야 한다.
Map<String, dynamic> agentFacts(Paifu p, PaifuReview r) {
  return {
    'version': agentFactsVersion,
    'game': {
      'round': p.round,
      'honba': p.honba,
      'hero_wind': _wind(p, p.hero),
      'dora_indicators': [for (final t in p.doraIndicators) _code(t.tile)],
      'efficiency_pct': r.efficiencyPct,
      'grades': {for (final g in ReviewGrade.values) g.name: r.gradeCount(g)},
      'statuses': {for (final s in ReviewStatus.values) s.name: r.count(s)},
      'result': _result(p),
    },
    'turns': [for (final t in r.turns) _turn(p, t)],
    'others': _others(p),
  };
}

/// 판 결과: 종류(ron · tsumo · draw) · 화료한 자리 바람 · 쏘인 자리 바람 · 화료패. 결과 기록이 없으면 null.
/// 이름 대신 자리 바람으로만 적는다(hero 인지는 `game.hero_wind` 와 비교).
Map<String, dynamic>? _result(Paifu p) {
  final res = p.result;
  if (res == null) return null;
  final win = res.type == 'ron' || res.type == 'tsumo';
  return {
    'type': res.type,
    'winner': win ? _windOrNull(p, res.winner) : null,
    'loser': res.type == 'ron' ? _windOrNull(p, res.loser) : null,
    'win_tile': win && res.winTile != null ? _code(res.winTile!.tile) : null,
  };
}

/// 후보 하나. `tiles` 는 유효패 → 남은 장수(엔진 순서 = 패 번호 순, 남은 장수 0 인 것도 그대로).
///
/// 설계서 2절 예시의 `[{"tile", "left"}]` 목록 대신 순서 있는 맵으로 둔다: 예시 11판 중 두 판(r15 · r16)이 목록 꼴로
/// 압축 60.8 · 63.3KB 라 목표(60KB)를 넘었다. 서버 도구가 LLM 에 보일 때는 목록 꼴로 되돌린다.
Map<String, dynamic> _option(DiscardOption o) => {
      'discard': _code(o.tile),
      'shanten': o.shanten,
      'total': o.ukeire.total,
      'kinds': o.ukeire.liveKinds,
      'tiles': {for (final u in o.ukeire.tiles) _code(u.tile): u.left},
    };

/// 최선과 샹텐 · 유효패 장수가 같은 후보 전부(options 순서). 숫자 없는 차례는 빈 목록.
List<String> _bestCodes(TurnReview t) {
  final b = t.best;
  if (b == null) return const [];
  return [
    for (final o in t.options)
      if (o.shanten == b.shanten && o.ukeire.total == b.ukeire.total) _code(o.tile),
  ];
}

/// 해설 규격 A-8 과 같은 뜻: 뽑기 전 닫힌 패(`before` − `drawn` 한 장)의 샹텐. 뽑은 패를 모르거나 손에 없으면 null.
int? _shantenPrev(TurnReview t) {
  final before = t.before;
  final drawn = t.drawn?.tile;
  if (before == null || drawn == null || drawn < 0 || drawn >= Tiles.count || before[drawn] == 0) return null;
  final prev = [...before];
  prev[drawn]--;
  return shanten(prev, melds: t.melds);
}

Map<String, dynamic> _turn(Paifu p, TurnReview t) {
  final before = t.before;
  final numbers = t.actual != null && t.options.isNotEmpty;
  return {
    'turn': t.turn,
    'step': t.eventIndex + 1,
    'status': t.status.name,
    'grade': t.grade?.name,
    'hand': before == null
        ? null
        : [
            for (var k = 0; k < Tiles.count; k++)
              for (var n = 0; n < before[k]; n++) _code(k),
          ],
    'drawn': t.drawn == null ? null : _code(t.drawn!.tile),
    'discard': _code(t.discard.tile),
    'tsumogiri': t.tsumogiri,
    'melds': t.melds,
    'riichi_declared': t.riichiDeclared,
    'shanten_prev': _shantenPrev(t),
    'shanten_before': t.shantenBefore,
    'shanten_loss': t.shantenLoss,
    'ukeire_loss': t.ukeireLoss,
    'options': [for (final o in t.options) _option(o)],
    'actual': numbers ? _code(t.actual!.tile) : null,
    'best': _bestCodes(t),
    'riichi_winds': [for (final s in t.riichiSeats) _wind(p, s)],
    'genbutsu': t.genbutsu,
    'safe_tiles': [for (final k in t.safeTiles) _code(k)],
  };
}

/// 남의 큰 사건(사건 순서): 리치 선언 버림 · 울기 · 화료(hero 아닌 자리가 화료했을 때, 결과 걸음).
/// `step` 은 재생 걸음(사건 인덱스 + 1, 결과는 사건 수 + 1).
List<Map<String, dynamic>> _others(Paifu p) {
  final out = <Map<String, dynamic>>[];
  for (final (i, e) in p.events.indexed) {
    if (e.seat == p.hero) continue;
    if (e.type == PaifuEventType.discard && e.riichi && e.tile != null) {
      out.add({'step': i + 1, 'wind': _wind(p, e.seat), 'kind': 'riichi', 'tile': _code(e.tile!.tile)});
    } else if (e.type == PaifuEventType.call) {
      out.add({
        'step': i + 1,
        'wind': _wind(p, e.seat),
        'kind': 'call',
        'call': e.callKind ?? 'call',
        'tiles': [for (final t in e.callTiles) _code(t.tile)],
        'from': _windOrNull(p, e.from == e.seat ? null : e.from),
      });
    }
  }
  final res = p.result;
  if (res != null && (res.type == 'ron' || res.type == 'tsumo') && res.winner != null && res.winner != p.hero) {
    out.add({
      'step': p.events.length + 1,
      'wind': _windOrNull(p, res.winner),
      'kind': res.type,
      'tile': res.winTile == null ? null : _code(res.winTile!.tile),
      'from': res.type == 'ron' ? _windOrNull(p, res.loser) : null,
    });
  }
  return out;
}
