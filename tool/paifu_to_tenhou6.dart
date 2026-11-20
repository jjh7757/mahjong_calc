// 패보 한 판 → tenhou.net/6 JSON(천봉 형식, 설계서 부록 B). 외부 리뷰 도구에 붙여 넣기 위한 것.
//
//   dart run tool/paifu_to_tenhou6.dart <패보.json> <출력.json> [--unknown tedashi|tsumogiri] [--scores a,b,c,d] [--seed n]
//
// 출력은 한 줄 압축 JSON(공백 없음), UTF-8, 끝에 줄바꿈 하나. stderr 에 heroIndex 와 assumptions 를 찍는다.
// --scores 는 우리 패보의 자리 순(0~3). 변환 못 하면 까닭을 찍고 종료 코드 1. 화면 없이 도는 순수 Dart(Flutter 를 쓰지 않음).
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/tenhou6_export.dart';

const _usage = '쓰는 법: dart run tool/paifu_to_tenhou6.dart <패보.json> <출력.json> '
    '[--unknown tedashi|tsumogiri] [--scores a,b,c,d] [--seed n]';

void main(List<String> args) {
  final pos = <String>[];
  var unknown = UnknownDiscard.tedashi;
  List<int>? scores;
  var seed = 0;
  void bad(String why) {
    stderr.writeln(why);
    stderr.writeln(_usage);
    exitCode = 64;
  }

  for (var i = 0; i < args.length; i++) {
    final a = args[i];
    if (a == '--unknown' || a == '--scores' || a == '--seed') {
      if (i + 1 >= args.length) return bad('$a 뒤에 값이 없습니다');
      final v = args[++i];
      switch (a) {
        case '--unknown':
          final u = UnknownDiscard.values.where((x) => x.name == v);
          if (u.isEmpty) return bad('--unknown 은 tedashi 나 tsumogiri: $v');
          unknown = u.first;
        case '--scores':
          final parts = v.split(',').map((x) => int.tryParse(x.trim())).toList();
          if (parts.length != 4 || parts.contains(null)) return bad('--scores 는 정수 넷(쉼표로): $v');
          scores = [for (final x in parts) x!];
        case '--seed':
          final n = int.tryParse(v);
          if (n == null) return bad('--seed 는 정수: $v');
          seed = n;
      }
    } else if (a.startsWith('--')) {
      return bad('모르는 선택: $a');
    } else {
      pos.add(a);
    }
  }
  if (pos.length != 2) return bad('패보 경로와 출력 경로가 필요합니다');

  final src = File(pos[0]);
  if (!src.existsSync()) {
    stderr.writeln('패보 파일이 없습니다: ${pos[0]}');
    exitCode = 1;
    return;
  }
  final Tenhou6Export out;
  try {
    final p = Paifu.fromJson(jsonDecode(src.readAsStringSync(encoding: utf8)) as Map<String, dynamic>);
    out = toTenhou6(p, unknownAs: unknown, scores: scores, seed: seed);
  } on Tenhou6ExportError catch (e) {
    stderr.writeln('변환 못 함: ${e.message}');
    exitCode = 1;
    return;
  } on FormatException catch (e) {
    stderr.writeln('패보를 읽지 못함: ${e.message}');
    exitCode = 1;
    return;
  }
  File(pos[1]).writeAsBytesSync(utf8.encode('${jsonEncode(out.json)}\n'));
  stderr.writeln('heroIndex: ${out.heroIndex}');
  for (final a in out.assumptions) {
    stderr.writeln(a);
  }
}
