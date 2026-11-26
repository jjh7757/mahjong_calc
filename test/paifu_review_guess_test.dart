// 설계서 docs/paifu_review_ui_design_1121.md 3-6(짐작 손패는 평가하지 않음) · 3-1 요약 getter · 3-9 막대 · 7절 회귀.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_facts.dart';
import 'package:mahjong_calc/ui/paifu/review_view.dart';

/// 11-21 3-6 을 넣기 **전** 코드(reviewPaifu, 짐작 손패도 평가)로 낸 값 — 고치기 전에 덤프해 적었다.
/// 이름: (efficiencyPct, 차례마다 "status:grade").
const _before = {
  'L16_135321': (97, 'graded:inaccuracy graded:inaccuracy graded:best graded:inaccuracy graded:best graded:best graded:good graded:best graded:best graded:best graded:best graded:best graded:best graded:best graded:best graded:best defense:- defense:-'),
  'r11_130921': (71, 'graded:good graded:best graded:blunder graded:blunder graded:best graded:best graded:best defense:- defense:- forced:- forced:- forced:- forced:- forced:- forced:- forced:-'),
  'r12_131655': (100, 'graded:best graded:best graded:best graded:best graded:best graded:best graded:best forced:- forced:- forced:- forced:- forced:- forced:- forced:-'),
  'r13_132644': (91, 'graded:best graded:inaccuracy graded:inaccuracy graded:best graded:good graded:inaccuracy graded:inaccuracy graded:best graded:best forced:- forced:- forced:- forced:- forced:- forced:- forced:- forced:- forced:-'),
  'r14_133610': (100, 'graded:best graded:best'),
  // 11-26: 3순에 뽑은 패 · 1 ~ 3순 손패를 사용자 영상 확인으로 고침(예시 json) → 패효율 79 → 80 · 2순 good → best.
  'r15_134151': (80, 'graded:best graded:best graded:good graded:good graded:mistake graded:good graded:good graded:best graded:inaccuracy graded:best graded:blunder graded:blunder graded:best graded:best graded:best graded:mistake forced:-'),
  'r16_135321': (87, 'graded:best graded:blunder graded:best graded:best graded:best graded:best graded:inaccuracy graded:mistake graded:best graded:best graded:best graded:good graded:inaccuracy graded:best graded:inaccuracy graded:best forced:- forced:-'),
  'r17_140450': (99, 'graded:best graded:inaccuracy graded:best graded:best graded:best graded:best graded:best graded:best graded:best graded:best graded:best forced:-'),
  'r18_141259': (100, 'graded:best graded:best graded:best graded:best graded:best graded:best graded:best forced:- forced:- forced:-'),
  'r19_142013': (94, 'graded:best graded:best graded:best graded:best graded:best graded:mistake graded:inaccuracy graded:best forced:- forced:-'),
  'r20_143236': (null, 'unknownHand:- unknownHand:- unknownHand:- unknownHand:- unknownHand:- unknownHand:- unknownHand:-'),
};

String _sig(PaifuReview r) => r.turns.map((t) => '${t.status.name}:${t.grade?.name ?? '-'}').join(' ');

Map<String, Map<String, dynamic>> _raw() => {
      for (final f in Directory('assets/paifu').listSync().whereType<File>().where((f) => f.path.endsWith('.json')))
        f.uri.pathSegments.last.replaceAll('.json', ''): jsonDecode(f.readAsStringSync()) as Map<String, dynamic>,
    };

/// 원본 JSON 에서 직접: hero 버림 차례 번호 중 버림 사건 또는 바로 앞 hero 사건이 뽑기이고 guess 인 것.
Set<int> _guessedTurns(Map<String, dynamic> j) {
  final hero = j['hero'] as int;
  final events = (j['events'] as List).cast<Map<String, dynamic>>();
  final out = <int>{};
  var turn = 0;
  for (var i = 0; i < events.length; i++) {
    final e = events[i];
    if (e['seat'] != hero || e['type'] != 'discard') continue;
    turn++;
    Map<String, dynamic>? prev;
    for (var k = i - 1; k >= 0; k--) {
      if (events[k]['seat'] == hero) {
        prev = events[k];
        break;
      }
    }
    final prevDrawGuess = prev != null && prev['type'] == 'draw' && prev['guess'] == true;
    if (e['guess'] == true || prevDrawGuess) out.add(turn);
  }
  return out;
}

/// 손패 있는 짧은 판(hero 1): 뽑기(적5삭) → 중 버림. 고립된 중이라 최선.
Map<String, dynamic> _small({bool drawGuess = false, bool discardGuess = false, bool earlierGuess = false}) => {
      'version': 1,
      'id': 'g',
      'round': '동1국',
      'dealer': 0,
      'hero': 1,
      'names': ['가', '나', '다', '라'],
      'events': [
        if (earlierGuess) ...[
          {
            'type': 'draw',
            'seat': 1,
            'tile': '9p',
            'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '7z'],
            'guess': true,
          },
          {
            'type': 'discard',
            'seat': 1,
            'tile': '9p',
            'tsumogiri': true,
            'riichi': false,
            'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '7z'],
            'guess': true,
          },
        ],
        {'type': 'discard', 'seat': 0, 'tile': '9s', 'tsumogiri': null, 'riichi': false},
        {
          'type': 'draw',
          'seat': 1,
          'tile': '0s',
          'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '7z'],
          'guess': ?(drawGuess ? true : null),
        },
        {
          'type': 'discard',
          'seat': 1,
          'tile': '7z',
          'tsumogiri': false,
          'riichi': false,
          'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '0s'],
          'guess': ?(discardGuess ? true : null),
        },
      ],
    };

void main() {
  group('3-6 짐작 손패', () {
    test('짐작 없음: graded(최선) — 고립된 중을 버린 차례(기존 UI 시험에서도 최선 · 패효율 100)', () {
      final r = reviewPaifu(Paifu.fromJson(_small()));
      expect(r.turns.single.status, ReviewStatus.graded);
      expect(r.turns.single.grade, ReviewGrade.best);
      expect(r.efficiencyPct, 100);
    });

    test('직전 뽑기가 guess → guessed, 등급 · 숫자 없음', () {
      final r = reviewPaifu(Paifu.fromJson(_small(drawGuess: true)));
      final t = r.turns.single;
      expect(t.status, ReviewStatus.guessed);
      expect(t.grade, isNull);
      expect(t.options, isEmpty);
      expect(t.before, isNull);
      expect(t.drawn, const PaifuTile(22, red: true));
      expect(r.efficiencyPct, isNull);
      expect(r.handUnknownCount, 1);
    });

    test('버림 사건이 guess → guessed', () {
      final r = reviewPaifu(Paifu.fromJson(_small(discardGuess: true)));
      expect(r.turns.single.status, ReviewStatus.guessed);
    });

    test('앞 차례의 짐작은 다음 차례에 번지지 않는다', () {
      final r = reviewPaifu(Paifu.fromJson(_small(earlierGuess: true)));
      expect([for (final t in r.turns) t.status], [ReviewStatus.guessed, ReviewStatus.graded]);
    });

    test('gradeGuessed: true 면 예전처럼 평가', () {
      final r = reviewPaifu(Paifu.fromJson(_small(drawGuess: true)), gradeGuessed: true);
      expect(r.turns.single.status, ReviewStatus.graded);
      expect(r.turns.single.grade, ReviewGrade.best);
    });

    test('엔진 포함 평가에서도 guessed 차례는 엔진 버림 순위가 없다', () {
      final r = reviewPaifu(Paifu.fromJson(_small(drawGuess: true)), withEngine: true);
      expect(r.turns.single.status, ReviewStatus.guessed);
      expect(r.turns.single.mh, isNull);
    });

    test('reviewFacts: statuses 에 guessed 가 들고 합은 hero 버림 수, guessed 차례는 해설하지 않음', () {
      final p = Paifu.fromJson(_small(earlierGuess: true));
      final r = reviewPaifu(p);
      final f = reviewFacts(p, r);
      final st = (f['game'] as Map)['statuses'] as Map;
      expect(st['guessed'], 1);
      expect(st['graded'], 1);
      expect(st.values.fold<int>(0, (s, v) => s + (v as int)), 2);
      final timeline = (f['timeline'] as List).cast<Map<String, dynamic>>();
      expect(timeline.first['status'], 'guessed');
      expect(timeline.first['grade'], isNull);
      expect(f['turns'], isEmpty);
    });
  });

  group('예시 11판 회귀(7절)', () {
    final raw = _raw();

    test('gradeGuessed: true 면 11판 모두 3-6 전과 등급 · efficiencyPct 가 같다', () {
      expect(raw.keys.toSet(), _before.keys.toSet());
      for (final MapEntry(key: id, value: j) in raw.entries) {
        final r = reviewPaifu(Paifu.fromJson(j), gradeGuessed: true);
        expect(r.efficiencyPct, _before[id]!.$1, reason: id);
        expect(_sig(r), _before[id]!.$2, reason: id);
      }
    });

    test('기본(3-6): 짐작 차례만 guessed, 나머지 차례의 상태 · 등급은 전과 같다, 짐작 없는 판은 efficiencyPct 도 같다', () {
      // 원본에서 본 짐작 차례: 8판의 녹화 전 첫 순(r11 은 첫 두 순). r15 · r16 · r18 · r20 은 짐작 없음.
      const expectGuessed = {
        'L16_135321': {1},
        'r11_130921': {1, 2},
        'r12_131655': {1},
        'r13_132644': {1},
        'r14_133610': {1},
        'r15_134151': <int>{},
        'r16_135321': <int>{},
        'r17_140450': {1},
        'r18_141259': <int>{},
        'r19_142013': {1},
        'r20_143236': <int>{},
      };
      for (final MapEntry(key: id, value: j) in raw.entries) {
        final guessed = _guessedTurns(j);
        expect(guessed, expectGuessed[id], reason: id);
        final r = reviewPaifu(Paifu.fromJson(j));
        final old = _before[id]!.$2.split(' ');
        expect(r.turns.length, old.length, reason: id);
        for (final t in r.turns) {
          if (guessed.contains(t.turn)) {
            expect(t.status, ReviewStatus.guessed, reason: '$id ${t.turn}');
            expect(t.grade, isNull, reason: '$id ${t.turn}');
          } else {
            expect('${t.status.name}:${t.grade?.name ?? '-'}', old[t.turn - 1], reason: '$id ${t.turn}');
          }
        }
        if (guessed.isEmpty) expect(r.efficiencyPct, _before[id]!.$1, reason: id);
      }
    });

    test('짐작 차례를 빼면 r19 93 · r11 60 (손으로 셈)', () {
      // r19: 2~5 · 8 번째 최선(5) + 6 번째 실수 10/15 + 7 번째 부정확 10/12 = 6.5 → 6.5 / 7 = 92.9 → 93.
      expect(reviewPaifu(Paifu.fromJson(raw['r19_142013']!)).efficiencyPct, 93);
      // r11: 3 · 4 번째 큰 실수(0) + 5 ~ 7 번째 최선(3) = 3 → 3 / 5 = 60.
      expect(reviewPaifu(Paifu.fromJson(raw['r11_130921']!)).efficiencyPct, 60);
    });

    test('요약: 등급 개수 합 + 평가 안 함 네 묶음 합 = hero 버림 수(11판 전부)', () {
      for (final MapEntry(key: id, value: j) in raw.entries) {
        final p = Paifu.fromJson(j);
        final r = reviewPaifu(p);
        final heroDiscards = p.events.where((e) => e.seat == p.hero && e.type == PaifuEventType.discard).length;
        final grades = ReviewGrade.values.fold<int>(0, (s, g) => s + r.gradeCount(g));
        final skipped = r.forcedCount + r.defenseCount + r.completeCount + r.handUnknownCount;
        expect(grades, r.gradedCount, reason: id);
        expect(grades + skipped, heroDiscards, reason: id);
      }
    });

    test('r19 요약 숫자(손으로: 기존 등급에서 짐작 1순을 뺌)', () {
      final r = reviewPaifu(Paifu.fromJson(raw['r19_142013']!));
      expect(r.gradeCount(ReviewGrade.best), 5);
      expect(r.gradeCount(ReviewGrade.mistake), 1);
      expect(r.gradeCount(ReviewGrade.inaccuracy), 1);
      expect(r.forcedCount, 2);
      expect(r.handUnknownCount, 1);
      expect(r.gradedCount, 7);
    });
  });

  group('배울 장면', () {
    TurnReview tv(int turn, ReviewGrade g, {int sl = 0, int ul = 0}) => TurnReview(
          eventIndex: turn * 4,
          turn: turn,
          discard: const PaifuTile(0),
          drawn: null,
          tsumogiri: null,
          riichiDeclared: false,
          status: ReviewStatus.graded,
          melds: 0,
          grade: g,
          shantenLoss: sl,
          ukeireLoss: ul,
        );

    test('큰 실수 → 실수 → 부정확, 큰 실수는 샹텐 손실 큰 것, 나머지는 유효패 손실 큰 것, 같으면 앞 순, 최대 3', () {
      final r = PaifuReview([
        tv(1, ReviewGrade.inaccuracy, ul: 9),
        tv(2, ReviewGrade.mistake, ul: 3),
        tv(3, ReviewGrade.blunder, sl: 1, ul: -5),
        tv(4, ReviewGrade.mistake, ul: 7),
        tv(5, ReviewGrade.blunder, sl: 2),
        tv(6, ReviewGrade.best),
        tv(7, ReviewGrade.mistake, ul: 7),
      ]);
      expect([for (final t in r.lessons()) t.turn], [5, 3, 4]);
      expect([for (final t in r.lessons(max: 10)) t.turn], [5, 3, 4, 7, 2, 1]);
      expect(const PaifuReview([]).lessons(), isEmpty);
    });

    test('r15: 큰 실수 11 · 12(샹텐 손실 같음 → 앞 순) 다음 실수 5(유효패 −11) — 실수 16(−2)은 넷째라 빠짐', () {
      final r = reviewPaifu(Paifu.fromJson(_raw()['r15_134151']!));
      expect([for (final t in r.lessons()) t.turn], [11, 12, 5]);
    });
  });

  group('최선 보기 막대(3-9 · 7절)', () {
    test('11판의 숫자 있는 차례 전부: 막대 높이 순서 = options 유효패 순서, ★ = 최선과 같은 값의 후보', () {
      var turns = 0;
      for (final MapEntry(key: id, value: j) in _raw().entries) {
        final p = Paifu.fromJson(j);
        for (final t in reviewPaifu(p).turns) {
          if (t.options.isEmpty) continue;
          turns++;
          final bars = handBars(t);
          final b = t.best!;
          expect(bars.keys.toSet(), {for (final o in t.options) o.tile}, reason: '$id ${t.turn}');
          // 샹텐을 지키는 후보: options 순서대로 막대 높이가 늘지 않는다(같은 유효패면 같은 높이).
          final keep = [for (final o in t.options) if (o.shanten == b.shanten) o];
          for (var i = 1; i < keep.length; i++) {
            final hi = bars[keep[i - 1].tile]!.frac;
            final lo = bars[keep[i].tile]!.frac;
            expect(hi, greaterThanOrEqualTo(lo), reason: '$id ${t.turn}');
            expect(hi == lo, keep[i - 1].ukeire.total == keep[i].ukeire.total, reason: '$id ${t.turn}');
          }
          if (b.ukeire.total > 0) expect(bars[b.tile]!.frac, 1.0);
          // ★: 최선과 샹텐 · 유효패 수가 같은 후보들.
          final stars = {for (final e in bars.values) if (e.best) e.tile};
          expect(stars, {for (final o in t.options) if (o.shanten == b.shanten && o.ukeire.total == b.ukeire.total) o.tile},
              reason: '$id ${t.turn}');
          // 뒤로 가는 후보는 점(높이 0), 실제 버림 표시는 한 종류.
          for (final o in t.options.where((o) => o.shanten > b.shanten)) {
            expect(bars[o.tile]!.backward, isTrue);
            expect(bars[o.tile]!.frac, 0);
          }
          expect(bars.values.where((e) => e.actual).map((e) => e.tile), [t.discard.tile]);
        }
      }
      expect(turns, greaterThan(100));
    });

    test('버리기 전 줄: 11판 전부 before 와 같은 구성(14 − 3 × 울기), 흐린 패 = 버린 패', () {
      for (final MapEntry(key: id, value: j) in _raw().entries) {
        final p = Paifu.fromJson(j);
        for (final t in reviewPaifu(p).turns) {
          final bh = beforeHandOf(p, t);
          if (t.before == null) {
            expect(bh, isNull);
            continue;
          }
          expect(bh, isNotNull, reason: '$id ${t.turn}');
          final c = toCounts([for (final x in bh!.all) x.tile]);
          expect(c, t.before, reason: '$id ${t.turn}');
          final ghost = bh.ghost == -1 ? bh.drawn! : bh.row[bh.ghost];
          expect(ghost.tile, t.discard.tile, reason: '$id ${t.turn}');
        }
      }
    });

    test('적5 는 그 걸음의 손패 기록에서: r17 2번째(손에 0s) · 쯔모기리면 뽑은 패가 흐린 패', () {
      final p = Paifu.fromJson(_raw()['r17_140450']!);
      final t = reviewPaifu(p).turns.firstWhere((x) => x.turn == 2);
      final bh = beforeHandOf(p, t)!;
      expect(bh.all.where((x) => x.red).map((x) => x.code), ['0s']);
      // 원본 사건: 2번째 버림은 9p 쯔모기리(뽑은 패 9p).
      expect(bh.drawn, PaifuTile.parse('9p'));
      expect(bh.ghost, -1);
    });

    test('손에서 낸 버림은 손패 줄의 자리: 손으로 만든 판', () {
      final p = Paifu.fromJson(_small());
      final t = reviewPaifu(p).turns.single;
      final bh = beforeHandOf(p, t)!;
      expect(bh.drawn, const PaifuTile(22, red: true));
      expect(bh.ghost, 12); // 뽑기 전 줄 1m…2s 7z 의 13번째(중)
      expect(bh.row[bh.ghost], PaifuTile(Tiles.parse('7z')));
    });

    test('막대 비율: 손으로 만든 후보(15 · 15 · 10 · 후퇴)', () {
      DiscardOption o(int tile, int sh, int n) => DiscardOption(tile, sh, Ukeire(sh, [UkeireTile(33, n)]));
      final t = TurnReview(
        eventIndex: 1,
        turn: 1,
        discard: const PaifuTile(3),
        drawn: null,
        tsumogiri: null,
        riichiDeclared: false,
        status: ReviewStatus.graded,
        melds: 0,
        options: [o(2, 1, 15), o(20, 1, 15), o(3, 1, 10), o(25, 2, 48)],
        best: o(2, 1, 15),
        actual: o(3, 1, 10),
        grade: ReviewGrade.mistake,
      );
      final bars = handBars(t);
      expect(bars[2]!.frac, 1.0);
      expect(bars[20]!.frac, 1.0);
      expect(bars[3]!.frac, closeTo(10 / 15, 1e-9));
      expect(bars[25]!.backward, isTrue);
      expect({for (final e in bars.values) if (e.best) e.tile}, {2, 20});
      expect(bars[3]!.actual, isTrue);
    });
  });
}
