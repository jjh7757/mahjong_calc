// 복기 화면 글(lib/paifu/review_sentence.dart) — 설계서 docs/paifu_review_ui_design_1121.md 3-3 · 3-4 · 3-8.
// 기대 문장은 설계서의 문장 틀에 손으로 값을 넣어 적었다(구현 결과를 옮겨 적지 않음).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/efficiency.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_sentence.dart';

int t(String code) => Tiles.parse(code);

/// 후보 하나: [tile] 을 버리면 샹텐 [sh], 유효패 (패, 남은 장수) 목록.
DiscardOption opt(String tile, int sh, List<(String, int)> u) =>
    DiscardOption(t(tile), sh, Ukeire(sh, [for (final (c, n) in u) UkeireTile(t(c), n)]));

/// 유효패 합이 [total] 인 후보(1종 [total] 장으로 둔다 — 문장은 합만 쓴다).
DiscardOption optN(String tile, int sh, int total) => opt(tile, sh, [('7z', total)]);

TurnReview graded(
  ReviewGrade g,
  String discard,
  List<DiscardOption> options, {
  bool red = false,
}) {
  final actual = options.firstWhere((o) => o.tile == t(discard));
  final best = options.first;
  return TurnReview(
    eventIndex: 10,
    turn: 6,
    discard: PaifuTile(t(discard), red: red),
    drawn: null,
    tsumogiri: null,
    riichiDeclared: false,
    status: ReviewStatus.graded,
    melds: 0,
    shantenBefore: best.shanten,
    options: options,
    actual: actual,
    best: best,
    shantenLoss: actual.shanten - best.shanten,
    ukeireLoss: best.ukeire.total - actual.ukeire.total,
    rank: 1,
    grade: g,
  );
}

TurnReview bare(ReviewStatus s, String discard, {bool? genbutsu, bool red = false, List<DiscardOption>? options}) =>
    TurnReview(
      eventIndex: 10,
      turn: 9,
      discard: PaifuTile(t(discard), red: red),
      drawn: null,
      tsumogiri: true,
      riichiDeclared: false,
      status: s,
      melds: 0,
      genbutsu: genbutsu,
      riichiSeats: genbutsu == null ? const [] : const [2],
      options: options ?? const [],
      best: options?.first,
      actual: options?.firstWhere((o) => o.tile == t(discard)),
    );

void main() {
  group('낱말', () {
    test('조사 을/를: 받침 있으면 을, 없으면 를', () {
      expect(withEul('3만'), '3만을');
      expect(withEul('9통'), '9통을');
      expect(withEul('1삭'), '1삭을');
      expect(withEul('서'), '서를');
      expect(withEul('동'), '동을');
      expect(withEul('발'), '발을');
    });

    test('점수 쉼표', () {
      expect(formatPoints(500), '500');
      expect(formatPoints(8000), '8,000');
      expect(formatPoints(12000), '12,000');
      expect(formatPoints(1000000), '1,000,000');
    });

    test('샹텐 · 유효패/대기', () {
      expect(shantenText(-1), '화료 형태');
      expect(shantenText(0), '텐파이');
      expect(shantenText(2), '2샹텐');
      expect(ukeireWord(0), '대기');
      expect(ukeireWord(1), '유효패');
    });
  });

  group('3-8 문장 틀 열 가지 + 어긋남', () {
    test('① 최선: 제목 "최선입니다" · 비교 한 줄 · 구석 비움', () {
      final r = graded(ReviewGrade.best, '3m', [
        opt('3m', 1, [('2m', 4), ('5m', 4), ('3s', 3), ('4s', 2), ('8s', 2)]),
        optN('4m', 1, 10),
      ]);
      expect(reviewTitle(r), '3만 버림 · 최선입니다');
      expect(reviewCompareLines(r), ['내 버림 3만 · 유효패 15장']);
      expect(reviewCorner(r), isNull);
      expect(reviewSentence(r), '유효패가 가장 많은 버림입니다.');
    });

    test('① 최선(텐파이): "유효패" 대신 "대기"', () {
      final r = graded(ReviewGrade.best, '3s', [optN('3s', 0, 3), optN('3m', 1, 35)]);
      expect(reviewCompareLines(r), ['내 버림 3삭 · 대기 3장']);
      expect(reviewSentence(r), '대기가 가장 많은 버림입니다.');
    });

    test('② 좋음: 최선(○)과 N장 차이', () {
      final r = graded(ReviewGrade.good, '2z', [optN('8m', 2, 37), optN('2z', 2, 36)]);
      expect(reviewTitle(r), '남 버림 · 좋음');
      expect(reviewCompareLines(r), ['내 버림 남 · 유효패 36장', '최선 8만 · 유효패 37장']);
      expect(reviewCorner(r), '−1장');
      expect(reviewSentence(r), '최선(8만)과 1장 차이로 거의 같습니다.');
    });

    test('③ 부정확: ○을 버렸다면 유효패가 N장 더', () {
      final r = graded(ReviewGrade.inaccuracy, '1s', [optN('3s', 1, 12), optN('1s', 1, 10)]);
      expect(reviewTitle(r), '1삭 버림 · 부정확');
      expect(reviewCompareLines(r), ['내 버림 1삭 · 유효패 10장', '최선 3삭 · 유효패 12장']);
      expect(reviewCorner(r), '−2장');
      expect(reviewSentence(r), '3삭을 버렸다면 유효패가 2장 더 많았습니다.');
    });

    test('④ 실수 + 동률 최선 둘: "3만(또는 3삭)"', () {
      final r = graded(ReviewGrade.mistake, '4m', [optN('3m', 1, 15), optN('3s', 1, 15), optN('5s', 1, 13), optN('4m', 1, 10)]);
      expect(reviewTitle(r), '4만 버림 · 실수');
      expect(bestTiles(r), [t('3m'), t('3s')]);
      expect(reviewCompareLines(r), ['내 버림 4만 · 유효패 10장', '최선 3만(또는 3삭) · 유효패 15장']);
      expect(reviewCorner(r), '−5장');
      expect(reviewSentence(r), '3만(또는 3삭)을 버렸다면 유효패가 5장 더 많았습니다. 차이가 큽니다.');
    });

    test('④ 실수(텐파이) · 받침 없는 패 "서를" · 동률 셋이면 둘까지', () {
      final tenpai = graded(ReviewGrade.mistake, '7m', [optN('8m', 0, 5), optN('7m', 0, 3)]);
      expect(reviewSentence(tenpai), '8만을 버렸다면 대기가 2장 더 많았습니다. 차이가 큽니다.');
      expect(reviewCompareLines(tenpai), ['내 버림 7만 · 대기 3장', '최선 8만 · 대기 5장']);

      final west = graded(ReviewGrade.inaccuracy, '9p', [optN('3z', 1, 10), optN('9p', 1, 8)]);
      expect(reviewSentence(west), '서를 버렸다면 유효패가 2장 더 많았습니다.');

      final three = graded(ReviewGrade.mistake, '1p', [optN('2s', 1, 11), optN('5s', 1, 11), optN('8s', 1, 11), optN('1p', 1, 6)]);
      expect(bestLabel(three), '2삭(또는 5삭)');
      expect(bestLabel(three, paren: false), '2삭 또는 5삭');
    });

    test('⑤ 큰 실수: 샹텐이 N 늘었습니다 · 구석 "샹텐 후퇴" · 비교는 샹텐', () {
      final r = graded(ReviewGrade.blunder, '1p', [optN('6m', 1, 8), optN('9p', 1, 8), optN('1p', 2, 51)]);
      expect(reviewTitle(r), '1통 버림 · 큰 실수');
      expect(reviewCompareLines(r), ['내 버림 1통 · 2샹텐', '최선 6만(또는 9통) · 1샹텐']);
      expect(reviewCorner(r), '샹텐 후퇴');
      expect(reviewSentence(r), '샹텐이 1 늘었습니다. 6만(또는 9통)을 버리면 그대로였습니다.');

      final tenpai = graded(ReviewGrade.blunder, '9m', [optN('8m', 0, 4), optN('9m', 1, 25)]);
      expect(reviewCompareLines(tenpai), ['내 버림 9만 · 1샹텐', '최선 8만 · 텐파이']);

      final two = graded(ReviewGrade.blunder, '5p', [optN('5m', 1, 8), optN('5p', 3, 60)]);
      expect(reviewCorner(two), '2샹텐 후퇴');
      expect(reviewSentence(two), '샹텐이 2 늘었습니다. 5만을 버리면 그대로였습니다.');
    });

    test('⑥ 리치 중(forced) · 적5 이름', () {
      final r = bare(ReviewStatus.forced, '5s', red: true);
      expect(reviewTitle(r), '적5삭 버림 · 리치 중');
      expect(reviewCompareLines(r), isEmpty);
      expect(reviewCorner(r), isNull);
      expect(reviewSentence(r), '리치 중이라 뽑은 패를 그대로 버립니다.');
    });

    test('⑦ 수비: 현물 / 현물 아님 / 모름', () {
      expect(reviewSentence(bare(ReviewStatus.defense, '9p', genbutsu: true)), '다른 자리가 리치 중입니다. 버린 패는 현물입니다.');
      expect(reviewSentence(bare(ReviewStatus.defense, '9p', genbutsu: false)), '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다.');
      expect(reviewSentence(bare(ReviewStatus.defense, '9p')), '다른 자리가 리치 중입니다. 현물인지 판단하지 않습니다.');
      // 수비 걸음은 숫자가 있어도 두 줄 비교 · 구석 숫자가 없다.
      final withNumbers = bare(ReviewStatus.defense, '9p', genbutsu: false, options: [optN('1m', 1, 10), optN('9p', 1, 6)]);
      expect(reviewCompareLines(withNumbers), isEmpty);
      expect(reviewCorner(withNumbers), isNull);
      expect(reviewTitle(withNumbers), '9통 버림 · 수비');
    });

    test('⑧ 화료 형태 · ⑨ 손패 모름 · ⑩ 짐작 손패 · 어긋남', () {
      expect(reviewSentence(bare(ReviewStatus.complete, '1m')), '화료 형태에서 버렸습니다. 화료하지 않은 까닭은 판단하지 않습니다.');
      expect(reviewSentence(bare(ReviewStatus.unknownHand, '1m')), '이 순은 손패 기록이 없어 평가하지 않습니다.');
      expect(reviewSentence(bare(ReviewStatus.guessed, '4z')), '이 순의 손패는 짐작이라 평가하지 않습니다.');
      expect(reviewTitle(bare(ReviewStatus.guessed, '4z')), '북 버림 · 짐작 손패');
      expect(reviewTitle(bare(ReviewStatus.unknownHand, '4z')), '북 버림 · 손패 모름');
      expect(reviewSentence(bare(ReviewStatus.inconsistent, '1m')), '이 순은 손패 기록이 앞뒤가 맞지 않아 평가하지 않습니다.');
      for (final s in [ReviewStatus.complete, ReviewStatus.unknownHand, ReviewStatus.guessed, ReviewStatus.inconsistent]) {
        expect(reviewCompareLines(bare(s, '1m')), isEmpty);
        expect(reviewCorner(bare(s, '1m')), isNull);
      }
    });
  });

  group('최선 보기 막대 줄 · 배울 장면 손실', () {
    test('막대를 누르면: "3만을 버리면 유효패: 2만 5만 3삭 4삭 8삭 (15장)", 남은 0장은 빼고, 후퇴 후보는 샹텐을 앞에', () {
      final r = graded(ReviewGrade.mistake, '4m', [
        opt('3m', 1, [('2m', 4), ('5m', 4), ('3s', 3), ('4s', 2), ('8s', 2), ('9s', 0)]),
        opt('4m', 1, [('3m', 2), ('3s', 3), ('4s', 3), ('8s', 2)]),
        opt('1p', 2, [('2p', 3)]),
      ]);
      expect(barInfoLine(r, t('3m')), '3만을 버리면 유효패: 2만 5만 3삭 4삭 8삭 (15장)');
      expect(barInfoLine(r, t('1p')), '1통을 버리면 2샹텐 · 유효패: 2통 (3장)');
      expect(barInfoLine(r, t('7z')), isNull); // 후보에 없는 패
    });

    test('lessonLossText', () {
      expect(lessonLossText(graded(ReviewGrade.mistake, '4m', [optN('3m', 1, 15), optN('4m', 1, 10)])), '유효패 −5장');
      expect(lessonLossText(graded(ReviewGrade.mistake, '7m', [optN('8m', 0, 5), optN('7m', 0, 3)])), '대기 −2장');
      expect(lessonLossText(graded(ReviewGrade.blunder, '1p', [optN('6m', 1, 8), optN('1p', 2, 51)])), '샹텐 후퇴');
    });
  });

  group('3-4 단계 문장', () {
    test('배패 · 리치(내 · 남) · 끝', () {
      expect(stageSentence(const ReviewStage(kind: ReviewStageKind.start, step: 0, startShanten: 0)), '배패 텐파이였습니다.');
      expect(stageSentence(const ReviewStage(kind: ReviewStageKind.start, step: 0, startShanten: 3)), '배패는 3샹텐이었습니다.');
      expect(
        stageSentence(const ReviewStage(kind: ReviewStageKind.riichi, step: 38, seat: 1, riichiTurn: 8, afterRiichi: 2)),
        '8순에 리치했습니다. 그 뒤 2번은 뽑은 패를 그대로 버렸습니다.',
      );
      expect(stageSentence(const ReviewStage(kind: ReviewStageKind.riichi, step: 38, seat: 1, riichiTurn: 8)),
          '8순에 리치했습니다.');
      expect(
        stageSentence(const ReviewStage(kind: ReviewStageKind.riichi, step: 20, seat: 2), seatLabel: (s) => '서 다'),
        '서 다 자리가 리치했습니다. 여기부터 수비 판단은 평가하지 않습니다.',
      );
      const end = ReviewStage(kind: ReviewStageKind.end, step: 52);
      expect(stageSentence(end, result: '론 · 8,000점', efficiencyPct: 94), '론 · 8,000점\n이 판 패효율 94');
      expect(stageSentence(end, result: '유국'), '유국\n이 판은 평가한 버림이 없습니다');
    });

    test('끝 결과 한 줄', () {
      const ron = PaifuResult(type: 'ron', winner: 1, loser: 2);
      expect(endResultText(ron, points: 8000), '론 · 8,000점');
      expect(endResultText(ron), '론');
      expect(endResultText(const PaifuResult(type: 'tsumo', winner: 1), points: 3900), '쯔모 · 3,900점');
      expect(endResultText(const PaifuResult(type: 'draw')), '유국');
      expect(endResultText(null), '결과 기록 없음');
    });
  });

  group('reviewStages', () {
    Map<String, dynamic> base(List<Map<String, dynamic>> events, {List<String>? start, Map<String, dynamic>? result}) => {
          'version': 1,
          'id': 's',
          'round': '동1국',
          'dealer': 0,
          'hero': 1,
          'names': ['가', '나', '다', '라'],
          'start_hand': ?start,
          'events': events,
          'result': ?result,
        };
    Map<String, dynamic> d(int seat, String tile, {bool riichi = false}) =>
        {'type': 'discard', 'seat': seat, 'tile': tile, 'tsumogiri': null, 'riichi': riichi};

    test('start_hand 텐파이(123456789m 11p 23s) → 배패 0, 남의 리치는 첫 번째만, 내 리치 · 끝', () {
      final p = Paifu.fromJson(base(
        [
          d(0, '9s'), // 걸음 1
          d(1, '7z', riichi: true), // 2: 내 리치(1번째 버림)
          d(2, '1s', riichi: true), // 3: 남의 첫 리치
          d(3, '2s', riichi: true), // 4: 남의 둘째 리치 — 단계 아님
          d(0, '3s'), // 5
          d(1, '4s'), // 6: 리치 뒤 1번
        ],
        start: ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '3s'],
        result: {'type': 'draw'},
      ));
      final s = reviewStages(p);
      expect([for (final x in s) (x.kind, x.step)], [
        (ReviewStageKind.start, 0),
        (ReviewStageKind.riichi, 2),
        (ReviewStageKind.riichi, 3),
        (ReviewStageKind.end, 7),
      ]);
      expect(s[0].startShanten, 0);
      expect(s[1].heroRiichi, isTrue);
      expect(s[1].riichiTurn, 1);
      expect(s[1].afterRiichi, 1);
      expect(s[2].heroRiichi, isFalse);
      expect(s[2].seat, 2);
    });

    test('첫 뽑기의 손패(123456789m 11p 2s 7z, 1샹텐)로 배패 — 짐작이면 건너뜀, 손패 없으면 건너뜀', () {
      Map<String, dynamic> draw({bool guess = false}) => {
            'type': 'draw',
            'seat': 1,
            'tile': '5z',
            'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '7z'],
            'guess': ?(guess ? true : null),
          };
      final ok = reviewStages(Paifu.fromJson(base([d(0, '9s'), draw(), d(1, '5z')])));
      expect(ok.first.kind, ReviewStageKind.start);
      expect(ok.first.startShanten, 1);
      expect(stageSentence(ok.first), '배패는 1샹텐이었습니다.');

      final guessed = reviewStages(Paifu.fromJson(base([d(0, '9s'), draw(guess: true), d(1, '5z')])));
      expect(guessed.any((x) => x.kind == ReviewStageKind.start), isFalse);

      final noHand = reviewStages(Paifu.fromJson(base([d(0, '9s'), d(1, '5z')])));
      expect(noHand.any((x) => x.kind == ReviewStageKind.start), isFalse);
      // 끝은 늘 마지막 걸음(결과가 없으면 마지막 사건 뒤).
      expect(noHand.last.kind, ReviewStageKind.end);
      expect(noHand.last.step, 2);
    });
  });

  group('예시 11판(assets/paifu) — 7절', () {
    final files = Directory('assets/paifu').listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));

    test('11판 전부에서 문장이 만들어지고, 문장 속 숫자 · 패 이름이 평가 값과 같다', () {
      expect(files.length, 11);
      var mismatches = 0;
      var checked = 0;
      for (final f in files) {
        final p = Paifu.fromJson(jsonDecode(f.readAsStringSync()) as Map<String, dynamic>);
        final r = reviewPaifu(p);
        for (final x in r.turns) {
          final s = reviewSentence(x);
          expect(s, isNotEmpty);
          expect(reviewTitle(x), startsWith('${tileText(x.discard)} 버림 · '));
          if (x.status != ReviewStatus.graded) continue;
          checked++;
          final b = x.best!;
          final a = x.actual!;
          final bestName = Tiles.name(b.tile);
          final lines = reviewCompareLines(x);
          var ok = true;
          switch (x.grade!) {
            case ReviewGrade.best:
              ok = lines.length == 1 && lines[0].endsWith('${a.ukeire.total}장');
            case ReviewGrade.good:
              ok = s.contains('최선($bestName') && s.contains('${x.ukeireLoss}장 차이') && lines.length == 2;
            case ReviewGrade.inaccuracy:
            case ReviewGrade.mistake:
              ok = s.startsWith(bestName) &&
                  s.contains('${x.ukeireLoss}장 더 많았습니다') &&
                  lines[0].endsWith('${a.ukeire.total}장') &&
                  lines[1].endsWith('${b.ukeire.total}장') &&
                  reviewCorner(x) == '−${x.ukeireLoss}장';
            case ReviewGrade.blunder:
              ok = s.startsWith('샹텐이 ${x.shantenLoss} 늘었습니다. $bestName') &&
                  lines[0].endsWith(shantenText(a.shanten)) &&
                  lines[1].endsWith(shantenText(b.shanten));
          }
          if (!ok) mismatches++;
        }
      }
      expect(checked, greaterThan(50));
      expect(mismatches, 0);
    });
  });
}
