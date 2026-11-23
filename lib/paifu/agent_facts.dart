/// 패보 복기 에이전트의 사실표: 서버 `POST /v2/review/ask` 에 질문과 함께 넘길 한 판의 숫자 전부.
///
/// 규격은 `docs/paifu_review_agent_design_1121.md` 2절. 해설 사실표([reviewFacts])와 달리 hero 버림을 거르지 않고,
/// 차례마다 버림 후보 전부(`options`)를 싣는다 — 에이전트가 아무 차례 · 아무 후보나 물을 수 있게.
/// 서버의 도구는 이 표에서 찾기만 하고 계산하지 않는다(엔진을 두 벌 두지 않음).
///
/// 패 표기는 해설 규격 A-1([Tiles.toCode], 적5 도 `5m`). 플레이어 이름 · 패보 id · 제목 · note 는 넣지 않는다.
/// 뽑기만 한 걸음 · 남의 버림 하나하나도 넣지 않는다(크기). 남의 사건은 리치 · 울기 · 화료만.
///
/// v2(2026-11-22, `docs/paifu_review_agent_defense_design_1122.md` 2절): 차례마다 `defense`(방총 위험의 단계 · 순서).
/// 엔진 리뷰(`reviewPaifu(withEngine: true)`)일 때만 채워지고, 엔진의 % 값 자체는 넣지 않는다.
library;

import '../engine/efficiency.dart';
import '../engine/shanten.dart';
import '../engine/tile.dart';
import 'paifu.dart';
import 'paifu_review.dart';

/// 사실표 판. 서버가 `facts.version` 으로 검사한다.
const agentFactsVersion = 2;

// ── 방총 위험 단계(설계서 1122 1절) ──
//
// 근거: metrics 표 16-11 — 개발 200판, 남이 리치한 차례의 내 버림 14,711개에서 엔진 합친 위험(`mixed34`)별 실제 방총이
// 안전(모두에게 안전패) 0/2,499 · 3% 미만 0.5% · 3~8% 3.4% · 8~18% 8.5% · 18% 이상 14.6%. 엔진 값은 순서는 맞고 크기는
// 1.5배쯤 커서 % 대신 이 다섯 단계로만 말한다. 문턱은 그 표를 보고 정한 값이라 바꾸지 않는다.

/// 이 값 미만이면 "낮음"(엔진 위험 %).
const riskLevelLowBelow = 3.0;

/// 이 값 미만이면 "보통".
const riskLevelMidBelow = 8.0;

/// 이 값 미만이면 "높음", 이상이면 "매우 높음".
const riskLevelHighBelow = 18.0;

/// 다섯 단계(안전한 순).
const riskLevels = ['안전', '낮음', '보통', '높음', '매우 높음'];

// 밀기 · 접기의 "사실"(판정 아님): 버린 패 위험 − 손 안 가장 낮은 위험(%p). 근거: docs/push_fold_design_1122.md 3절
// (맞춤 140판을 보고 고정한 값, 이후 바꾸지 않음).
// a4(11-22, 설계서 1122 "a4" F1): 차이만으로는 '높음' 패를 버리고도 가장 안전한 '보통' 패와 차이가 2 미만이면 "folded" 로
// 적혔다(천봉 du2a) → folded 는 차이 2 미만이고 두 위험이 같은 구간(위 3 · 8 · 18 문턱으로 나눈 넷)일 때만.

/// 이 차 이상이면 "pushed".
const stancePushedAtLeast = 5.0;

/// 이 차 미만이고 버린 패와 가장 안전한 패의 위험이 같은 구간이면 "folded". 구간이 다르거나 차가 그 사이면 "between".
const stanceFoldedBelow = 2.0;

/// 패 하나의 위험 단계. [safeForAll] = 엔진의 "모두에게 안전패"(`RiskTable.safeForAll34`).
String riskLevel(double risk, {required bool safeForAll}) {
  if (safeForAll) return riskLevels[0];
  if (risk < riskLevelLowBelow) return riskLevels[1];
  if (risk < riskLevelMidBelow) return riskLevels[2];
  if (risk < riskLevelHighBelow) return riskLevels[3];
  return riskLevels[4];
}

/// 버린 패의 위험과 손 안 가장 낮은 위험(엔진 %) → pushed · folded · between.
///
/// 차 d = [actualRisk] − [minRisk]. d ≥ [stancePushedAtLeast] 면 pushed. d < [stanceFoldedBelow] 이고 두 위험이
/// 같은 구간([riskLevelLowBelow] · [riskLevelMidBelow] · [riskLevelHighBelow] 로 나눈 넷)이면 folded, 구간이 다르면
/// between. 그 밖은 between. 구간은 '안전'(모두에게 안전패) 표시와 상관없이 숫자로만 본다
/// (= `riskLevel(risk, safeForAll: false)` 가 같은가).
String defenseStance(double actualRisk, double minRisk) {
  final d = actualRisk - minRisk;
  if (d >= stancePushedAtLeast) return 'pushed';
  if (d < stanceFoldedBelow &&
      riskLevel(actualRisk, safeForAll: false) == riskLevel(minRisk, safeForAll: false)) {
    return 'folded';
  }
  return 'between';
}

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
    'defense': _defense(p, t),
  };
}

/// 설계서 1122 2절의 `defense`. 리치한 다른 자리가 있고 · 손패를 알고 · 엔진 위험표가 있을 때만(아니면 null).
/// `threat_winds` 는 엔진이 위험을 합친 자리(리치 · 텐파이율 높은 울기, [TurnReview.riskSeats]).
/// 내가 리치 중인 차례(forced)는 `stance` · `efficient` 가 null.
Map<String, dynamic>? _defense(Paifu p, TurnReview t) {
  final table = t.riskTable;
  final byKind = t.riskByKind;
  if (t.riichiSeats.isEmpty || t.before == null || table == null || byKind == null || byKind.isEmpty) return null;
  final discard = t.discard.tile;
  final actualRisk = byKind[discard];
  if (actualRisk == null) return null;
  final kinds = byKind.keys.toList()
    ..sort((a, b) {
      final c = byKind[a]!.compareTo(byKind[b]!);
      return c != 0 ? c : a - b;
    });
  String level(int k) => riskLevel(byKind[k]!, safeForAll: table.safeForAll34[k]);
  final safe = t.safeTiles.toSet();
  final minRisk = byKind[kinds.first]!;
  // 내가 리치 중(forced)인 차례는 패를 고를 수 없었다 — "밀었다 · 접었다" · 효율대로 버릴 패는 뜻이 없어 null(11-22 보완).
  // 버린 패가 얼마나 위험했나(tiles · actual · safest)는 사실이라 남긴다.
  final canChoose = t.status != ReviewStatus.forced;
  Map<String, dynamic>? efficient;
  final mh = t.mh;
  if (canChoose && mh != null) {
    int? e;
    for (final d in mh) {
      if (!d.isBackward) {
        e = d.tile;
        break;
      }
    }
    e ??= t.mhBest;
    if (e != null && byKind.containsKey(e)) efficient = {'tile': _code(e), 'level': level(e)};
  }
  return {
    'threat_winds': [for (final s in t.riskSeats) _wind(p, s)],
    'tiles': [
      for (final k in kinds) {'tile': _code(k), 'level': level(k), 'genbutsu': safe.contains(k)},
    ],
    'actual': {
      'tile': _code(discard),
      'level': level(discard),
      'rank': 1 + kinds.where((k) => byKind[k]! < actualRisk).length,
      'of': kinds.length,
    },
    'safest': [
      for (final k in kinds)
        if (byKind[k] == minRisk) _code(k),
    ],
    'efficient': efficient,
    'stance': canChoose ? defenseStance(actualRisk, minRisk) : null,
    // 앱 화면은 [TurnReview.pushFold](설계서 docs/push_fold_design_1122.md R3)로 "접는 자리" 를 판정하지만, 여기는 일부러
    // 그대로 null 로 둔다(11-23): 운영 서버(app/review_agent.py)는 fold_spot 을 null/bool 로만 받고, 참이면 에이전트가
    // "접었어야 했다" 같은 판정 말을 쓸 수 있게 돼 설계서 6절의 "참고" 문구(지표 3 이 70% 미만)보다 세다.
    // 에이전트에 넣는 것은 서버를 고치고 안 본 판으로 다시 잰 뒤. 사실표의 다른 칸도 바꾸지 않는다(서버 검증이 모르는 칸을 거절).
    'fold_spot': null,
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
