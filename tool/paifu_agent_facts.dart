// 패보 한 판 → 복기 에이전트 사실표(서버 POST /v2/review/ask 의 facts, 설계서 1121 2절 · v2 defense 는 1122 2절).
//
//   dart run tool/paifu_agent_facts.dart [--compact] <패보.json> [출력.json]
//
// 출력 경로가 없으면 stdout 으로. 기본은 들여쓰기 2칸, --compact 면 공백 없는 한 줄(서버로 보내는 꼴 · 서버 시험 견본용).
// UTF-8, 줄바꿈 LF. 화면 없이 도는 순수 Dart(Flutter 를 쓰지 않음).
// 출력 파일을 쓸 때는 stderr 에 버림 수 · 숫자 있는 차례 수 · 크기(압축 JSON 기준)를 적는다.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/agent_facts.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';

void main(List<String> argv) {
  final compactOut = argv.contains('--compact');
  final args = [for (final a in argv) if (a != '--compact') a];
  if (args.isEmpty || args.length > 2) {
    stderr.writeln('쓰는 법: dart run tool/paifu_agent_facts.dart [--compact] <패보.json> [출력.json]');
    exitCode = 64;
    return;
  }
  final src = File(args[0]);
  if (!src.existsSync()) {
    stderr.writeln('패보 파일이 없습니다: ${args[0]}');
    exitCode = 66;
    return;
  }
  final p = Paifu.fromJson(jsonDecode(src.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
  // 사실표 v2 의 defense(방총 위험 단계)는 엔진 위험표가 있어야 채워진다 — 엔진을 켠다(한 판 수 초).
  final facts = agentFacts(p, reviewPaifu(p, withEngine: true));
  final compact = jsonEncode(facts);
  final text = '${compactOut ? compact : const JsonEncoder.withIndent('  ').convert(facts)}\n';
  if (args.length == 2) {
    File(args[1]).writeAsBytesSync(utf8.encode(text));
    final turns = (facts['turns'] as List).cast<Map<String, dynamic>>();
    final withNumbers = turns.where((t) => (t['options'] as List).isNotEmpty).length;
    final withDefense = turns.where((t) => t['defense'] != null).length;
    stderr.writeln('${args[1]} — 버림 ${turns.length}번, 숫자 있는 차례 $withNumbers, 수비 칸 $withDefense, '
        '압축 ${utf8.encode(compact).length} bytes');
  } else {
    stdout.add(utf8.encode(text));
  }
}
