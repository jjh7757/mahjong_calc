// 패보 한 판 → 패보 리뷰 사실표(LLM 해설 서버에 넘길 요청 JSON, 설계서 부록 A-2).
//
//   dart run tool/paifu_facts.dart <패보.json> [출력.json]
//
// 출력 경로가 없으면 stdout 으로. 들여쓰기 2칸, UTF-8, 줄바꿈 LF. 화면 없이 도는 순수 Dart(Flutter 를 쓰지 않음).
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_facts.dart';

void main(List<String> args) {
  if (args.isEmpty || args.length > 2) {
    stderr.writeln('쓰는 법: dart run tool/paifu_facts.dart <패보.json> [출력.json]');
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
  final facts = reviewFacts(p, reviewPaifu(p));
  final text = '${const JsonEncoder.withIndent('  ').convert(facts)}\n';
  if (args.length == 2) {
    File(args[1]).writeAsBytesSync(utf8.encode(text));
    final turns = (facts['turns'] as List).map((t) => (t as Map)['turn']).join(', ');
    stderr.writeln('${args[1]} — 버림 ${(facts['timeline'] as List).length}번, 해설할 차례 [$turns]');
  } else {
    stdout.add(utf8.encode(text));
  }
}
