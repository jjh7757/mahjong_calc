// 예시 11판(assets/paifu) → 앱이 서버 POST /v2/review/ask 에 보낼 질문 · 요청 본문을 파일로(설계서 1122 6절 1단계 "맞물림").
//
//   dart run tool/review_ask_bodies.dart <출력 폴더>
//
// 판마다(엔진 켬 — 사실표 v2 의 defense 가 채워지게):
//   <id>.questions.json — [{"turn": N|null, "kind": "suggested"|"typed", "q": "보낼 글"}]
//       hero 차례마다 추천 질문 전부 + 차례 붙인 직접 질문 withTurnContext("이 수 어땠어?", N) 하나, 끝에 t == null 의 추천 질문.
//   <id>.body.json — 첫 추천 질문으로 만든 본문 jsonEncode(askBody(...)) 그대로(클라이언트가 보내는 바이트, 한 줄, 끝 LF 없음).
// 서버 쪽에서 review_agent.validate_request · question_turns 에 넣어 대조한다. 화면 없이 도는 순수 Dart.
// stderr 에 판마다 질문 수 · 본문 바이트.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_chat.dart';

/// 차례 붙이기를 보일 직접 쓴 질문(차례 번호 없음).
const typedQuestion = '이 수 어땠어?';

void main(List<String> argv) {
  if (argv.length != 1) {
    stderr.writeln('쓰는 법: dart run tool/review_ask_bodies.dart <출력 폴더>');
    exitCode = 64;
    return;
  }
  final out = Directory(argv[0])..createSync(recursive: true);
  final files = Directory('assets/paifu').listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  if (files.isEmpty) {
    stderr.writeln('assets/paifu 에 패보가 없습니다(저장소 뿌리에서 돌리세요).');
    exitCode = 66;
    return;
  }
  for (final f in files) {
    final id = f.uri.pathSegments.last.replaceAll('.json', '');
    final p = Paifu.fromJson(jsonDecode(f.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
    final r = reviewPaifu(p, withEngine: true);
    final facts = agentFacts(p, r);
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
    final first = qs.firstWhere((q) => q['kind'] == 'suggested')['q'] as String;
    final body = askBody(facts: facts, question: first);
    final problem = askProblem(body);
    final bodyBytes = utf8.encode(jsonEncode(body));
    File('${out.path}/$id.questions.json')
        .writeAsBytesSync(utf8.encode('${const JsonEncoder.withIndent('  ').convert(qs)}\n'));
    File('${out.path}/$id.body.json').writeAsBytesSync(bodyBytes);
    stderr.writeln('$id — 질문 ${qs.length}개(추천 ${qs.where((q) => q['kind'] == 'suggested').length}), '
        '본문 ${bodyBytes.length} bytes${problem == null ? '' : ' — 보내기 전 검사: $problem'}');
  }
}
