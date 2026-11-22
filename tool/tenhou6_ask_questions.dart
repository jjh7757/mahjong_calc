// 천봉(tenhou.net/6) 한 국 · 한 자리 → 앱이 그 국에서 만들 질문 글(설계서 docs/paifu_review_agent_app_design_1122.md 6절 3단계 A).
//
//   dart run tool/tenhou6_ask_questions.dart <tenhou6.json> <국 번호(log 배열 0부터)> <자리(천봉 0~3)> [출력.json]
//
// 그 국의 [Paifu] 를 tool/tenhou6_agent_facts.dart 와 같은 방법으로 만들고(kyokuToPaifu + 결과 칸 tenhouResult, 판 ID 비움),
// reviewPaifu(엔진 켬)로 리뷰를 내어 tool/review_ask_bodies.dart 와 같은 꼴의 질문 목록을 낸다:
//   [{"turn": N|null, "kind": "suggested"|"typed", "q": "보낼 글"}]
//   hero 차례마다 suggestedQuestions 전부 + withTurnContext("이 수 어땠어?", N) 하나, 끝에 t == null 의 추천 질문.
// 안전 검사: 같은 Paifu · 리뷰로 낸 agentFacts 가 tenhouAgentFacts(같은 판 · 국 · 자리)와 JSON 으로 같아야 한다
// (질문 글이 사실표와 같은 판에서 나왔다는 보증). 다르면 종료 코드 70.
// 깡이 든 국 · 범위 밖 · 재생 실패는 tenhou6_agent_facts.dart 와 같이 종료 코드 65. 쓰는 법 틀림 64, 파일 없음 66.
// 출력 경로가 없으면 stdout. 들여쓰기 2칸 · UTF-8 · LF. stderr 에 질문 수(추천 · 차례 · 판 전체). 화면 없이 도는 순수 Dart.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_chat.dart';

import 'tenhou6_agent_facts.dart' show tenhouAgentFacts, tenhouResult;
import 'tenhou6_features.dart' show ReplayError, hasKan, kyokuToPaifu;

/// 차례 붙이기를 보일 직접 쓴 질문(차례 번호 없음) — tool/review_ask_bodies.dart 와 같은 글.
const typedQuestion = '이 수 어땠어?';

/// tenhou6_agent_facts.dart 의 tenhouAgentFacts 와 같은 [Paifu](같은 검사 · 같은 순서).
Paifu tenhouPaifu(Map<String, dynamic> json, int kyoku, int seat) {
  final logs = json['log'] as List;
  if (kyoku < 0 || kyoku >= logs.length) throw ReplayError('국 번호 $kyoku 가 범위 밖(0~${logs.length - 1})');
  if (seat < 0 || seat > 3) throw ReplayError('자리는 0~3: $seat');
  final log = logs[kyoku] as List;
  if (hasKan(log)) throw ReplayError('깡이 든 국은 지원하지 않는다(국 $kyoku)');
  final bare = kyokuToPaifu(log, seat);
  return Paifu(
    id: '',
    round: bare.round,
    honba: bare.honba,
    dealer: bare.dealer,
    hero: bare.hero,
    doraIndicators: bare.doraIndicators,
    events: bare.events,
    result: tenhouResult(log, bare),
  );
}

/// 리뷰 하나로 앱이 낼 질문 목록(tool/review_ask_bodies.dart 와 같은 꼴 · 같은 순서).
List<Map<String, dynamic>> askQuestions(Paifu p, PaifuReview r) {
  final qs = <Map<String, dynamic>>[];
  for (final t in r.turns) {
    for (final q in suggestedQuestions(p, r, t)) {
      qs.add({'turn': t.turn, 'kind': 'suggested', 'q': q});
    }
    qs.add({'turn': t.turn, 'kind': 'typed', 'q': withTurnContext(typedQuestion, t.turn)});
  }
  for (final q in suggestedQuestions(p, r, null)) {
    qs.add({'turn': null, 'kind': 'suggested', 'q': q});
  }
  return qs;
}

const _usage = '쓰는 법: dart run tool/tenhou6_ask_questions.dart <tenhou6.json> <국 번호> <자리> [출력.json]';

void main(List<String> args) {
  if (args.length < 3 || args.length > 4) {
    stderr.writeln(_usage);
    exitCode = 64;
    return;
  }
  final src = File(args[0]);
  final kyoku = int.tryParse(args[1]), seat = int.tryParse(args[2]);
  if (kyoku == null || seat == null) {
    stderr.writeln('국 번호 · 자리는 정수\n$_usage');
    exitCode = 64;
    return;
  }
  if (!src.existsSync()) {
    stderr.writeln('파일이 없습니다: ${args[0]}');
    exitCode = 66;
    return;
  }
  final json = jsonDecode(src.readAsStringSync(encoding: utf8)) as Map<String, dynamic>;
  final Paifu p;
  final PaifuReview r;
  final Map<String, dynamic> expected;
  try {
    p = tenhouPaifu(json, kyoku, seat);
    r = reviewPaifu(p, withEngine: true);
    expected = tenhouAgentFacts(json, kyoku, seat);
  } on ReplayError catch (e) {
    stderr.writeln('거절: ${e.message}');
    exitCode = 65;
    return;
  }
  // 안전 검사: 질문을 만든 리뷰의 사실표 = tenhou6_agent_facts.dart 가 내는 사실표.
  if (jsonEncode(agentFacts(p, r)) != jsonEncode(expected)) {
    stderr.writeln('사실표가 tenhouAgentFacts 와 다르다 — 질문 글을 이 판의 사실표와 맞춰 쓸 수 없다(국 $kyoku · 자리 $seat)');
    exitCode = 70;
    return;
  }
  final qs = askQuestions(p, r);
  final text = '${const JsonEncoder.withIndent('  ').convert(qs)}\n';
  if (args.length == 4) {
    File(args[3]).writeAsBytesSync(utf8.encode(text));
  } else {
    stdout.add(utf8.encode(text));
  }
  // 차례 질문 = 글에 차례 번호가 있는 추천 질문, 판 전체 = 없는 것(차례 걸음에서 판 전체 질문으로 바뀐 것 포함).
  final sug = qs.where((q) => q['kind'] == 'suggested');
  final turnQ = sug.where((q) => questionTurns(q['q'] as String).isNotEmpty).length;
  stderr.writeln('${args.length == 4 ? args[3] : 'stdout'} — 질문 ${qs.length}개: 추천 ${sug.length}'
      '(차례 질문 $turnQ · 판 전체 질문 ${sug.length - turnQ})'
      ' · 차례 붙인 직접 질문 ${qs.where((q) => q['kind'] == 'typed').length}, hero 버림 ${r.turns.length}번, 사실표 대조 같음');
}
