import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

/// '123m11z' → ['1m', '2m', '3m', '1z', '1z'].
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

/// 손패 줄에서 한 장 뺀다.
List<String> minus(List<String> hand, String tile) {
  final out = [...hand];
  out.remove(tile);
  return out;
}

int t(String code) => Tiles.parse(code);

Map<String, dynamic> d(int seat, String tile, {List<String>? hand, bool riichi = false, bool? tsumogiri}) => {
      'type': 'discard',
      'seat': seat,
      'tile': tile,
      'tsumogiri': tsumogiri,
      'riichi': riichi,
      'hand': ?hand,
    };

Map<String, dynamic> dr(int seat, String? tile, List<String>? hand) => {'type': 'draw', 'seat': seat, 'tile': tile, 'hand': hand};

Map<String, dynamic> call(int seat, String kind, int from, List<String> tiles, {List<String>? hand}) =>
    {'type': 'call', 'seat': seat, 'kind': kind, 'from': from, 'tiles': tiles, 'hand': ?hand};

/// hero = 자리 0 인 작은 판.
Paifu pf(List<Map<String, dynamic>> events,
        {List<String> dora = const [], List<String> ura = const [], Map<String, dynamic>? result}) =>
    Paifu.fromJson({
      'version': 1,
      'id': 't',
      'hero': 0,
      'dora_indicators': dora,
      'ura_indicators': ura,
      'events': events,
      'result': ?result,
    });

List<(int, int)> waits(DiscardOption o) => [for (final u in o.ukeire.tiles) (u.tile, u.left)];

/// 텐파이 13장: 123m 456p 789s 23s 11z — 기다림 1s·4s.
final tenpai13 = h('123m456p789s23s11z');

/// 등급 시험 손: 뽑기 전 123m 789p 11z 23p 467s + 9m 뽑음(14장, 1샹텐).
///   9m 버림 → 23p(1p·4p) + 467s(5s·8s) : 1p·4p·5s·8s
///   4s 버림 → 23p + 67s(5s·8s)          : 1p·4p·5s·8s (9m 와 같음)
///   7s 버림 → 23p + 46s(5s)             : 1p·4p·5s   (8s 만큼 손해)
///   2p 버림 → 2샹텐
/// 손에 1p·4p·5s·8s 는 없으니 남은 장수 = 4 − 자리 1 강에 보이는 수.
final grade13 = h('123m789p11z23p467s');

TurnReview gradeCase(List<String> river, String discard, {ReviewThresholds th = const ReviewThresholds()}) {
  final p = pf([
    for (final x in river) d(1, x),
    dr(0, '9m', grade13),
    d(0, discard, hand: minus([...grade13, '9m'], discard)),
  ]);
  final r = reviewPaifu(p, thresholds: th);
  expect(r.turns, hasLength(1));
  return r.turns.single;
}

/// 수비 시험 손 14장: 123m 456p 789s + 9m 2z 5z 6z 7z(뽑은 패 7z). 몸통 셋 + 외톨이 다섯 → 2샹텐.
final defense13 = h('123m456p789s9m256z');

DiscardOption opt(int sh, int total) => DiscardOption(0, sh, Ukeire(sh, [UkeireTile(0, total)]));

TurnReview synth(ReviewStatus s, {ReviewGrade? g, int? actual, int? best}) => TurnReview(
      eventIndex: 0,
      turn: 1,
      discard: const PaifuTile(0),
      drawn: null,
      tsumogiri: null,
      riichiDeclared: false,
      status: s,
      melds: 0,
      actual: actual == null ? null : opt(1, actual),
      best: best == null ? null : opt(1, best),
      grade: g,
    );

void main() {
  group('평범한 차례', () {
    test('숫자·등급, 보이는 패는 강·울기·도라 표시패(울려 나간 버림은 한 번, 뒷도라는 안 셈)', () {
      final p = pf([
        d(1, '1s'), // 강에 1s
        d(2, '4s'),
        call(3, 'chi', 2, ['4s', '5s', '6s']), // 4s 는 강에서 빠져 묶음으로 — 한 번만 센다
        d(3, '9p'),
        dr(0, '9m', tenpai13),
        d(0, '9m', hand: tenpai13, tsumogiri: true),
      ], dora: ['1s'], ura: ['4s']);
      final r = reviewPaifu(p).turns.single;
      expect(r.eventIndex, 5);
      expect(r.turn, 1);
      expect(r.discard, PaifuTile(t('9m')));
      expect(r.drawn, PaifuTile(t('9m')));
      expect(r.tsumogiri, isTrue);
      expect(r.riichiDeclared, isFalse);
      expect(r.status, ReviewStatus.graded);
      expect(r.melds, 0);
      expect(r.shantenBefore, 0);
      // 손에 든 종류 13가지(1m2m3m 4p5p6p 7s8s9s 2s3s 1z 9m).
      expect(r.options, hasLength(13));
      expect(r.best!.tile, t('9m'));
      expect(r.actual!.tile, t('9m'));
      expect(identical(r.best, r.options.first), isTrue);
      // 1s: 4 − 강 1 − 도라 표시패 1 = 2. 4s: 4 − 묶음 1 = 3(강에서 울려 나간 것까지 세면 2, 뒷도라까지 세면 1).
      expect(waits(r.actual!), [(t('1s'), 2), (t('4s'), 3)]);
      expect(r.actual!.ukeire.total, 5);
      expect(r.shantenLoss, 0);
      expect(r.ukeireLoss, 0);
      expect(r.rank, 1);
      expect(r.grade, ReviewGrade.best);
      expect(r.riichiSeats, isEmpty);
      expect(r.genbutsu, isNull);
      expect(r.safeTiles, isEmpty);
    });

    test('버림 쪽 근거만 있어도 평가(뽑기 null, 버린 뒤 손패만)', () {
      final r = reviewPaifu(pf([
        dr(0, null, null),
        d(0, '9m', hand: tenpai13),
      ])).turns.single;
      expect(r.status, ReviewStatus.graded);
      expect(r.drawn, isNull);
      expect(r.shantenBefore, 0);
      // 보이는 패 없음: 1s 4 + 4s 4.
      expect(r.actual!.ukeire.total, 8);
      expect(r.grade, ReviewGrade.best);
    });

    test('뽑기에 손패는 있고 뽑은 패가 null 이면 버림 쪽으로', () {
      final r = reviewPaifu(pf([
        dr(0, null, tenpai13),
        d(0, '9m', hand: tenpai13),
      ])).turns.single;
      expect(r.status, ReviewStatus.graded);
      expect(r.actual!.ukeire.total, 8);
    });
  });

  group('등급 경계', () {
    test('최선: 9m 버림(16장), 같은 장수의 4s 버림도 최선 · 순위 1', () {
      final a = gradeCase(const [], '9m');
      expect(a.shantenBefore, 1);
      expect(a.options, hasLength(13));
      // 1p·4p·5s·8s 각 4장.
      expect(waits(a.actual!), [(t('1p'), 4), (t('4p'), 4), (t('5s'), 4), (t('8s'), 4)]);
      expect(a.best!.tile, t('9m'));
      expect((a.grade, a.rank, a.ukeireLoss), (ReviewGrade.best, 1, 0));

      final b = gradeCase(const [], '4s');
      // 동률이면 패 번호가 작은 9m 이 best. 4s 도 16장이라 손실 0 · 순위 1.
      expect(b.best!.tile, t('9m'));
      expect(b.actual!.tile, t('4s'));
      expect(b.actual!.ukeire.total, 16);
      expect((b.grade, b.rank, b.ukeireLoss), (ReviewGrade.best, 1, 0));
    });

    test('보이는 패 없음: 7s 버림 12/16 — 손실 4, 400 ≤ 30×16 → inaccuracy, 순위 3', () {
      final r = gradeCase(const [], '7s');
      expect(waits(r.actual!), [(t('1p'), 4), (t('4p'), 4), (t('5s'), 4)]);
      expect(r.best!.ukeire.total, 16);
      expect(r.ukeireLoss, 4);
      expect(r.shantenLoss, 0);
      // 9m·4s 둘이 엄밀히 낫다.
      expect(r.rank, 3);
      expect(r.grade, ReviewGrade.inaccuracy);
    });

    test('good 경계: 1p·8s 셋씩 보임 → 최선 10(1+4+4+1), 7s 9 — 손실 1, 100 ≤ 10×10', () {
      const river = ['1p', '1p', '1p', '8s', '8s', '8s'];
      final r = gradeCase(river, '7s');
      expect((r.best!.ukeire.total, r.actual!.ukeire.total, r.ukeireLoss), (10, 9, 1));
      expect(r.grade, ReviewGrade.good);
      expect(r.rank, 3);
      // 문턱을 9% 로 낮추면 100 > 90 → inaccuracy.
      expect(gradeCase(river, '7s', th: const ReviewThresholds(goodPct: 9)).grade, ReviewGrade.inaccuracy);
    });

    test('inaccuracy 경계: 1p 넷·4p 하나·8s 하나 → 최선 10(0+3+4+3), 7s 7 — 손실 3, 300 ≤ 30×10', () {
      const river = ['1p', '1p', '1p', '1p', '4p', '8s'];
      final r = gradeCase(river, '7s');
      expect((r.best!.ukeire.total, r.actual!.ukeire.total, r.ukeireLoss), (10, 7, 3));
      expect(r.grade, ReviewGrade.inaccuracy);
      // 문턱을 29% 로 낮추면 300 > 290 → mistake.
      expect(gradeCase(river, '7s', th: const ReviewThresholds(inaccuracyPct: 29)).grade, ReviewGrade.mistake);
    });

    test('mistake: 1p 셋 보임 → 최선 13(1+4+4+4), 7s 9 — 손실 4, 400 > 30×13 = 390', () {
      const river = ['1p', '1p', '1p'];
      final r = gradeCase(river, '7s');
      expect((r.best!.ukeire.total, r.actual!.ukeire.total, r.ukeireLoss), (13, 9, 4));
      expect(r.grade, ReviewGrade.mistake);
      // 31% 면 400 ≤ 403 → inaccuracy.
      expect(gradeCase(river, '7s', th: const ReviewThresholds(inaccuracyPct: 31)).grade, ReviewGrade.inaccuracy);
    });

    test('blunder: 2p 버림은 2샹텐(3p·467s 에서 실마리 하나)', () {
      final r = gradeCase(const [], '2p');
      expect(r.actual!.shanten, 2);
      expect(r.best!.shanten, 1);
      expect(r.shantenLoss, 1);
      // 1샹텐 후보(9m·4s·7s)가 모두 낫다.
      expect(r.rank, greaterThan(3));
      expect(r.grade, ReviewGrade.blunder);
    });
  });

  group('리치', () {
    test('hero 리치 선언 버림은 graded, 그 뒤 버림은 forced', () {
      final p = pf([
        dr(0, '9m', tenpai13),
        d(0, '9m', hand: tenpai13, tsumogiri: true, riichi: true),
        d(1, '5z'),
        d(2, '6z'),
        d(3, '3z'),
        dr(0, '7z', tenpai13),
        d(0, '7z', hand: tenpai13, tsumogiri: true),
      ]);
      final r = reviewPaifu(p);
      expect(r.turns, hasLength(2));
      final a = r.turns[0];
      expect(a.riichiDeclared, isTrue);
      expect(a.status, ReviewStatus.graded);
      expect(a.grade, ReviewGrade.best);
      final b = r.turns[1];
      expect(b.turn, 2);
      expect(b.eventIndex, 6);
      expect(b.status, ReviewStatus.forced);
      expect(b.grade, isNull);
      // 숫자는 채운다: 7z 를 내야 텐파이 유지.
      expect(b.shantenBefore, 0);
      expect(b.actual!.tile, t('7z'));
      expect(b.best!.tile, t('7z'));
      expect((b.shantenLoss, b.ukeireLoss, b.rank), (0, 0, 1));
      // hero 자신의 리치는 리치 상대가 아니다.
      expect(b.riichiSeats, isEmpty);
      expect(b.genbutsu, isNull);
      expect(r.count(ReviewStatus.graded), 1);
      expect(r.count(ReviewStatus.forced), 1);
      expect(r.gradeCount(ReviewGrade.best), 1);
      expect(r.gradeCount(ReviewGrade.mistake), 0);
      expect(r.efficiencyPct, 100);
    });

    // 자리 1 리치. 5z 는 자리 1 이 리치 전에 버림(가), 6z 는 자리 2 가 자리 1 리치 **앞**에 버림(현물 아님),
    // 9m 은 자리 1 의 선언패(가), 7z·2z 는 리치 뒤 자리 2·3 이 버림(나).
    List<Map<String, dynamic>> oneRiichi(String discard) => [
          d(1, '5z'),
          d(2, '6z'),
          d(1, '9m', riichi: true),
          d(2, '7z'),
          d(3, '2z'),
          dr(0, '7z', defense13),
          d(0, discard, hand: minus([...defense13, '7z'], discard)),
        ];

    test('다른 자리 리치 중: defense, grade null, 현물 (가)·(나)', () {
      final r = reviewPaifu(pf(oneRiichi('5z'))).turns.single;
      expect(r.status, ReviewStatus.defense);
      expect(r.grade, isNull);
      expect(r.riichiSeats, [1]);
      expect(r.genbutsu, isTrue); // (가) 리치 전 자기 버림
      // 숫자는 채운다. 몸통 셋 + 외톨이 다섯 → 2샹텐, 외톨이를 내면 그대로 2샹텐.
      expect(r.shantenBefore, 2);
      expect(r.actual!.tile, t('5z'));
      expect(r.shantenLoss, 0);
      expect(r.options, isNotEmpty);
      // 손에 있는 9m·2z·5z·7z 가 현물, 6z 는 아님.
      expect(r.safeTiles, [t('9m'), t('2z'), t('5z'), t('7z')]);

      expect(reviewPaifu(pf(oneRiichi('7z'))).turns.single.genbutsu, isTrue); // (나) 리치 뒤 남의 버림
      expect(reviewPaifu(pf(oneRiichi('9m'))).turns.single.genbutsu, isTrue); // 선언패
      expect(reviewPaifu(pf(oneRiichi('6z'))).turns.single.genbutsu, isFalse); // 리치 앞 남의 버림
      expect(reviewPaifu(pf(oneRiichi('1m'))).turns.single.genbutsu, isFalse);
    });

    // 자리 1·3 리치. 자리 1 현물: 5z·9m(가) + 7z·2z(나). 자리 3 현물: 9m·2z(가), 리치 뒤 버림은 아직 없음.
    List<Map<String, dynamic>> twoRiichi(String discard) => [
          d(3, '9m'),
          d(1, '5z'),
          d(1, '9m', riichi: true),
          d(2, '7z'),
          d(3, '2z', riichi: true),
          dr(0, '7z', defense13),
          d(0, discard, hand: minus([...defense13, '7z'], discard)),
        ];

    test('리치 자리 둘: 모두에게 현물이어야 genbutsu', () {
      final r = reviewPaifu(pf(twoRiichi('5z'))).turns.single;
      expect(r.status, ReviewStatus.defense);
      expect(r.riichiSeats, [1, 3]);
      expect(r.genbutsu, isFalse); // 5z 는 자리 1 에게만
      expect(r.safeTiles, [t('9m'), t('2z')]);
      expect(reviewPaifu(pf(twoRiichi('7z'))).turns.single.genbutsu, isFalse); // 자리 1 에게만
      expect(reviewPaifu(pf(twoRiichi('2z'))).turns.single.genbutsu, isTrue); // 자리 3 선언패 = 자리 1 리치 뒤 버림
      expect(reviewPaifu(pf(twoRiichi('9m'))).turns.single.genbutsu, isTrue);
    });

    test('손패 모름: unknownHand 이어도 riichiSeats·genbutsu 는 채움, hero 버림도 (나) 에 든다', () {
      final p = pf([
        d(1, '1m', riichi: true),
        d(2, '3m'),
        dr(0, null, null),
        d(0, '4z'), // 리치 뒤 hero 첫 4z — 아직 현물 아님
        d(1, '5m', tsumogiri: true),
        d(2, '6m'),
        d(3, '7m'),
        dr(0, null, null),
        d(0, '4z'), // 앞서 hero 가 리치 뒤에 4z 를 냈으니 현물
        d(1, '8m', tsumogiri: true),
        d(2, '9m'),
        d(3, '9p'),
        dr(0, null, null),
        d(0, '3m'), // 리치 뒤 자리 2 가 버린 3m
      ]);
      final r = reviewPaifu(p);
      expect(r.turns, hasLength(3));
      for (final x in r.turns) {
        expect(x.status, ReviewStatus.unknownHand);
        expect(x.riichiSeats, [1]);
        expect(x.options, isEmpty);
        expect(x.actual, isNull);
        expect(x.best, isNull);
        expect(x.shantenBefore, isNull);
        expect(x.rank, isNull);
        expect(x.grade, isNull);
        expect(x.safeTiles, isEmpty);
      }
      expect([for (final x in r.turns) x.genbutsu], [false, true, true]);
      expect([for (final x in r.turns) x.turn], [1, 2, 3]);
      expect(r.count(ReviewStatus.unknownHand), 3);
      expect(r.efficiencyPct, isNull);
    });
  });

  group('어긋난 기록', () {
    test('뽑기 쪽과 버림 쪽이 다름', () {
      final r = reviewPaifu(pf([
        dr(0, '9m', tenpai13),
        d(0, '9m', hand: h('223m456p789s23s11z')),
      ])).turns.single;
      expect(r.status, ReviewStatus.inconsistent);
      expect(r.options, isEmpty);
      expect(r.grade, isNull);
      expect(r.riichiSeats, isEmpty);
    });

    test('장수가 틀림(뽑기 전 12장)', () {
      final r = reviewPaifu(pf([
        dr(0, '9m', h('23m456p789s23s11z')),
        d(0, '9m'),
      ])).turns.single;
      expect(r.status, ReviewStatus.inconsistent);
    });

    test('버린 패가 손패에 없음', () {
      final r = reviewPaifu(pf([
        dr(0, '9m', tenpai13),
        d(0, '5z'),
      ])).turns.single;
      expect(r.status, ReviewStatus.inconsistent);
    });

    test('한 종류가 5장', () {
      final r = reviewPaifu(pf([
        dr(0, '1z', h('123m456p789s1111z')),
        d(0, '9s'),
      ])).turns.single;
      expect(r.status, ReviewStatus.inconsistent);
    });

    test('탁자를 못 쌓는 기록(울린 자리가 범위 밖)에도 예외 없이 버림마다 inconsistent', () {
      final p = pf([
        dr(0, '9m', tenpai13),
        d(0, '9m', hand: tenpai13),
        call(2, 'pon', 7, ['9m', '9m', '9m']),
        d(2, '1z'),
        dr(0, '5z', tenpai13),
        d(0, '5z', hand: tenpai13),
      ]);
      final r = reviewPaifu(p);
      expect(r.turns, hasLength(2));
      expect(r.count(ReviewStatus.inconsistent), 2);
      expect([for (final x in r.turns) x.eventIndex], [1, 5]);
    });
  });

  group('울기·화료 형태·쯔모 끝', () {
    test('hero 퐁 뒤 버림(울기 1, 11장): 123m 456p 23s 55s 9m + 퐁 1z → 9m 버리고 1s·4s 텐파이', () {
      final p = pf([
        d(3, '1z'),
        call(0, 'pon', 3, ['1z', '1z', '1z'], hand: h('123m456p23s55s9m')),
        d(0, '9m', hand: h('123m456p23s55s')),
      ]);
      final r = reviewPaifu(p).turns.single;
      expect(r.melds, 1);
      expect(r.status, ReviewStatus.graded);
      expect(r.drawn, isNull);
      expect(r.shantenBefore, 0);
      expect(r.options, hasLength(10));
      expect(r.best!.tile, t('9m'));
      expect(waits(r.actual!), [(t('1s'), 4), (t('4s'), 4)]);
      expect((r.shantenLoss, r.ukeireLoss, r.rank, r.grade), (0, 0, 1, ReviewGrade.best));
    });

    test('complete: 화료 형태(123m 456p 789s 234s 11z)에서 4s 버림', () {
      final r = reviewPaifu(pf([
        dr(0, '4s', tenpai13),
        d(0, '4s', hand: tenpai13, tsumogiri: true),
      ])).turns.single;
      expect(r.status, ReviewStatus.complete);
      expect(r.shantenBefore, -1);
      expect(r.grade, isNull);
      // 몸통 하나를 헐면 텐파이: 양면 쪽은 7장(버린 패 한 장이 보임 → 3 + 4)이 가장 많고, 동률이면 패 번호가 작은 1m 버림이 best.
      expect(r.actual!.shanten, 0);
      expect(r.actual!.ukeire.total, 7);
      expect(r.best!.tile, t('1m'));
      expect(r.best!.ukeire.total, 7);
      expect((r.shantenLoss, r.ukeireLoss, r.rank), (0, 0, 1));
    });

    test('쯔모 화료로 끝난 판: 마지막 뽑기는 평가 건이 아님, turn·eventIndex', () {
      final p = pf([
        dr(0, null, null),
        d(0, '9m'),
        d(1, '1z'),
        d(2, '2z'),
        d(3, '3z'),
        dr(0, '8m', null),
        d(0, '8m', tsumogiri: true),
        d(1, '4z'),
        d(2, '5z'),
        d(3, '6z'),
        dr(0, '5s', null),
      ], result: {
        'type': 'tsumo',
        'winner': 0,
        'loser': null,
        'win_tile': '5s',
        'hand': null,
      });
      final r = reviewPaifu(p);
      expect(r.turns, hasLength(2));
      expect([for (final x in r.turns) x.turn], [1, 2]);
      expect([for (final x in r.turns) x.eventIndex], [1, 6]);
      expect(r.turns[1].drawn, PaifuTile(t('8m')));
      expect(r.turns[1].tsumogiri, isTrue);
      expect(r.turns[0].tsumogiri, isNull);
    });
  });

  group('PaifuReview 모음', () {
    test('count · gradeCount', () {
      final r = PaifuReview([
        synth(ReviewStatus.graded, g: ReviewGrade.best, actual: 8, best: 8),
        synth(ReviewStatus.graded, g: ReviewGrade.mistake, actual: 4, best: 8),
        synth(ReviewStatus.defense, actual: 1, best: 8),
        synth(ReviewStatus.unknownHand),
      ]);
      expect(r.count(ReviewStatus.graded), 2);
      expect(r.count(ReviewStatus.defense), 1);
      expect(r.count(ReviewStatus.forced), 0);
      expect(r.gradeCount(ReviewGrade.best), 1);
      expect(r.gradeCount(ReviewGrade.mistake), 1);
      expect(r.gradeCount(ReviewGrade.blunder), 0);
      // graded 만: (1 + 0.5) / 2 = 75. defense 는 안 셈.
      expect(r.efficiencyPct, 75);
    });

    test('efficiencyPct: 반올림 · blunder 0 · 최선 0장이면 100 · graded 없으면 null', () {
      expect(const PaifuReview([]).efficiencyPct, isNull);
      expect(PaifuReview([synth(ReviewStatus.forced, actual: 1, best: 2)]).efficiencyPct, isNull);
      // 1/8 = 12.5 → 13(반은 올림).
      expect(PaifuReview([synth(ReviewStatus.graded, g: ReviewGrade.mistake, actual: 1, best: 8)]).efficiencyPct, 13);
      // (2/3 + 0 + 1) / 3 = 55.56 → 56. blunder 는 장수와 상관없이 0, best 0장은 100.
      expect(
        PaifuReview([
          synth(ReviewStatus.graded, g: ReviewGrade.inaccuracy, actual: 2, best: 3),
          synth(ReviewStatus.graded, g: ReviewGrade.blunder, actual: 5, best: 8),
          synth(ReviewStatus.graded, g: ReviewGrade.best, actual: 0, best: 0),
        ]).efficiencyPct,
        56,
      );
      // 2/3 = 66.67 → 67.
      expect(PaifuReview([synth(ReviewStatus.graded, g: ReviewGrade.mistake, actual: 2, best: 3)]).efficiencyPct, 67);
    });
  });

  group('실제 패보', () {
    final dir = Directory('assets/paifu');
    final all = {
      if (dir.existsSync())
        for (final f in dir.listSync())
          if (f is File && f.path.endsWith('.json'))
            f.uri.pathSegments.last: Paifu.fromJson(jsonDecode(f.readAsStringSync()) as Map<String, dynamic>),
    };

    test('10판 모두 예외 없이 돌고, 평가 건 수 = hero 버림 수', () {
      expect(all.length, greaterThanOrEqualTo(10));
      for (final p in all.values) {
        final r = reviewPaifu(p);
        final heroDiscards = p.events.where((e) => e.seat == p.hero && e.type == PaifuEventType.discard).length;
        expect(r.turns, hasLength(heroDiscards), reason: p.id);
        expect([for (final x in r.turns) x.turn], [for (var i = 1; i <= heroDiscards; i++) i], reason: p.id);
      }
    });

    test('손패 없는 판은 전부 unknownHand', () {
      final noHands = all.values.where((p) => !p.hasHeroHands).toList();
      // 11-20: r13 · r15 · r16 · L16(텐파이 공개자) · r14(2순 정답) · r18(Opus 읽기)에 손패를 넣어 손패 없는 판은 r20 하나.
      expect(noHands.length, greaterThanOrEqualTo(1));
      for (final p in noHands) {
        final r = reviewPaifu(p);
        expect(r.count(ReviewStatus.unknownHand), r.turns.length, reason: p.id);
        expect(r.efficiencyPct, isNull, reason: p.id);
      }
    });

    test('손패 있는 판: 평가가 나오고, 숫자 있는 차례는 actual ∈ options · best = options.first · 샹텐 손실 0 또는 1', () {
      final withHands = all.values.where((p) => p.hasHeroHands).toList();
      expect(withHands.length, greaterThanOrEqualTo(10));
      var forced = 0;
      for (final p in withHands) {
        final r = reviewPaifu(p);
        // 녹화 전 차례(첫 1순 — r15 · r16 은 없음)만 손패 null, 그 뒤는 평가된다.
        final nullHand = p.events.where((e) => e.seat == p.hero && e.type == PaifuEventType.discard && e.hand == null).length;
        expect(r.count(ReviewStatus.unknownHand), nullHand, reason: p.id);
        expect(r.count(ReviewStatus.graded), greaterThan(0), reason: p.id);
        expect(r.efficiencyPct, isNotNull, reason: p.id);
        forced += r.count(ReviewStatus.forced);
        for (final x in r.turns) {
          if (x.status case ReviewStatus.graded || ReviewStatus.forced || ReviewStatus.defense) {
            expect(x.options, contains(same(x.actual)), reason: '${p.id} ${x.turn}');
            expect(x.actual!.tile, x.discard.tile, reason: '${p.id} ${x.turn}');
            expect(identical(x.best, x.options.first), isTrue, reason: '${p.id} ${x.turn}');
            expect(x.shantenLoss, anyOf(0, 1), reason: '${p.id} ${x.turn}');
            expect(x.rank, greaterThanOrEqualTo(1), reason: '${p.id} ${x.turn}');
            expect(x.grade == null, x.status != ReviewStatus.graded, reason: '${p.id} ${x.turn}');
          }
        }
      }
      // 네 판 모두 hero 가 리치했다.
      expect(forced, greaterThan(0));
    });
  });
}
