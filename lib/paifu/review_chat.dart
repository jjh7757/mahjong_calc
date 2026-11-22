/// 패보 복기 에이전트 질문 창의 글: 추천 질문 · 지금 차례 붙이기 · 이어 묻기 자르기 · 보내기 전 검사 · 답 글 조각.
///
/// 규격은 `docs/paifu_review_agent_app_design_1122.md` 3-2 · 3-3 · 3-5 · 4절. 화면과 떼어 시험하는 순수 Dart 다
/// (Flutter 를 쓰지 않음 — `dart run tool/review_ask_bodies.dart` 로도 돈다). 서버를 부르는 코드는
/// `lib/services/review_ask_client.dart`.
library;

import 'dart:convert';

import '../engine/tile.dart';
import 'agent_facts.dart' show riskLevels;
import 'paifu.dart';
import 'paifu_review.dart';
import 'review_sentence.dart' show gradeName, withEul;

// ── 서버 한도(mahjong-recognizer `app/review_agent.py` 의 같은 이름 상수, `validate_request` 가 검사) ──
//
// 서버와 다르면 앱이 보낸 요청이 422 로 거절된다. 바꾸려면 서버 쪽부터.

/// 질문 글자 수(앞뒤 공백을 뺀 코드 포인트, 서버 `QUESTION_MAX`).
const reviewQuestionMax = 300;

/// 이어 묻기로 함께 보내는 질문 · 답 쌍(서버 `HISTORY_MAX`).
const reviewHistoryMax = 4;

/// 이어 묻기의 질문 · 답 하나의 글자 수(코드 포인트, 서버 `HISTORY_TEXT_MAX`).
const reviewHistoryTextMax = 1000;

/// 사실표 차례 수(서버 `MAX_TURNS`).
const reviewMaxTurns = 40;

/// 사실표 남의 사건 수(서버 `MAX_OTHERS`). 명세 밖이지만 서버가 같이 거절하므로 같이 본다.
const reviewMaxOthers = 64;

/// 요청 전체(UTF-8 압축 JSON, 서버 `MAX_REQUEST_BYTES`). 서버는 이걸 넘는 본문을 413 으로 받지 않는다.
const reviewMaxRequestBytes = 200 * 1024;

/// 판이 너무 커서 보내지 않을 때의 문구(설계서 3-4). 클라이언트가 이 문구로 tooLarge 를 가린다.
const askTooLargeMessage = '이 판은 너무 길어 질문할 수 없습니다.';

/// 질문이 비었을 때.
const askEmptyMessage = '질문을 쓰세요.';

/// 질문이 너무 길 때.
const askTooLongMessage = '질문은 $reviewQuestionMax자까지 쓸 수 있습니다.';

/// 이어 묻기 기록이 규격 밖일 때([askBody] 로 만들면 생기지 않음).
const askBadHistoryMessage = '이어 묻기 기록이 규격을 벗어났습니다.';

/// 한 번의 질문 · 답.
class ReviewExchange {
  final String q;
  final String a;
  const ReviewExchange(this.q, this.a);
}

// ── 차례 번호(설계서 3-3) ──

/// 서버 `review_agent._QUESTION_TURN` 과 같은 뜻: `(\d+)\s?(?:순(?!위)|번째|차례|턴)`.
/// 파이썬 `\d` 는 유니코드 숫자 전부라, 자주 쓰일 법한 전각 숫자(０~９)까지만 같이 받는다.
final _questionTurn = RegExp(r'([0-9０-９]+)\s?(?:순(?!위)|번째|차례|턴)');

String _asciiDigits(String s) => String.fromCharCodes([
      for (final c in s.codeUnits) c >= 0xFF10 && c <= 0xFF19 ? c - 0xFF10 + 0x30 : c,
    ]);

/// 질문 글에 든 차례 번호(나온 순서, 겹침 없이). 서버 `review_agent.question_turns` 와 같은 뜻.
/// int 에 안 들어가는 긴 숫자는 버린다(서버는 받지만 그런 차례는 없다).
List<int> questionTurns(String q) {
  final out = <int>[];
  for (final m in _questionTurn.allMatches(q)) {
    final n = int.tryParse(_asciiDigits(m.group(1)!));
    if (n != null && !out.contains(n)) out.add(n);
  }
  return out;
}

/// 지금 보는 차례 붙이기: 앞뒤 공백을 빼고, [turn] 이 있고 글에 차례 번호가 없으면 앞에 "N순에 대해: ".
String withTurnContext(String question, int? turn) {
  final q = question.trim();
  if (turn == null || questionTurns(q).isNotEmpty) return q;
  return '$turn순에 대해: $q';
}

// ── 추천 질문(설계서 3-2) ──

const _windNames = ['동', '남', '서', '북'];

const _handUnknown = {ReviewStatus.unknownHand, ReviewStatus.inconsistent, ReviewStatus.guessed};

const _lowGrades = {ReviewGrade.inaccuracy, ReviewGrade.mistake, ReviewGrade.blunder};

/// "실수야" · "부정확이야": 받침이 있으면 "이야".
String _withIya(String word) {
  final c = word.codeUnitAt(word.length - 1);
  final jong = c < 0xAC00 || c > 0xD7A3 || (c - 0xAC00) % 28 != 0;
  return jong ? '$word이야' : '$word야';
}

/// 사건 순서로 처음 리치한 남(hero 아닌 자리)의 자리. 없으면 null. `agent_facts.dart` `_others` 의 리치와 같은 뜻.
int? _firstOtherRiichi(Paifu p) {
  for (final e in p.events) {
    if (e.seat != p.hero && e.type == PaifuEventType.discard && e.riichi && e.tile != null) return e.seat;
  }
  return null;
}

/// 판 전체 질문(내 버림이 아닌 걸음 · 그 차례 질문이 없을 때).
List<String> _gameQuestions(Paifu p) {
  final seat = _firstOtherRiichi(p);
  return [
    '이 판에서 제일 아까운 수는?',
    '이 판 총평 해 줘',
    if (seat != null) '${_windNames[p.windOf(seat)]} 리치 뒤에 나는 어떻게 했어?',
  ];
}

/// 지금 걸음의 추천 질문(최대 3개). [t] 는 지금 걸음의 내 버림 평가(내 버림 걸음이 아니면 null).
///
/// 문구는 평가 세트(`experiments/paifu_review/agent_questions_*.json`)의 꼴 그대로다 — 새 꼴을 지어내면 평가한 범위를
/// 벗어난다. 패 이름은 대괄호 없이, 적5 도 "5만"(서버 표기). 순서: 수비 질문 → 등급 질문, 합쳐 3개까지,
/// 하나도 없으면 판 전체 질문. 손패를 모르는 차례는 그 차례 질문을 내지 않는다(물으면 에이전트가 "모른다" 고 답함).
/// [r] 은 화면이 가진 리뷰 그대로 받는다(지금은 [t] 만 보면 되지만 판 전체 질문을 리뷰로 고를 자리).
List<String> suggestedQuestions(Paifu p, PaifuReview r, TurnReview? t) {
  if (t == null || _handUnknown.contains(t.status)) return _gameQuestions(p);
  final n = t.turn;
  final x = Tiles.name(t.discard.tile);
  final out = <String>[];
  // 수비(D): 남이 리치한 차례. 내가 리치 중(forced)이면 고를 수 없었으므로 "뭘 버리면" 은 묻지 않는다.
  if (t.riichiSeats.isNotEmpty && t.before != null) {
    out.add('$n순에 버린 $x 위험했어?');
    if (t.status != ReviewStatus.forced) out.add('$n순에 뭘 버리면 제일 안전했어?');
  }
  // 등급(E): 부정확 · 실수 · 큰 실수.
  final g = t.grade;
  if (t.status == ReviewStatus.graded && g != null && _lowGrades.contains(g)) {
    out.add('$n순에 $x 버린 게 왜 ${_withIya(gradeName(g))}?');
    final b = t.best;
    if (b != null && b.tile != t.discard.tile) out.add('$n순에 ${withEul(Tiles.name(b.tile))} 버렸으면 어떻게 됐어?');
  }
  if (out.isEmpty) return _gameQuestions(p);
  return out.length > 3 ? out.sublist(0, 3) : out;
}

// ── 요청 본문 ──

/// 코드 포인트 [max] 개까지(서버 `len(str)` 과 같은 셈).
String _cut(String s, int max) {
  final runes = s.runes;
  return runes.length <= max ? s : String.fromCharCodes(runes.take(max));
}

/// 이어 묻기로 보낼 기록: 최근 [reviewHistoryMax] 쌍, 질문 · 답 각각 [reviewHistoryTextMax] 자로 자름.
List<Map<String, String>> historyPayload(List<ReviewExchange> all) {
  final recent = all.length > reviewHistoryMax ? all.sublist(all.length - reviewHistoryMax) : all;
  return [
    for (final e in recent) {'q': _cut(e.q, reviewHistoryTextMax), 'a': _cut(e.a, reviewHistoryTextMax)},
  ];
}

/// `POST /v2/review/ask` 의 본문. 질문은 앞뒤 공백을 뺀다. 기록이 없으면 `history` 키를 넣지 않는다.
Map<String, dynamic> askBody({
  required Map<String, dynamic> facts,
  required String question,
  List<ReviewExchange> history = const [],
}) {
  return {
    'facts': facts,
    'question': question.trim(),
    if (history.isNotEmpty) 'history': historyPayload(history),
  };
}

/// 보내기 전 검사(서버 `validate_request` 의 크기 · 글자 수 부분). 문제가 없으면 null, 있으면 화면에 그대로 보일 한 줄.
/// 판이 너무 크면 [askTooLargeMessage] — 서버에 보내도 413 · 422 라 보내지 않는다.
String? askProblem(Map<String, dynamic> body) {
  final q = body['question'];
  if (q is! String || q.trim().isEmpty) return askEmptyMessage;
  if (q.trim().runes.length > reviewQuestionMax) return askTooLongMessage;
  final hist = body['history'];
  if (hist != null) {
    final ok = hist is List &&
        hist.length <= reviewHistoryMax &&
        hist.every((h) =>
            h is Map &&
            [h['q'], h['a']].every((s) => s is String && s.runes.length <= reviewHistoryTextMax));
    if (!ok) return askBadHistoryMessage;
  }
  final facts = body['facts'];
  if (facts is Map) {
    final turns = facts['turns'];
    final others = facts['others'];
    if (turns is List && turns.length > reviewMaxTurns) return askTooLargeMessage;
    if (others is List && others.length > reviewMaxOthers) return askTooLargeMessage;
  }
  if (utf8.encode(jsonEncode(body)).length > reviewMaxRequestBytes) return askTooLargeMessage;
  return null;
}

// ── 답 글 조각(설계서 3-5) ──

enum AnswerSpanKind { text, tile, level }

/// 답 글의 한 조각. tile 은 대괄호 안 패 이름, level 은 따옴표 안 위험 단계, text 는 그 밖의 글.
class AnswerSpan {
  final AnswerSpanKind kind;
  final String text;
  const AnswerSpan(this.kind, this.text);

  @override
  bool operator ==(Object other) => other is AnswerSpan && other.kind == kind && other.text == text;

  @override
  int get hashCode => Object.hash(kind, text);

  @override
  String toString() => '${kind.name}($text)';
}

/// `[3만]`(패 이름 34개만 — 서버 `bracket()` 이 쓰는 꼴) 또는 `'높음'` · `‘높음’`(다섯 단계만).
final _answerMark = RegExp(
  '\\[(${[for (var k = 0; k < Tiles.count; k++) Tiles.name(k)].join('|')})\\]'
  "|['‘](${riskLevels.join('|')})['’]",
);

/// 답 글 → 조각. 조각의 text 를 이어 붙이면 표시(대괄호 · 따옴표)만 빠진 원문이다.
/// 패 이름이 아닌 대괄호 · 다섯 단계가 아닌 따옴표 글은 손대지 않고 text 로 둔다.
List<AnswerSpan> answerSpans(String answer) {
  final out = <AnswerSpan>[];
  var at = 0;
  for (final m in _answerMark.allMatches(answer)) {
    if (m.start > at) out.add(AnswerSpan(AnswerSpanKind.text, answer.substring(at, m.start)));
    final tile = m.group(1);
    out.add(tile != null ? AnswerSpan(AnswerSpanKind.tile, tile) : AnswerSpan(AnswerSpanKind.level, m.group(2)!));
    at = m.end;
  }
  if (at < answer.length) out.add(AnswerSpan(AnswerSpanKind.text, answer.substring(at)));
  return out;
}

/// 응답 `tool_calls` 의 `args.turn`(1 이상 정수) — 나온 순서 · 겹침 없이 최대 3개("N순 보기" 칩).
/// 꼴이 이상하면 빈 목록(던지지 않음). 목록 안의 이상한 항목 하나는 건너뛴다.
List<int> answerTurns(Map<String, dynamic> response) {
  final calls = response['tool_calls'];
  if (calls is! List) return const [];
  final out = <int>[];
  for (final c in calls) {
    if (c is! Map) continue;
    final args = c['args'];
    if (args is! Map) continue;
    final n = args['turn'];
    if (n is int && n >= 1 && !out.contains(n)) {
      out.add(n);
      if (out.length == 3) break;
    }
  }
  return out;
}
