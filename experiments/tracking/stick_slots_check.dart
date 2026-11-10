// ignore_for_file: avoid_print
// lib/table/stick_slots.dart 를 11-07 리치봉 크롭(captures/*_track/sticks_###.jpg)에 돌려 Gemini 답과 맞춘다.
// Python 원형(stick_color_free.py, metrics 표 11-1)과 같은 결과인지 확인용. 크롭 전체를 구역으로 본다.
//
//   dart run experiments/tracking/stick_slots_check.dart [sampleLong=120]
import 'dart:convert';
import 'dart:io';

import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/stick_slots.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main(List<String> args) {
  final sample = args.isNotEmpty ? int.parse(args[0]) : 120;
  final root = Directory('experiments/visit_20261107/captures');
  final files = root
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => RegExp(r'_track[\\/]sticks_\d+\.json$').hasMatch(f.path))
      .toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  var pos = 0, posOk = 0, neg = 0, negOk = 0, n = 0;
  final bad = <String>[];
  final sw = Stopwatch();
  for (final js in files) {
    final jpg = File(js.path.replaceAll('.json', '.jpg'));
    if (!jpg.existsSync()) continue;
    final read = (jsonDecode(js.readAsStringSync())['read']['riichi_sticks'] as Map).cast<String, dynamic>();
    final im = img.decodeJpg(jpg.readAsBytesSync())!;
    sw.start();
    final got = stickSlotsIn(im, const NormBox(0, 0, 1000, 1000), config: StickSlotConfig(sampleLong: sample));
    sw.stop();
    n++;
    for (final s in Side.values) {
      final t = read[s.name] == true;
      if (t) {
        pos++;
        if (got[s]!) posOk++;
      } else {
        neg++;
        if (!got[s]!) negOk++;
      }
      if (got[s] != t) bad.add('${jpg.path.split(RegExp(r'[\\/]')).reversed.take(2).toList().reversed.join('/')} ${s.name} 정답 $t');
    }
  }
  print('크롭 $n장(구역 긴 변 $sample) · 봉 있음 $posOk/$pos · 봉 없음 $negOk/$neg · 판정 평균 ${(sw.elapsedMicroseconds / n / 1000).toStringAsFixed(1)}ms');
  for (final b in bad) {
    print('  $b');
  }
}
