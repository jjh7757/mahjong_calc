/// 패보 리뷰의 사실표: LLM 해설 서버(`POST /v2/review/explain`)에 넘길 요청 JSON.
///
/// 규격은 `docs/paifu_review_llm_design_1118.md` 부록 A(A-1 패 표기 · A-2 요청 · A-3 모양 힌트 · A-8 v1.1 더한 칸).
/// 패는 전부 [Tiles.toCode] 꼴(적5 도 `5m`). 플레이어 이름 · 패보 id · 제목 · note · 결과는 넣지 않는다.
library;

import '../engine/efficiency.dart';
import '../engine/shanten.dart';
import '../engine/tile.dart';
import 'paifu.dart';
import 'paifu_review.dart';

const _windNames = ['동', '남', '서', '북'];

String _code(int t) => Tiles.toCode(t);

String _wind(Paifu p, int seat) => _windNames[p.windOf(seat)];

/// 부록 A-2 의 요청 JSON(Map). jsonEncode 가능해야 한다.
Map<String, dynamic> reviewFacts(Paifu p, PaifuReview r) {
  return {
    'version': 1,
    'game': {
      'round': p.round,
      'honba': p.honba,
      'hero_wind': _wind(p, p.hero),
      'dora_indicators': [for (final t in p.doraIndicators) _code(t.tile)],
      'efficiency_pct': r.efficiencyPct,
      'grades': {for (final g in ReviewGrade.values) g.name: r.gradeCount(g)},
      // 11-21(설계서 3-6): 짐작 손패 차례는 'guessed' 칸으로 센다. 화면은 unknownHand · inconsistent · guessed 를 묶어
      // "손패 모름" 으로 보인다. 합은 늘 hero 버림 수.
      'statuses': {for (final s in ReviewStatus.values) s.name: r.count(s)},
    },
    'timeline': [
      for (final t in r.turns)
        {
          'turn': t.turn,
          'discard': _code(t.discard.tile),
          'status': t.status.name,
          'grade': t.grade?.name,
          'shanten_after': t.actual?.shanten,
          'total': t.actual?.ukeire.total,
          'riichi': t.riichiDeclared,
        },
    ],
    'turns': [
      for (final t in r.turns)
        if (_explained(t)) _turnFacts(p, t),
    ],
  };
}

/// 해설할 차례: 등급이 부정확 · 실수 · 큰 실수이거나 상태가 defense · complete.
bool _explained(TurnReview t) =>
    t.grade == ReviewGrade.inaccuracy ||
    t.grade == ReviewGrade.mistake ||
    t.grade == ReviewGrade.blunder ||
    t.status == ReviewStatus.defense ||
    t.status == ReviewStatus.complete;

Map<String, dynamic> _option(DiscardOption o, {bool withTiles = true}) => {
      'discard': _code(o.tile),
      'shanten': o.shanten,
      'total': o.ukeire.total,
      'kinds': o.ukeire.liveKinds,
      if (withTiles)
        'tiles': [
          for (final u in o.ukeire.tiles) {'tile': _code(u.tile), 'left': u.left},
        ],
    };

/// [a] 의 유효패 중 남은 장수가 있고 [b] 의 유효패(남은 장수 있는 것)에 없는 패, 패 번호 순.
List<String> _onlyIn(DiscardOption a, DiscardOption b) {
  final other = {
    for (final u in b.ukeire.tiles)
      if (u.left > 0) u.tile,
  };
  final out = [
    for (final u in a.ukeire.tiles)
      if (u.left > 0 && !other.contains(u.tile)) u.tile,
  ]..sort();
  return [for (final t in out) _code(t)];
}

/// 부록 A-8: 뽑기 전 닫힌 패(`before` − `drawn` 한 장)의 샹텐. 뽑은 패를 모르거나 손에 없으면 null.
int? _shantenPrev(TurnReview t) {
  final before = t.before;
  final drawn = t.drawn?.tile;
  if (before == null || drawn == null || drawn < 0 || drawn >= Tiles.count || before[drawn] == 0) return null;
  final prev = [...before];
  prev[drawn]--;
  return shanten(prev, melds: t.melds);
}

Map<String, dynamic> _turnFacts(Paifu p, TurnReview t) {
  final before = t.before;
  final actual = t.actual;
  final best = t.best;
  final drawn = t.drawn?.tile;
  return {
    'turn': t.turn,
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
    'melds': t.melds,
    'riichi_declared': t.riichiDeclared,
    'shanten_prev': _shantenPrev(t),
    'shanten_before': t.shantenBefore,
    'actual': actual == null ? null : _option(actual),
    'best': best == null ? null : _option(best),
    'top': [for (final o in t.options.take(3)) _option(o, withTiles: false)],
    'rank': t.rank,
    'shanten_loss': t.shantenLoss,
    'ukeire_loss': t.ukeireLoss,
    'only_best': actual == null || best == null ? <String>[] : _onlyIn(best, actual),
    'only_actual': actual == null || best == null ? <String>[] : _onlyIn(actual, best),
    'shape': {
      'drawn': before == null || drawn == null ? <Map<String, dynamic>>[] : shapeOf(before, drawn),
      'discard': before == null ? <Map<String, dynamic>>[] : shapeOf(before, t.discard.tile),
      'best': before == null || best == null ? <Map<String, dynamic>>[] : shapeOf(before, best.tile),
    },
    'riichi_winds': [for (final s in t.riichiSeats) _wind(p, s)],
    'genbutsu': t.genbutsu,
    'safe_tiles': [for (final k in t.safeTiles) _code(k)],
  };
}

Map<String, dynamic> _block(String kind, List<int> tiles) => {
      'kind': kind,
      'tiles': [for (final k in tiles) _code(k)],
    };

/// 부록 A-3: [counts](버리기 전 손패 34칸)에서 패 [tile] 이 낄 수 있는 덩어리 전부.
///
/// 순서는 triplet → pair → sequence → ryanmen → penchan → kanchan → isolated, 같은 kind 안에서는 첫 패 번호 순.
/// [tile] 이 손에 없으면(counts[tile] == 0) 낄 덩어리가 없으므로 빈 목록.
List<Map<String, dynamic>> shapeOf(List<int> counts, int tile) {
  if (tile < 0 || tile >= Tiles.count || counts.length != Tiles.count || counts[tile] <= 0) return [];
  final c = counts[tile];
  final out = <Map<String, dynamic>>[];
  if (c >= 3) out.add(_block('triplet', [tile, tile, tile]));
  if (c >= 2) out.add(_block('pair', [tile, tile]));
  if (!Tiles.isHonor(tile)) {
    final suit = Tiles.suit(tile);
    // 같은 수트 안에 있고 손에 1장 이상.
    bool has(int k) => k >= 0 && k < 27 && Tiles.suit(k) == suit && counts[k] > 0;
    for (final lo in [tile - 2, tile - 1, tile]) {
      if (has(lo) && has(lo + 1) && has(lo + 2)) {
        out.add(_block('sequence', [lo, lo + 1, lo + 2]));
      }
    }
    // 이웃 두 장: 1-2 · 8-9 면 penchan, 아니면 ryanmen.
    final neighbors = [
      if (has(tile - 1)) [tile - 1, tile],
      if (has(tile + 1)) [tile, tile + 1],
    ];
    bool edge(List<int> two) => Tiles.number(two[0]) == 1 || Tiles.number(two[1]) == 9;
    for (final two in neighbors) {
      if (!edge(two)) out.add(_block('ryanmen', two));
    }
    for (final two in neighbors) {
      if (edge(two)) out.add(_block('penchan', two));
    }
    if (has(tile - 2)) out.add(_block('kanchan', [tile - 2, tile]));
    if (has(tile + 2)) out.add(_block('kanchan', [tile, tile + 2]));
  }
  if (out.isEmpty) out.add(_block('isolated', [tile]));
  return out;
}
