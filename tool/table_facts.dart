// 패보 한 판 → 탁자 사실표(대국 뒤 복기 대화, 설계서 docs/postgame_review_chat_design_1124.md 3 · 4절).
//
//   dart run tool/table_facts.dart <패보.json> [출력.json]
//   dart run tool/table_facts.dart --examples <출력폴더>
//
// 출력 경로가 없으면 stdout 으로. 들여쓰기 2칸, UTF-8, 줄바꿈 LF. 화면 없이 도는 순수 Dart(Flutter 를 쓰지 않음).
// --examples 는 예시 22판(assets/paifu/*.json 11 + assets/paifu_h3/*.json 11)을 각각 `<id>.json` 으로 쓰고,
// stderr 에 판마다 버림 수 · vs 붙은 버림 수 · 자리별 장면 수와 합계를 적는다.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/table_facts.dart';

const _exampleDirs = ['assets/paifu', 'assets/paifu_h3'];

Paifu _load(File f) => Paifu.fromJson(jsonDecode(f.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);

String _text(Map<String, dynamic> facts) => '${const JsonEncoder.withIndent('  ').convert(facts)}\n';

/// 판 하나의 요약 한 줄과 숫자들.
({int discards, int withVs, List<int> scenes, String line}) _summary(String id, Map<String, dynamic> f) {
  final events = (f['events'] as List).cast<Map<String, dynamic>>();
  final discards = events.where((e) => e['kind'] == 'discard').toList();
  final withVs = discards.where((e) => (e['vs'] as List).isNotEmpty).length;
  final bySeat = (f['scenes_by_seat'] as Map).cast<String, dynamic>();
  final scenes = [for (final w in const ['동', '남', '서', '북']) (bySeat[w] as List).length];
  final line = '$id — 버림 ${discards.length}, vs 붙은 버림 $withVs, 장면(동남서북) ${scenes.join('/')} = '
      '${scenes.reduce((a, b) => a + b)}, 압축 ${utf8.encode(jsonEncode(f)).length} bytes';
  return (discards: discards.length, withVs: withVs, scenes: scenes, line: line);
}

void main(List<String> args) {
  if (args.length == 2 && args[0] == '--examples') {
    final out = Directory(args[1])..createSync(recursive: true);
    final files = [
      for (final d in _exampleDirs)
        ...(Directory(d).listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
          ..sort((a, b) => a.path.compareTo(b.path))),
    ];
    var discards = 0, withVs = 0, scenes = 0, zeroSeats = 0;
    for (final f in files) {
      final p = _load(f);
      final facts = tableFacts(p);
      File('${out.path}/${p.id}.json').writeAsBytesSync(utf8.encode(_text(facts)));
      final s = _summary(p.id, facts);
      stderr.writeln(s.line);
      discards += s.discards;
      withVs += s.withVs;
      scenes += s.scenes.reduce((a, b) => a + b);
      zeroSeats += s.scenes.where((n) => n == 0).length;
    }
    stderr.writeln('합계 ${files.length}판 — 버림 $discards, vs 붙은 버림 $withVs, 장면 $scenes, '
        '장면 0 인 자리 $zeroSeats/${files.length * 4} → ${out.path}');
    return;
  }
  if (args.isEmpty || args.length > 2 || args[0].startsWith('--')) {
    stderr.writeln('쓰는 법: dart run tool/table_facts.dart <패보.json> [출력.json]\n'
        '        dart run tool/table_facts.dart --examples <출력폴더>');
    exitCode = 64;
    return;
  }
  final src = File(args[0]);
  if (!src.existsSync()) {
    stderr.writeln('패보 파일이 없습니다: ${args[0]}');
    exitCode = 66;
    return;
  }
  final p = _load(src);
  final facts = tableFacts(p);
  final text = _text(facts);
  if (args.length == 2) {
    File(args[1]).writeAsBytesSync(utf8.encode(text));
    stderr.writeln('${args[1]} — ${_summary(p.id, facts).line}');
  } else {
    stdout.add(utf8.encode(text));
  }
}
