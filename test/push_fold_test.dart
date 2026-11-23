// 밀기 · 접기 판정(설계서 docs/push_fold_design_1122.md 3 · 4 · 6 · 7절, metrics 표 16-15) — lib/paifu/paifu_review.dart
// `pushFoldSpotOf` · `TurnReview.pushFold`, 문구 lib/paifu/review_sentence.dart, 말풍선 한 줄 lib/ui/paifu/review_view.dart.
// 정의는 측정 스크립트 experiments/paifu_review/pushfold/pf_eval.py 와 같아야 한다(대상 차례 · 효율 패 · 최소 위험 ·
// 갈림 ≥ 5%p · 밂 ≥ 5 / 접음 < 2 / 그 사이 중간, R3 = 버리기 전 3샹텐 이상). 기대값은 설계서 정의에서 손으로 적었다.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_facts.dart';
import 'package:mahjong_calc/paifu/review_sentence.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/paifu/review_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

int k(String code) => Tiles.parse(code);

/// '2468m5z' → ['2m', '4m', '6m', '8m', '5z'].
List<String> h(String s) {
  final out = <String>[];
  final buf = <String>[];
  for (final ch in s.split('')) {
    if ('mpsz'.contains(ch)) {
      for (final d in buf) {
        out.add('$d$ch');
      }
      buf.clear();
    } else {
      buf.add(ch);
    }
  }
  return out;
}

/// 손으로 만든 한 국: 자리 0(친)이 [river0] 을 버리고 마지막 패로 리치([riichi] 가 거짓이면 리치 없이), 사이에 자리 1 ~ 3 이
/// 끝패 · 자패를 버린다. 그다음 hero(자리 1)가 [hand13] 에 [draw] 를 뽑아 [discard] 를 버린다.
/// [ponLast] 면 뽑는 대신 자리 0 의 마지막 패를 퐁(손의 같은 패 두 장)하고 [discard] 를 버린다(울기 직후 버림).
/// 엔진 값(11-23): 손 2468m357p2468s55z + 3p, 자리 0 강 1z 9p 5p 2z(리치) — 3샹텐, 효율 패 7통(위험 6.13),
/// 최소 위험 5통 0(현물), 8삭 13.39, 백 2.38.
Paifu made({
  String hand13 = '2468m357p2468s55z',
  String draw = '3p',
  required String discard,
  List<String> river0 = const ['1z', '9p', '5p', '2z'],
  bool riichi = true,
  bool ponLast = false,
}) {
  final hand = h(hand13);
  final ev = <Map<String, dynamic>>[];
  const fill = [
    ['9m', '1s', '9s'],
    ['1p', '9p', '4z'],
    ['9s', '1m', '4z'],
    ['1m', '2z', '7z'],
  ];
  for (final (i, t) in river0.indexed) {
    final last = i == river0.length - 1;
    ev.add({'type': 'discard', 'seat': 0, 'tile': t, 'tsumogiri': false, 'riichi': riichi && last});
    if (last) break;
    for (var s = 1; s <= 3; s++) {
      ev.add({'type': 'discard', 'seat': s, 'tile': fill[s - 1][i % 3], 'tsumogiri': null, 'riichi': false});
    }
  }
  if (ponLast) {
    final t = river0.last;
    final after = [...hand]
      ..remove(t)
      ..remove(t);
    ev.add({'type': 'call', 'seat': 1, 'kind': 'pon', 'from': 0, 'tiles': [t, t, t], 'hand': after});
    ev.add({'type': 'discard', 'seat': 1, 'tile': discard, 'tsumogiri': false, 'riichi': false, 'hand': [...after]..remove(discard)});
  } else {
    final after = [...hand, draw]..remove(discard);
    ev.add({'type': 'draw', 'seat': 1, 'tile': draw, 'hand': hand});
    ev.add({'type': 'discard', 'seat': 1, 'tile': discard, 'tsumogiri': false, 'riichi': false, 'hand': after});
  }
  return Paifu.fromJson({
    'version': 1,
    'id': 'pf',
    'round': '동1국',
    'dealer': 0,
    'hero': 1,
    'names': ['', '', '', ''],
    'events': ev,
  });
}

/// 판정 하나만 바꿔 보는 기본 입력: 수비 · 울기 아님 · 3샹텐 · 위험 {1만 0, 2만 5.0(효율 패), 3만 [actual]}.
PushFoldSpot? spot({
  ReviewStatus status = ReviewStatus.defense,
  bool afterCall = false,
  int? shanten = 3,
  double eff = 5.0,
  double actual = 0.0,
  double min = 0.0,
  Map<int, double>? risk,
  String discard = '3m',
  String? efficient = '2m',
}) =>
    pushFoldSpotOf(
      status: status,
      afterCall: afterCall,
      shantenBefore: shanten,
      riskByKind: risk ?? {k('1m'): min, k('2m'): eff, k('3m'): actual},
      discard: k(discard),
      efficient: efficient == null ? null : k(efficient),
    );

/// 문장 · 말풍선용 손으로 만든 수비 차례.
TurnReview turnWith(PushFoldSpot? s, {String discard = '8s', bool genbutsu = false}) => TurnReview(
      eventIndex: 20,
      turn: 9,
      discard: PaifuTile.parse(discard),
      drawn: null,
      tsumogiri: false,
      riichiDeclared: false,
      status: ReviewStatus.defense,
      melds: 0,
      shantenBefore: s?.shantenBefore ?? 3,
      riichiSeats: const [0],
      genbutsu: genbutsu,
      pushFold: s,
    );

PushFoldSpot pf(PushFoldAction a, {String discard = '8s', double risk = 13.39, List<String> safest = const ['5p']}) =>
    PushFoldSpot(
      action: a,
      shantenBefore: 3,
      discard: k(discard),
      discardRisk: risk,
      minRisk: 0,
      safest: [for (final c in safest) k(c)],
      efficient: k('7p'),
      efficientRisk: 6.13,
    );

void main() {
  group('상수(설계서 · 표 16-15)', () {
    test('R3 3샹텐 · 갈림 5 · 접음 2 · 문구 94', () {
      expect(pushFoldMinShanten, 3);
      expect(pushFoldPushGap, 5.0);
      expect(pushFoldFoldGap, 2.0);
      expect(pushFoldAiFoldPct, 94);
    });
  });

  group('조건 경계(pushFoldSpotOf)', () {
    test('샹텐 2 → 없음, 3 → 있음', () {
      expect(spot(shanten: 2), isNull);
      expect(spot(shanten: 3), isNotNull);
      expect(spot(shanten: 5), isNotNull);
      expect(spot(shanten: null), isNull);
    });

    test('효율 패 위험 − 최소 위험 4.9 → 없음, 5.0 → 있음(최소 위험이 0 이 아니어도 차로 봄)', () {
      expect(spot(eff: 4.9), isNull);
      expect(spot(eff: 5.0), isNotNull);
      expect(spot(min: 1.0, eff: 5.9, actual: 1.0), isNull);
      expect(spot(min: 1.0, eff: 6.0, actual: 1.0), isNotNull);
    });

    test('행동: 버린 패 차 1.9 접음 · 2.0 중간 · 4.9 중간 · 5.0 밂', () {
      expect(spot(actual: 1.9)!.action, PushFoldAction.fold);
      expect(spot(actual: 2.0)!.action, PushFoldAction.between);
      expect(spot(actual: 4.9)!.action, PushFoldAction.between);
      expect(spot(actual: 5.0)!.action, PushFoldAction.push);
      expect(spot(actual: 0)!.action, PushFoldAction.fold);
      // 효율 패를 그대로 버림 = 밂.
      expect(spot(discard: '2m')!.action, PushFoldAction.push);
      expect(pushFoldActionOf(1.9999), PushFoldAction.fold);
    });

    test('수비가 아니면 없음: 리치 중(forced) · 평가(남 리치 없음) · 화료 형태 · 손패 모름', () {
      for (final s in ReviewStatus.values) {
        final got = spot(status: s);
        if (s == ReviewStatus.defense) {
          expect(got, isNotNull);
        } else {
          expect(got, isNull, reason: s.name);
        }
      }
    });

    test('울기 직후 → 없음', () {
      expect(spot(afterCall: true), isNull);
    });

    test('후보(손의 패 종류) 1종류 → 없음 · 위험표 없음(엔진 끔) → 없음 · 효율 패 없음 → 없음', () {
      expect(spot(risk: {k('3m'): 9.0}, efficient: '3m'), isNull);
      expect(
          pushFoldSpotOf(
              status: ReviewStatus.defense,
              afterCall: false,
              shantenBefore: 4,
              riskByKind: null,
              discard: k('3m'),
              efficient: k('2m')),
          isNull);
      expect(spot(efficient: null), isNull);
      // 효율 패 · 버린 패가 위험표(손)에 없으면 없음(측정의 "후보에 없는 패" 거르기).
      expect(spot(efficient: '9m'), isNull);
      expect(spot(discard: '9m'), isNull);
    });

    test('근거: 최소 위험 · 가장 안전한 패 전부(번호 순) · 효율 패 위험 · 유한하지 않은 위험은 0', () {
      final s = spot(risk: {k('4m'): 0.0, k('1m'): 0.0, k('2m'): 7.5, k('3m'): 3.0})!;
      expect(s.minRisk, 0);
      expect(s.safest, [k('1m'), k('4m')]);
      expect(s.efficientRisk, 7.5);
      expect(s.efficientGap, 7.5);
      expect(s.discardRisk, 3.0);
      expect(s.discardGap, 3.0);
      expect(s.action, PushFoldAction.between);
      expect(s.shantenBefore, 3);
      final n = spot(risk: {k('1m'): double.nan, k('2m'): 5.0, k('3m'): 0.5})!;
      expect(n.minRisk, 0);
      expect(n.safest, [k('1m')]);
      expect(n.action, PushFoldAction.fold);
    });
  });

  group('효율 패(pushFoldEfficientTile) = 측정의 mhForwardBest or mhBest', () {
    test('엔진 리뷰의 수비 차례: 샹텐을 물리지 않는 첫 후보', () {
      final t = reviewPaifu(made(discard: '8s'), withEngine: true).turns.last;
      expect(t.mh, isNotNull);
      final want = t.mh!.where((d) => !d.isBackward).first.tile;
      expect(pushFoldEfficientTile(t.mh, t.mhBest), want);
      expect(pushFoldEfficientTile(null, t.mhBest), isNull);
      expect(pushFoldEfficientTile(const [], 5), 5);
    });
  });

  group('reviewPaifu — 손으로 만든 한 국', () {
    test('엔진 켬: 8삭(13.4) 밂 · 5통(현물 0) 접음 · 백(2.4) 중간 — 효율 패 7통 6.13', () {
      final push = reviewPaifu(made(discard: '8s'), withEngine: true).turns.last;
      expect(push.status, ReviewStatus.defense);
      expect(push.shantenBefore, 3);
      final s = push.pushFold!;
      expect(s.action, PushFoldAction.push);
      expect(Tiles.toCode(s.efficient), '7p');
      expect(s.efficientRisk, closeTo(6.13, 0.01));
      expect(s.safest, [k('5p')]);
      expect(s.minRisk, 0);
      expect(s.discard, k('8s'));
      expect(s.discardRisk, push.riskOfActual);
      expect(s.discardRisk, closeTo(13.39, 0.01));
      expect(reviewPaifu(made(discard: '5p'), withEngine: true).turns.last.pushFold!.action, PushFoldAction.fold);
      expect(reviewPaifu(made(discard: '5z'), withEngine: true).turns.last.pushFold!.action, PushFoldAction.between);
    });

    test('엔진 끔 → 없음', () {
      final t = reviewPaifu(made(discard: '8s')).turns.last;
      expect(t.status, ReviewStatus.defense);
      expect(t.pushFold, isNull);
    });

    test('남 리치 없음 → 없음(평가 차례)', () {
      final t = reviewPaifu(made(discard: '8s', riichi: false), withEngine: true).turns.last;
      expect(t.status, ReviewStatus.graded);
      expect(t.pushFold, isNull);
    });

    test('갈리지 않음(현물이 효율 패 7통) → 없음', () {
      final t = reviewPaifu(made(discard: '5p', river0: const ['1z', '7p', '5p', '2z']), withEngine: true).turns.last;
      expect(t.status, ReviewStatus.defense);
      expect(t.shantenBefore, 3);
      expect(t.pushFold, isNull);
    });

    test('울기 직후 버림 → 없음(같은 값으로 울기만 빼면 있음)', () {
      final t = reviewPaifu(made(discard: '8s', ponLast: true, river0: const ['1z', '9p', '4m', '5z']), withEngine: true)
          .turns
          .last;
      expect(t.status, ReviewStatus.defense);
      expect(t.melds, 1);
      expect(t.shantenBefore, greaterThanOrEqualTo(3));
      expect(t.pushFold, isNull);
      final same = pushFoldSpotOf(
        status: t.status,
        afterCall: false,
        shantenBefore: t.shantenBefore,
        riskByKind: t.riskByKind,
        discard: t.discard.tile,
        efficient: pushFoldEfficientTile(t.mh, t.mhBest),
      );
      expect(same, isNotNull, reason: '울기만 빼면 접는 자리여야 이 시험이 뜻이 있다');
    });

    test('등급 · 패효율 · 요약 집계는 엔진을 켜도 그대로(반영 안 함)', () {
      for (final d in ['8s', '5p']) {
        final on = reviewPaifu(made(discard: d), withEngine: true);
        final off = reviewPaifu(made(discard: d));
        expect(on.efficiencyPct, off.efficiencyPct);
        for (final s in ReviewStatus.values) {
          expect(on.count(s), off.count(s));
        }
        for (final g in ReviewGrade.values) {
          expect(on.gradeCount(g), off.gradeCount(g));
        }
        expect(on.turns.last.grade, isNull);
      }
    });

    // 사실표 3(11-23, docs/review_agent_foldspot_scores_design_1123.md 2-1): fold_spot 은 객체 {shanten, ai_fold_pct} 또는 null.
    // 행동(push · fold)은 넣지 않고 stance 를 쓴다. 해설 사실표에는 새 칸 없음.
    test('서버로 가는 사실표 3: 접는 자리면 fold_spot {shanten, ai_fold_pct} · 행동 없음 · defense 칸 일곱 · 해설 사실표에 새 칸 없음', () {
      for (final dis in ['8s', '5p', '5z']) {
        final p = made(discard: dis);
        final r = reviewPaifu(p, withEngine: true);
        final pf = r.turns.last.pushFold!;
        final f = agentFacts(p, r);
        expect(f['version'], 3);
        final d = ((f['turns'] as List).last as Map<String, dynamic>)['defense'] as Map<String, dynamic>;
        expect(d.keys, ['threat_winds', 'tiles', 'actual', 'safest', 'efficient', 'stance', 'fold_spot']);
        expect(d['fold_spot'], {'shanten': pf.shantenBefore, 'ai_fold_pct': pushFoldAiFoldPct}, reason: dis);
        expect(d['fold_spot'], {'shanten': 3, 'ai_fold_pct': 94}, reason: dis);
        // 행동은 stance 하나(8삭 밂 · 5통 접음 · 백 중간).
        expect(d['stance'], {'8s': 'pushed', '5p': 'folded', '5z': 'between'}[dis], reason: dis);
        final text = jsonEncode(f) + jsonEncode(reviewFacts(p, r));
        for (final w in ['push_fold', 'pushFold', '"action"', 'fold_spot":true', 'fold_spot":false', '94%', '접는 자리']) {
          expect(text.contains(w), isFalse, reason: '$dis $w');
        }
        expect(jsonEncode(reviewFacts(p, r)).contains('fold_spot'), isFalse, reason: dis);
      }
    });

    test('사실표 3: 접는 자리가 아니면 fold_spot null(defense 는 있음) · 엔진 끄면 defense 째 null', () {
      // 갈리지 않음(현물이 효율 패) — defense 는 있고 fold_spot 만 null.
      final p = made(discard: '5p', river0: const ['1z', '7p', '5p', '2z']);
      final r = reviewPaifu(p, withEngine: true);
      expect(r.turns.last.pushFold, isNull);
      final d = ((agentFacts(p, r)['turns'] as List).last as Map<String, dynamic>)['defense'] as Map<String, dynamic>?;
      expect(d, isNotNull);
      expect(d!.containsKey('fold_spot'), isTrue);
      expect(d['fold_spot'], isNull);
      // 울기 직후 버림도 null.
      final q = made(discard: '8s', ponLast: true, river0: const ['1z', '9p', '4m', '5z']);
      final dq = ((agentFacts(q, reviewPaifu(q, withEngine: true))['turns'] as List).last as Map<String, dynamic>)['defense']
          as Map<String, dynamic>?;
      expect(dq?['fold_spot'], isNull);
      // 엔진 끔: 위험표가 없어 defense 자체가 null(그대로).
      final off = made(discard: '8s');
      expect(((agentFacts(off, reviewPaifu(off))['turns'] as List).last as Map<String, dynamic>)['defense'], isNull);
    });
  });

  group('문장(6절)', () {
    test('밂: 참고 문구 + 근거 숫자, 지적 말 없음', () {
      final t = turnWith(pf(PushFoldAction.push));
      expect(pushFoldHeadline(t), '보통은 접는 자리입니다. 강한 AI 는 이런 자리의 약 94% 에서 접습니다.');
      expect(pushFoldEvidence(t), '내 손 3샹텐 · 방총 위험: 버린 8삭(약 13.4%), 가장 안전 5통(약 0.0%)');
      expect(reviewSentence(t),
          '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다. 보통은 접는 자리입니다. 강한 AI 는 이런 자리의 약 94% 에서 접습니다. '
          '내 손 3샹텐 · 방총 위험: 버린 8삭(약 13.4%), 가장 안전 5통(약 0.0%)');
      expect(reviewSentence(t, withPushFold: false), '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다.');
      for (final w in ['틀렸', '실수', '접었어야', '잘못']) {
        expect(reviewSentence(t).contains(w), isFalse, reason: w);
      }
    });

    test('접음: "잘 접었습니다." + 근거(버린 패가 가장 안전하면 "= 가장 안전")', () {
      final t = turnWith(pf(PushFoldAction.fold, discard: '5p', risk: 0, safest: const ['5p']), discard: '5p', genbutsu: true);
      expect(pushFoldHeadline(t), '잘 접었습니다.');
      expect(reviewSentence(t), '다른 자리가 리치 중입니다. 버린 패는 현물입니다. 잘 접었습니다. 내 손 3샹텐 · 방총 위험: 버린 5통(약 0.0%) = 가장 안전');
      // 가장 안전한 패가 여럿이고 버린 패가 그중이 아니면 번호 작은 패, [safest] 로 고를 수 있음(목록 밖이면 무시).
      final u = turnWith(pf(PushFoldAction.fold, discard: '3p', risk: 1.5, safest: const ['5p', '1z']), discard: '3p');
      expect(pushFoldEvidence(u), '내 손 3샹텐 · 방총 위험: 버린 3통(약 1.5%), 가장 안전 5통(약 0.0%)');
      expect(pushFoldEvidence(u, safest: k('1z')), '내 손 3샹텐 · 방총 위험: 버린 3통(약 1.5%), 가장 안전 동(약 0.0%)');
      expect(pushFoldEvidence(u, safest: k('9m')), '내 손 3샹텐 · 방총 위험: 버린 3통(약 1.5%), 가장 안전 5통(약 0.0%)');
      expect(pushFoldEvidence(u, riskText: (t, v) => '[$v]'), '내 손 3샹텐 · 방총 위험: 버린 3통([1.5]), 가장 안전 5통([0.0])');
    });

    test('중간 · 판정 없음: 덧붙이지 않음', () {
      final mid = turnWith(pf(PushFoldAction.between, risk: 3.0));
      expect(pushFoldHeadline(mid), isNull);
      expect(pushFoldEvidence(mid), isNull);
      expect(pushFoldSentence(mid), isNull);
      expect(reviewSentence(mid), '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다.');
      final none = turnWith(null);
      expect(pushFoldSentence(none), isNull);
      expect(reviewSentence(none), '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다.');
    });
  });

  group('말풍선 한 줄(7절)', () {
    String? note(WidgetTester tester) {
      final f = find.byKey(const ValueKey('paifu-bubble-pushfold'));
      return f.evaluate().isEmpty ? null : tester.widget<Text>(f).textSpan!.toPlainText();
    }

    String? sentence(WidgetTester tester) {
      final f = find.byKey(const ValueKey('paifu-bubble-sentence'));
      return f.evaluate().isEmpty ? null : tester.widget<Text>(f).data;
    }

    for (final size in const [Size(400, 800), Size(1280, 800)]) {
      testWidgets('${size.width.toInt()}×${size.height.toInt()}: 밂 · 접음은 제목 아래 한 줄, 중간은 없음, 넘침 없음', (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        Future<void> show(TurnReview t) async {
          await tester.pumpWidget(MaterialApp(
            home: Scaffold(body: Padding(padding: const EdgeInsets.all(8), child: ReviewBubble.turn(t, step: 21))),
          ));
          await tester.pump();
          expect(tester.takeException(), isNull);
        }

        await show(turnWith(pf(PushFoldAction.push)));
        expect(note(tester),
            '보통은 접는 자리입니다. 강한 AI 는 이런 자리의 약 94% 에서 접습니다. 내 손 3샹텐 · 방총 위험: 버린 8삭(약 13.4%), 가장 안전 5통(약 0.0%)');
        // 문장에는 겹쳐 붙이지 않는다.
        expect(sentence(tester), '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다.');
        // 제목 아래(문장 위).
        expect(tester.getTopLeft(find.byKey(const ValueKey('paifu-bubble-pushfold'))).dy,
            greaterThan(tester.getTopLeft(find.byKey(const ValueKey('paifu-bubble-title'))).dy));
        expect(tester.getTopLeft(find.byKey(const ValueKey('paifu-bubble-pushfold'))).dy,
            lessThan(tester.getTopLeft(find.byKey(const ValueKey('paifu-bubble-sentence'))).dy));
        // 말풍선 안에 다 들어간다(밂: 근거까지 석 줄 + 문장 한 줄).
        final bubble = tester.getRect(find.byKey(const ValueKey('paifu-bubble')));
        expect(tester.getRect(find.byKey(const ValueKey('paifu-bubble-sentence'))).bottom, lessThanOrEqualTo(bubble.bottom));

        await show(turnWith(pf(PushFoldAction.fold, discard: '5p', risk: 0), discard: '5p', genbutsu: true));
        expect(note(tester), '잘 접었습니다. 내 손 3샹텐 · 방총 위험: 버린 5통(약 0.0%) = 가장 안전');
        expect(sentence(tester), '다른 자리가 리치 중입니다. 버린 패는 현물입니다.');
        expect(tester.getRect(find.byKey(const ValueKey('paifu-bubble-sentence'))).bottom,
            lessThanOrEqualTo(tester.getRect(find.byKey(const ValueKey('paifu-bubble'))).bottom));

        await show(turnWith(pf(PushFoldAction.between, risk: 3.0)));
        expect(note(tester), isNull);
        await show(turnWith(null));
        expect(note(tester), isNull);
      });
    }

    // 재생 화면 전체: 엔진 리뷰가 오면 hero 버림 걸음 말풍선에 한 줄. 좁은 화면 · 태블릿 가로.
    for (final size in const [Size(400, 800), Size(1280, 800)]) {
      testWidgets('재생 화면 ${size.width.toInt()}×${size.height.toInt()}: 엔진 리뷰 뒤 hero 버림 걸음에 밂 한 줄', (tester) async {
        SharedPreferences.setMockInitialValues({});
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final p = made(discard: '8s');
        final engine = reviewPaifu(p, withEngine: true);
        final done = Completer<PaifuReview>();
        await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p, engineReview: (_) => done.future)));
        await tester.pump(const Duration(milliseconds: 200));
        await tester.ensureVisible(find.byKey(const ValueKey('paifu-summary-start')));
        await tester.tap(find.byKey(const ValueKey('paifu-summary-start')));
        await tester.pumpAndSettle();
        final target = engine.turns.last.eventIndex + 1;
        int step() => tester.widget<ReviewBubble>(find.byType(ReviewBubble)).step;
        while (step() != target) {
          await tester.sendKeyEvent(step() < target ? LogicalKeyboardKey.arrowRight : LogicalKeyboardKey.arrowLeft);
          await tester.pump();
        }
        await tester.pumpAndSettle();
        // 엔진 전(빠른 리뷰): 판정 칸이 없어 한 줄도 없음.
        expect(find.byKey(const ValueKey('paifu-bubble-pushfold')), findsNothing);
        done.complete(engine);
        await tester.pumpAndSettle();
        expect(note(tester), startsWith('보통은 접는 자리입니다. 강한 AI 는 이런 자리의 약 94% 에서 접습니다. 내 손 3샹텐 · 방총 위험: 버린 8삭'));
        expect(tester.takeException(), isNull);
      });
    }
  });
}
