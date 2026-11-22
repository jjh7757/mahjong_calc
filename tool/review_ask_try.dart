// 앱 클라이언트(ReviewAskClient)로 복기 서버에 질문 한 번(설계서 1122 6절 1단계 — 개발용 서버 `--fake` 확인용).
//
//   dart run tool/review_ask_try.dart <base url> <api key> <패보.json> "<질문>" [--no-engine]
//
// 사실표는 앱과 같게 agentFacts(p, reviewPaifu(p, withEngine: true)). --no-engine 이면 엔진을 끈다(수비 칸 없음).
// 질문은 그대로 보낸다(차례 붙이기 없음). 성공이면 답 · verified · turns · 걸린 초, 실패면 ReviewAskError 이름 · 문구 ·
// retryAfter 를 stdout 에(UTF-8). 종료 코드 0 / 1, 쓰는 법이 틀리면 64.
// 운영 주소 · 실제 Gemini 서버에 쓰면 호출 제한 · 돈이 든다 — 개발용 서버(`scripts/review_dev_server.py --fake`)에 쓴다.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/services/review_ask_client.dart';

void _out(String s) => stdout.add(utf8.encode('$s\n'));

Future<void> main(List<String> argv) async {
  final noEngine = argv.contains('--no-engine');
  final args = [for (final a in argv) if (a != '--no-engine') a];
  if (args.length != 4) {
    stderr.writeln('쓰는 법: dart run tool/review_ask_try.dart <base url> <api key> <패보.json> "<질문>" [--no-engine]');
    exitCode = 64;
    return;
  }
  final [baseUrl, apiKey, path, question] = args;
  final p = Paifu.fromJson(jsonDecode(File(path).readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
  final facts = agentFacts(p, reviewPaifu(p, withEngine: !noEngine));
  final client = ReviewAskClient(baseUrl: baseUrl, apiKey: apiKey);
  final sw = Stopwatch()..start();
  try {
    final a = await client.ask(facts: facts, question: question);
    final s = (sw.elapsedMilliseconds / 1000).toStringAsFixed(2);
    _out('답: ${a.answer}');
    _out('verified: ${a.verified} · turns: ${a.turns} · retries: ${a.retries} · 서버 ${a.elapsedS}초 · 왕복 $s초 · '
        'model ${a.model} · prompt ${a.promptVersion}');
    exitCode = 0;
  } on ReviewAskException catch (e) {
    _out('실패: ${e.kind.name} · ${e.message} · retryAfter: ${e.retryAfter?.inSeconds} · HTTP ${e.statusCode}');
    exitCode = 1;
  } finally {
    client.close();
  }
}
