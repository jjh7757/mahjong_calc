import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_chat.dart';

/// 예시 11판 전부(assets/paifu).
const games = [
  'L16_135321',
  'r11_130921',
  'r12_131655',
  'r13_132644',
  'r14_133610',
  'r15_134151',
  'r16_135321',
  'r17_140450',
  'r18_141259',
  'r19_142013',
  'r20_143236',
];

Paifu load(String id) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$id.json').readAsStringSync(encoding: utf8)) as Map<String, dynamic>);

/// 엔진 리뷰는 한 판 수 초라 판마다 한 번만.
final _cache = <String, (Paifu, PaifuReview)>{};

(Paifu, PaifuReview) game(String id) => _cache.putIfAbsent(id, () {
      final p = load(id);
      return (p, reviewPaifu(p, withEngine: true));
    });

TurnReview turnOf(PaifuReview r, int n) => r.turns.firstWhere((t) => t.turn == n);

List<String> suggestedAt(String id, int? n) {
  final (p, r) = game(id);
  return suggestedQuestions(p, r, n == null ? null : turnOf(r, n));
}

const _handUnknown = {ReviewStatus.unknownHand, ReviewStatus.inconsistent, ReviewStatus.guessed};

void main() {
  group('questionTurns — 서버 review_agent.question_turns 와 같은 답(같은 예문을 파이썬으로 돌린 값)', () {
    const cases = <String, List<int>>{
      '6순에 4만': [6],
      '6 순': [6],
      '6  순': [], // \s? 는 한 칸까지
      '3번째': [3],
      '2차례': [2],
      '5턴': [5],
      '1순위': [],
      '6순 7순 6순': [6, 7],
      '숫자 없는 글': [],
      '10순위 6순': [6],
      '12순에 대해: 이 수': [12],
      '0순': [0],
      '06순': [6],
      '６순': [6], // 전각 숫자
      '6\t순': [6],
      '6\n순': [6],
      '3번 째': [],
      '1순위 2순위 3순': [3],
    };
    for (final e in cases.entries) {
      test(jsonEncode(e.key), () => expect(questionTurns(e.key), e.value));
    }
  });

  group('withTurnContext', () {
    test('차례 번호가 없으면 앞에 붙임(앞뒤 공백 뺌)', () {
      expect(withTurnContext('  이 수 어땠어?  ', 6), '6순에 대해: 이 수 어땠어?');
    });
    test('글에 차례 번호가 있으면 그대로', () {
      expect(withTurnContext('3순에 1통은?', 6), '3순에 1통은?');
      expect(withTurnContext(' 2번째 버림은? ', 6), '2번째 버림은?');
    });
    test('차례가 없으면 그대로', () => expect(withTurnContext(' 이 판 총평 ', null), '이 판 총평'));
    test('"1순위" 는 차례 번호가 아니라 붙임', () {
      expect(withTurnContext('1순위 후보는?', 4), '4순에 대해: 1순위 후보는?');
    });
  });

  group('suggestedQuestions — 예시 11판', () {
    test('모든 hero 차례와 null: 1~3개 · 300자 이하 · 차례 질문은 그 차례 번호만', () {
      var turnQuestions = 0;
      for (final id in games) {
        final (p, r) = game(id);
        for (final t in <TurnReview?>[...r.turns, null]) {
          final qs = suggestedQuestions(p, r, t);
          final where = '$id ${t?.turn}';
          expect(qs.length, inInclusiveRange(1, 3), reason: where);
          expect(qs.toSet().length, qs.length, reason: '$where 겹침');
          for (final q in qs) {
            expect(q.runes.length, lessThanOrEqualTo(reviewQuestionMax), reason: where);
            expect(q, isNot(contains('[')), reason: '$where 대괄호 없이');
            expect(q, isNot(contains('적5')), reason: '$where 적5 도 5');
            final turns = questionTurns(q);
            if (turns.isNotEmpty) {
              turnQuestions++;
              expect(t, isNotNull, reason: '$where 판 전체 질문에 차례 번호');
              expect(turns, [t!.turn], reason: '$where "$q"');
            }
          }
          if (t != null && _handUnknown.contains(t.status)) {
            expect(qs.every((q) => questionTurns(q).isEmpty), isTrue, reason: '$where 손패 모름');
          }
        }
      }
      expect(turnQuestions, greaterThan(0));
    });

    test('등급 낮음(실수): r19 6순', () {
      expect(suggestedAt('r19_142013', 6), ['6순에 4만 버린 게 왜 실수야?', '6순에 3만을 버렸으면 어떻게 됐어?']);
    });
    test('등급 낮음(부정확 — "이야", 최선 패가 자패 "백을"): L16 2순', () {
      expect(suggestedAt('L16_135321', 2), ['2순에 2통 버린 게 왜 부정확이야?', '2순에 백을 버렸으면 어떻게 됐어?']);
    });
    test('등급 낮음(큰 실수): r11 3순', () {
      expect(suggestedAt('r11_130921', 3), ['3순에 1통 버린 게 왜 큰 실수야?', '3순에 6만을 버렸으면 어떻게 됐어?']);
    });
    test('남 리치 차례(수비): L16 17순', () {
      expect(suggestedAt('L16_135321', 17), ['17순에 버린 4만 위험했어?', '17순에 뭘 버리면 제일 안전했어?']);
    });
    test('남 리치 + 내가 리치 중(forced): r11 10순 — "뭘 버리면" 은 빼고', () {
      expect(suggestedAt('r11_130921', 10), ['10순에 버린 중 위험했어?']);
    });
    test('리치 중 · 남 리치 없음: r13 10순 → 판 전체(남 리치 없는 판)', () {
      expect(suggestedAt('r13_132644', 10), ['이 판에서 제일 아까운 수는?', '이 판 총평 해 줘']);
    });
    test('최선: L16 3순 → 판 전체(남 리치 있는 판)', () {
      expect(suggestedAt('L16_135321', 3), ['이 판에서 제일 아까운 수는?', '이 판 총평 해 줘', '서 리치 뒤에 나는 어떻게 했어?']);
    });
    test('손패 모름(unknownHand): r20 1순', () {
      expect(turnOf(game('r20_143236').$2, 1).status, ReviewStatus.unknownHand);
      expect(suggestedAt('r20_143236', 1), ['이 판에서 제일 아까운 수는?', '이 판 총평 해 줘']);
    });
    test('짐작 손패(guessed): L16 1순', () {
      expect(turnOf(game('L16_135321').$2, 1).status, ReviewStatus.guessed);
      expect(suggestedAt('L16_135321', 1), ['이 판에서 제일 아까운 수는?', '이 판 총평 해 줘', '서 리치 뒤에 나는 어떻게 했어?']);
    });
    test('내 버림이 아닌 걸음(null): r12 — 북 리치', () {
      expect(suggestedAt('r12_131655', null), ['이 판에서 제일 아까운 수는?', '이 판 총평 해 줘', '북 리치 뒤에 나는 어떻게 했어?']);
    });
    test('내 버림이 아닌 걸음(null): r19 — 남 리치 없음', () {
      expect(suggestedAt('r19_142013', null), ['이 판에서 제일 아까운 수는?', '이 판 총평 해 줘']);
    });
  });

  group('historyPayload', () {
    test('5쌍 → 뒤 4쌍', () {
      final all = [for (var i = 1; i <= 5; i++) ReviewExchange('q$i', 'a$i')];
      expect(historyPayload(all), [
        for (var i = 2; i <= 5; i++) {'q': 'q$i', 'a': 'a$i'},
      ]);
    });
    test('1001자 → 1000자(코드 포인트 — 한글 · 그림 글자)', () {
      final ko = '가' * 1001;
      final emoji = '\u{1F004}' * 1001; // 마작 패 그림 글자(UTF-16 두 칸)
      final out = historyPayload([ReviewExchange(ko, emoji)]);
      expect(out.single['q'], '가' * 1000);
      expect(out.single['a']!.runes.length, 1000);
      expect(out.single['a'], '\u{1F004}' * 1000);
    });
    test('1000자는 그대로 · 빈 목록', () {
      expect(historyPayload([ReviewExchange('나' * 1000, '')]).single['q'], '나' * 1000);
      expect(historyPayload(const []), isEmpty);
    });
  });

  group('askBody · askProblem', () {
    final small = {'version': 2, 'game': <String, dynamic>{}, 'turns': <dynamic>[], 'others': <dynamic>[]};

    test('history 가 비면 키 없음, 있으면 historyPayload', () {
      final b = askBody(facts: small, question: ' 질문 ');
      expect(b.keys.toList(), ['facts', 'question']);
      expect(b['question'], '질문');
      final h = askBody(facts: small, question: 'q', history: const [ReviewExchange('a', 'b')]);
      expect(h['history'], [
        {'q': 'a', 'a': 'b'},
      ]);
    });
    test('문제 없음 → null', () => expect(askProblem(askBody(facts: small, question: '이 판 총평 해 줘')), isNull));
    test('빈 질문 · 공백만', () {
      expect(askProblem(askBody(facts: small, question: '')), askEmptyMessage);
      expect(askProblem({'facts': small, 'question': '   '}), askEmptyMessage);
      expect(askProblem({'facts': small}), askEmptyMessage);
    });
    test('300자는 받고 301자는 거절(코드 포인트)', () {
      expect(askProblem(askBody(facts: small, question: '가' * 300)), isNull);
      expect(askProblem(askBody(facts: small, question: '가' * 301)), askTooLongMessage);
      expect(askProblem(askBody(facts: small, question: '\u{1F004}' * 300)), isNull);
    });
    test('차례 41 · 남의 사건 65 → 너무 긺', () {
      final long = {...small, 'turns': List.filled(41, <String, dynamic>{})};
      expect(askProblem(askBody(facts: long, question: 'q')), askTooLargeMessage);
      final forty = {...small, 'turns': List.filled(40, <String, dynamic>{})};
      expect(askProblem(askBody(facts: forty, question: 'q')), isNull);
      final others = {...small, 'others': List.filled(65, <String, dynamic>{})};
      expect(askProblem(askBody(facts: others, question: 'q')), askTooLargeMessage);
    });
    test('UTF-8 JSON 200KB 초과 → 너무 긺(한글 3바이트로 셈)', () {
      Map<String, dynamic> withPad(int n) => {...small, 'pad': '가' * n};
      final base = utf8.encode(jsonEncode(askBody(facts: withPad(0), question: 'q'))).length;
      final fit = (reviewMaxRequestBytes - base) ~/ 3;
      expect(utf8.encode(jsonEncode(askBody(facts: withPad(fit), question: 'q'))).length,
          lessThanOrEqualTo(reviewMaxRequestBytes));
      expect(askProblem(askBody(facts: withPad(fit), question: 'q')), isNull);
      expect(askProblem(askBody(facts: withPad(fit + 1), question: 'q')), askTooLargeMessage);
    });
    test('손으로 만든 규격 밖 history', () {
      expect(askProblem({'facts': small, 'question': 'q', 'history': List.filled(5, {'q': '', 'a': ''})}),
          askBadHistoryMessage);
      expect(askProblem({'facts': small, 'question': 'q', 'history': [{'q': 'x'}]}), askBadHistoryMessage);
    });
    test('예시 11판 × 모든 추천 질문 · 차례 붙인 질문: 보내기 전 검사 통과', () {
      for (final id in games) {
        final (p, r) = game(id);
        final facts = agentFacts(p, r);
        final qs = {
          for (final t in <TurnReview?>[...r.turns, null]) ...suggestedQuestions(p, r, t),
          for (final t in r.turns) withTurnContext('이 수 어땠어?', t.turn),
        };
        for (final q in qs) {
          expect(askProblem(askBody(facts: facts, question: q)), isNull, reason: '$id "$q"');
        }
        expect(utf8.encode(jsonEncode(askBody(facts: facts, question: qs.first))).length, lessThan(60 * 1024),
            reason: id);
      }
    });
  });

  group('answerSpans', () {
    const t = AnswerSpanKind.text, tile = AnswerSpanKind.tile, lv = AnswerSpanKind.level;
    String joined(List<AnswerSpan> s) => s.map((x) => x.text).join();

    test('패', () {
      expect(answerSpans('[3만]'), [const AnswerSpan(tile, '3만')]);
      expect(answerSpans('[중]을 버렸다.'), [const AnswerSpan(tile, '중'), const AnswerSpan(t, '을 버렸다.')]);
    });
    test('단계(곧은 · 굽은 따옴표, 띄어 쓴 "매우 높음")', () {
      expect(answerSpans("'높음'"), [const AnswerSpan(lv, '높음')]);
      expect(answerSpans('위험 ‘매우 높음’이다'),
          [const AnswerSpan(t, '위험 '), const AnswerSpan(lv, '매우 높음'), const AnswerSpan(t, '이다')]);
      expect(answerSpans("‘안전'"), [const AnswerSpan(lv, '안전')]);
    });
    test('섞인 글 — 이어 붙이면 표시만 빠진 원문', () {
      const a = "6순에 버린 [4만]은 위험 '보통'으로 손의 12종 중 7위였다. 가장 안전한 패는 [9통] · [서]다.";
      final s = answerSpans(a);
      expect(s, [
        const AnswerSpan(t, '6순에 버린 '),
        const AnswerSpan(tile, '4만'),
        const AnswerSpan(t, '은 위험 '),
        const AnswerSpan(lv, '보통'),
        const AnswerSpan(t, '으로 손의 12종 중 7위였다. 가장 안전한 패는 '),
        const AnswerSpan(tile, '9통'),
        const AnswerSpan(t, ' · '),
        const AnswerSpan(tile, '서'),
        const AnswerSpan(t, '다.'),
      ]);
      expect(joined(s), a.replaceAll(RegExp("[\\[\\]']"), ''));
    });
    test('표시 없는 글 · 빈 글', () {
      expect(answerSpans('이 판 패효율은 94%다.'), [const AnswerSpan(t, '이 판 패효율은 94%다.')]);
      expect(answerSpans(''), isEmpty);
    });
    test('패 이름이 아닌 대괄호 · 다섯 단계가 아닌 따옴표는 그대로 글', () {
      const a = "[참고] 'abc' 와 [10만]";
      expect(answerSpans(a), [const AnswerSpan(t, a)]);
    });
  });

  group('answerTurns', () {
    test('나온 순서 · 겹침 없이 최대 3개', () {
      final r = {
        'tool_calls': [
          {'tool': 'turn_info', 'args': {'turn': 6}},
          {'tool': 'discard_options', 'args': {'turn': 6}},
          {'tool': 'game_summary', 'args': <String, dynamic>{}},
          {'tool': 'turn_info', 'args': {'turn': 3}},
          {'tool': 'turn_info', 'args': {'turn': 9}},
          {'tool': 'turn_info', 'args': {'turn': 11}},
        ],
      };
      expect(answerTurns(r), [6, 3, 9]);
    });
    test('꼴이 이상하면 빈 목록 · 이상한 항목은 건너뜀(던지지 않음)', () {
      expect(answerTurns({}), isEmpty);
      expect(answerTurns({'tool_calls': 'x'}), isEmpty);
      expect(answerTurns({'tool_calls': null}), isEmpty);
      expect(
          answerTurns({
            'tool_calls': [
              1,
              {'args': 'x'},
              {'args': {'turn': '6'}},
              {'args': {'turn': 6.0}},
              {'args': {'turn': 0}},
              {'args': {'turn': 4}},
            ],
          }),
          [4]);
    });
  });
}
