// 웹(기록 사이트)과 Dart VM 이 같이 쓰는 엔진 입구. 패보 JSON 글 → 결과 JSON 글.
//
// 앱의 순수 Dart 엔진(lib/engine · lib/paifu)을 그대로 부른다 — 로직을 새로 짜지 않고, 앱 화면이 부르는 함수
// (scoreOf · reviewPaifu · review_sentence.dart 의 글 함수)의 결과를 JSON 으로 옮기기만 한다.
// 이 파일은 dart:js_interop 을 쓰지 않아 VM(대조 스크립트 compare_vm.dart)과 dart2js(web_engine.dart) 양쪽에서 돈다.
//
// 룰: RuleSet.standard(쿠이탄 있음 · 끌어올림 만관 없음 · 헤아림 역만 있음 · 더블 역만 있음 · 연풍패 머리 4부 · 적도라 있음)
// — 앱 기본값. 앱은 사용자가 바꾼 룰(RulesStore)을 쓸 수 있으나 웹에는 그 설정이 없다.
// 복기: reviewPaifu(기본 문턱 10% · 30%, 엔진 참고값 withEngine 끔) — 앱 재생 화면이 처음 그릴 때(PaifuReviewIndex.of)와 같다.
library;

import 'dart:convert';

import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/paifu_score.dart';
import 'package:mahjong_calc/paifu/review_sentence.dart';

/// 출력 꼴 판. 칸을 바꾸면 올린다.
const engineApiVersion = 1;

const _rules = RuleSet.standard;
const _thresholds = ReviewThresholds();

Map<String, Object?> _rulesJson(RuleSet r) => {
      'kuitan': r.kuitan,
      'kiriageMangan': r.kiriageMangan,
      'kazoeYakuman': r.kazoeYakuman,
      'doubleYakuman': r.doubleYakuman,
      'doubleWindPairFu': r.doubleWindPairFu,
      'redDora': r.redDora,
    };

/// 패보 JSON 글 → Paifu. 실패하면 예외(부르는 쪽이 {error} 로 바꾼다).
Paifu _parse(String paifuJson) {
  final j = jsonDecode(paifuJson);
  if (j is! Map) throw const FormatException('패보 JSON 이 객체가 아닙니다');
  return Paifu.fromJson(j.cast<String, dynamic>());
}

String _guard(String Function() f) {
  try {
    return f();
  } catch (e) {
    return jsonEncode({'error': e.toString()});
  }
}

// ── 점수 ──

/// 점수 결과 화면(lib/ui/result_screen.dart)의 역 한 줄 오른쪽 글.
String _hanLabel(YakuHan y) {
  if (y.yaku.isYakuman) return y.han >= 2 ? '더블 역만' : '역만';
  return '${y.han}판';
}

/// 점수 결과 화면의 지불 줄(result_screen.dart `_paymentLine`).
String _paymentLine(Payment p) {
  final note = p.honba > 0 ? '  (${p.honbaNote})' : '';
  if (p.ron > 0) return '론: 방총자 ${p.ron}점$note';
  if (p.tsumoFromDealer == 0) return '쯔모: 각 ${p.tsumoFromNonDealer}점$note';
  return '쯔모: 자 ${p.tsumoFromNonDealer}점 / 친 ${p.tsumoFromDealer}점$note';
}

/// 점수 결과 화면의 도장(만관 · 하네만 · 역만 …, result_screen.dart `stamp`).
String _stamp(ScoreResult r) {
  if (r.isYakuman) {
    final n = r.yakumanCount;
    return n >= 2 ? '$n배 역만' : '역만';
  }
  return r.limit.label;
}

Map<String, Object?> _situationJson(Situation s) => {
      'isTsumo': s.isTsumo,
      'isDealer': s.isDealer,
      'seatWind': Tiles.name(s.seatWind),
      'roundWind': Tiles.name(s.roundWind),
      'riichi': s.riichi,
      'doubleRiichi': s.doubleRiichi,
      'ippatsu': s.ippatsu,
      'lastTile': s.lastTile,
      'rinshan': s.rinshan,
      'chankan': s.chankan,
      'firstTurnWin': s.firstTurnWin,
      'doraIndicators': [for (final t in s.doraIndicators) Tiles.toCode(t)],
      'uraIndicators': [for (final t in s.uraIndicators) Tiles.toCode(t)],
      'honba': s.honba,
    };

Map<String, Object?> _resultHead(PaifuResult r) => {
      'type': r.type,
      'winner': r.winner,
      'loser': r.loser,
      'winTile': r.winTile?.code,
      if (r.tenpai != null) 'tenpai': r.tenpai,
    };

/// 끝 결과의 점수. 앱 재생 화면의 "점수 결과 보기 · N점" 단추와 결과 화면(ResultScreen)에 나오는 값.
/// - `kind: none`: 결과 기록 없음.
/// - `kind: draw`: 유국(텐파이 자리 그대로). 점수 없음.
/// - `kind: win`, `score: null`: 화료지만 끝 손패 · 화료패가 없거나 꼴이 안 맞아 계산하지 않음(앱도 단추를 안 그림).
/// - `kind: win`, `score.valid: false`: 계산했으나 역 없음 등(앱은 "점수를 계산할 수 없는 기록입니다 — 까닭").
/// - `kind: win`, `score.valid: true`: 역 · 판 · 부 · 점수 · 지불.
String scoreJson(String paifuJson) => _guard(() {
      final p = _parse(paifuJson);
      final r = p.result;
      if (r == null) return jsonEncode({'kind': 'none', 'rules': _rulesJson(_rules)});
      if (r.type != 'ron' && r.type != 'tsumo') {
        return jsonEncode({'kind': 'draw', 'result': _resultHead(r), 'rules': _rulesJson(_rules)});
      }
      final s = scoreOf(p, rules: _rules);
      if (s == null) {
        return jsonEncode({'kind': 'win', 'result': _resultHead(r), 'score': null, 'rules': _rulesJson(_rules)});
      }
      final res = s.result;
      final pay = res.payment;
      return jsonEncode({
        'kind': 'win',
        'result': _resultHead(r),
        'rules': _rulesJson(_rules),
        'score': {
          'valid': res.isValid,
          'error': res.error,
          'yaku': [
            for (final y in res.yaku)
              {'name': y.yaku.label, 'han': y.han, 'yakuman': y.yaku.isYakuman, 'label': _hanLabel(y)},
          ],
          'han': res.han,
          'fu': res.fu.total,
          'fuItems': [
            for (final f in res.fu.items) {'label': f.label, 'fu': f.fu},
          ],
          'limit': res.limit.name,
          'limitLabel': res.limit.label,
          'yakuman': res.isYakuman,
          'yakumanCount': res.yakumanCount,
          'stamp': res.isValid ? _stamp(res) : '',
          'summary': res.summary,
          'hanFu': res.isValid && !res.isYakuman ? '${res.han}판 ${res.fu.total}부' : '',
          'basePoints': res.basePoints,
          'payment': {
            'ron': pay.ron,
            'tsumoFromDealer': pay.tsumoFromDealer,
            'tsumoFromNonDealer': pay.tsumoFromNonDealer,
            'total': pay.total,
            'honba': pay.honba,
            'display': pay.display,
            'honbaNote': pay.honbaNote,
          },
          'paymentLine': res.isValid ? _paymentLine(pay) : '',
          'situation': _situationJson(s.situation),
          'hand': {
            'closed': [for (final t in r.hand!) t.code],
            'winTile': r.winTile!.code,
            'melds': [
              for (final m in r.melds) {'kind': m.kind, 'tiles': [for (final t in m.tiles) t.code]},
            ],
          },
        },
      });
    });

// ── 복기 ──

/// 배지(재생 화면 걸음 목록 · review_view.dart ReviewBadge): graded 는 등급 이름, defense '수비', complete '화료 형태'.
String? _badgeLabel(TurnReview t) {
  if (t.status == ReviewStatus.graded && t.grade != null) return gradeName(t.grade!);
  if (t.status == ReviewStatus.defense) return '수비';
  if (t.status == ReviewStatus.complete) return '화료 형태';
  return null;
}

/// 등급 아이콘 글자(review_view.dart gradeGlyph).
String _glyph(ReviewGrade g) => switch (g) {
      ReviewGrade.best => '★',
      ReviewGrade.good => '✓',
      ReviewGrade.inaccuracy => '?!',
      ReviewGrade.mistake => '?',
      ReviewGrade.blunder => '??',
    };

/// 후보 칸(review_view.dart ReviewCandidates.candidatesOf): 앞 3 + 실제가 그 밖이면 실제.
List<DiscardOption> _candidatesOf(TurnReview t) {
  final top = t.options.take(3).toList();
  final a = t.actual;
  if (a != null && !top.any((o) => o.tile == a.tile)) top.add(a);
  return top;
}

Map<String, Object?> _optionJson(TurnReview t, DiscardOption o, Set<int> bests) => {
      'tile': Tiles.toCode(o.tile),
      'name': Tiles.name(o.tile),
      'shanten': o.shanten,
      'shantenText': shantenText(o.shanten),
      'word': ukeireWord(o.shanten),
      'ukeire': o.ukeire.total,
      'ukeireTiles': [
        for (final u in o.ukeire.tiles) {'tile': Tiles.toCode(u.tile), 'left': u.left},
      ],
      'actual': o.tile == t.discard.tile,
      'best': bests.contains(o.tile),
      'info': barInfoLine(t, o.tile),
    };

Map<String, Object?> _turnJson(TurnReview t) {
  final g = t.grade;
  final graded = t.status == ReviewStatus.graded && g != null;
  final bests = bestTiles(t).toSet();
  return {
    'step': t.eventIndex + 1,
    'eventIndex': t.eventIndex,
    'turn': t.turn,
    'discard': t.discard.code,
    'discardName': tileText(t.discard),
    'drawn': t.drawn?.code,
    'tsumogiri': t.tsumogiri,
    'riichiDeclared': t.riichiDeclared,
    'status': t.status.name,
    'statusName': statusName(t.status),
    'grade': graded ? g.name : null,
    'gradeName': graded ? gradeName(g) : null,
    'glyph': graded ? _glyph(g) : null,
    'badge': _badgeLabel(t),
    'melds': t.melds,
    'shantenBefore': t.shantenBefore,
    'shantenLoss': t.shantenLoss,
    'ukeireLoss': t.ukeireLoss,
    'rank': t.rank,
    'riichiSeats': t.riichiSeats,
    'genbutsu': t.genbutsu,
    'safeTiles': [for (final s in t.safeTiles) Tiles.toCode(s)],
    'title': reviewTitle(t),
    'corner': reviewCorner(t),
    'lines': reviewCompareLines(t),
    'sentence': reviewSentence(t, withPushFold: false),
    'bestTiles': [for (final b in bestTiles(t)) Tiles.toCode(b)],
    'bestLabel': bestLabel(t),
    'actual': t.actual == null ? null : _optionJson(t, t.actual!, bests),
    'best': t.best == null ? null : _optionJson(t, t.best!, bests),
    'candidates': [for (final o in _candidatesOf(t)) _optionJson(t, o, bests)],
    'options': [for (final o in t.options) _optionJson(t, o, bests)],
  };
}

/// 끝 결과 한 낱말(paifu_screen.dart `_resultShort`).
String _resultShort(PaifuResult? r) => switch (r?.type) {
      'ron' => '론',
      'tsumo' => '쯔모',
      'draw' => '유국',
      null => '',
      _ => '유국',
    };

int? _points(Paifu p) {
  final s = scoreOf(p, rules: _rules);
  return s != null && s.result.isValid ? s.result.payment.total : null;
}

/// 판 요약(review_summary_view.dart PaifuReviewSummary 가 그리는 값과 글).
Map<String, Object?> _summaryJson(Paifu p, PaifuReview r) {
  final pct = r.efficiencyPct;
  const numbered = {ReviewStatus.graded, ReviewStatus.forced, ReviewStatus.defense, ReviewStatus.complete};
  const flagged = {ReviewGrade.inaccuracy, ReviewGrade.mistake, ReviewGrade.blunder};
  return {
    'hasHeroHands': p.hasHeroHands,
    'hasNumbers': r.turns.any((t) => numbered.contains(t.status)),
    'head': p.title.isNotEmpty ? p.title : p.round,
    'result': _resultShort(p.result),
    'turns': r.turns.length,
    'graded': r.gradedCount,
    'efficiencyPct': pct,
    'evaluatedText': pct == null ? '평가할 버림이 없습니다' : '버림 ${r.turns.length}번 가운데 ${r.gradedCount}번을 평가했습니다.',
    'noteText': '유효패 수만 본 값입니다. 수비와 점수 판단은 들어 있지 않습니다.',
    'thresholds': {'goodPct': _thresholds.goodPct, 'inaccuracyPct': _thresholds.inaccuracyPct},
    'thresholdText': '등급 기준(최선보다 유효패가 ${_thresholds.goodPct}% 이하로 적으면 좋음, '
        '${_thresholds.inaccuracyPct}% 이하면 부정확, 그보다 많으면 실수)은 임시 기준입니다.',
    'grades': [
      for (final g in ReviewGrade.values) {'grade': g.name, 'name': gradeName(g), 'glyph': _glyph(g), 'count': r.gradeCount(g)},
    ],
    'skip': {
      'forced': r.forcedCount,
      'defense': r.defenseCount,
      'complete': r.completeCount,
      'handUnknown': r.handUnknownCount,
    },
    'skipText': '리치 중 ${r.forcedCount} · 수비 ${r.defenseCount} · '
        '화료 형태 ${r.completeCount} · 손패 모름 ${r.handUnknownCount}',
    'lessons': [
      for (final t in r.lessons())
        {
          'step': t.eventIndex + 1,
          'turn': t.turn,
          'discard': t.discard.code,
          'text': '${t.turn}순 ${tileText(t.discard)} 버림',
          'grade': t.grade!.name,
          'gradeName': gradeName(t.grade!),
          'glyph': _glyph(t.grade!),
          'loss': lessonLossText(t),
        },
    ],
    'noLessonText': '이 판은 유효패 수에서 지적할 곳이 없습니다',
    'flaggedSteps': [
      for (final t in r.turns)
        if (flagged.contains(t.grade)) t.eventIndex + 1,
    ]..sort(),
  };
}

List<Map<String, Object?>> _stagesJson(Paifu p, PaifuReview r, List<String>? seatLabels) {
  String label(int seat) =>
      seatLabels != null && seat >= 0 && seat < seatLabels.length ? seatLabels[seat] : '${seat + 1}번';
  final pts = _points(p);
  return [
    for (final s in reviewStages(p))
      {
        'step': s.step,
        'kind': s.kind.name,
        'name': stageName(s.kind),
        'sentence': stageSentence(s,
            seatLabel: label, result: endResultText(p.result, points: pts), efficiencyPct: r.efficiencyPct),
      },
  ];
}

/// 복기: hero 버림마다 평가(앱 reviewPaifu 기본값) + 판 요약 + 단계 말풍선 글.
/// [optionsJson] 은 선택: `{"seatLabels": ["동 A", …]}` — 남의 리치 단계 문장에 넣는 자리 이름(없으면 "2번").
String reviewJson(String paifuJson, [String? optionsJson]) => _guard(() {
      final p = _parse(paifuJson);
      List<String>? labels;
      if (optionsJson != null && optionsJson.isNotEmpty) {
        final o = jsonDecode(optionsJson);
        if (o is Map && o['seatLabels'] is List) labels = [for (final x in o['seatLabels'] as List) '$x'];
      }
      final r = reviewPaifu(p, thresholds: _thresholds);
      return jsonEncode({
        'summary': _summaryJson(p, r),
        'turns': [for (final t in r.turns) _turnJson(t)],
        'stages': _stagesJson(p, r, labels),
      });
    });
