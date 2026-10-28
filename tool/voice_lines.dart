// 결과 음성 목록을 JSON(UTF-8) 으로 쓴다(tool/make_voice.py 가 읽음).
//   dart run tool/voice_lines.dart            → assets/voice/lines.json
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/services/voice_lines.dart';

void main(List<String> args) {
  final out = File(args.isEmpty ? 'assets/voice/lines.json' : args.first);
  out.writeAsStringSync('${const JsonEncoder.withIndent('  ').convert(voiceLines)}\n', encoding: utf8);
  stdout.writeln('${voiceLines.length}개 → ${out.path}');
}
