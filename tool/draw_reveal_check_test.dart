// 앱 유국 공개 판정(lib/table/draw_reveal.dart findDrawReveal)을 유국 공개 합성 216장(experiments/draw_reveal/manifest.json)에
// 그대로 돌려 실험 값(metrics 표 5-1 "펠트 +0.05 밖 지움, 500px" 207/216)과 같은지 본다. 전체 테스트에는 안 들어간다.
//   flutter test tool/draw_reveal_check_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/draw_reveal.dart';
import 'package:mahjong_calc/table/grid_zones.dart';

void main() {
  test('유국 공개 판정 — 합성 216장', () {
    final rows = jsonDecode(File('experiments/draw_reveal/manifest.json').readAsStringSync()) as List;
    var scene = 0, seat = 0;
    final byCount = <int, List<int>>{};
    final ms = <int>[];
    final wrong = <String>[];
    final sw = Stopwatch();
    for (final r in rows.cast<Map<String, dynamic>>()) {
      final g = r['grid'] as Map<String, dynamic>;
      final grid = GridZones(x1: g['x1'] as int, x2: g['x2'] as int, y1: g['y1'] as int, y2: g['y2'] as int);
      final bytes = File(r['file'] as String).readAsBytesSync();
      sw
        ..reset()
        ..start();
      final d = findDrawReveal((bytes, grid));
      sw.stop();
      ms.add(sw.elapsedMilliseconds);
      final truth = (r['tenpai'] as List).cast<String>().toSet();
      final pred = {for (final s in d.revealed) s.name};
      final c = byCount.putIfAbsent(truth.length, () => [0, 0]);
      c[1]++;
      if (pred.length == truth.length && pred.containsAll(truth)) {
        scene++;
        c[0]++;
      } else {
        wrong.add('${r['scene']} 정답 $truth 판정 $pred ${d.patterns.map((k, v) => MapEntry(k.name, v))}');
      }
      for (final s in ['bottom', 'right', 'top', 'left']) {
        if (pred.contains(s) == truth.contains(s)) seat++;
      }
    }
    ms.sort();
    // ignore: avoid_print
    print('장면 $scene/${rows.length} 자리 $seat/${rows.length * 4} 텐파이 수별 ${byCount.map((k, v) => MapEntry(k, '${v[0]}/${v[1]}'))}');
    // ignore: avoid_print
    print('시간 ms 중앙/p90/최대 ${ms[ms.length ~/ 2]} / ${ms[(ms.length * 0.9).floor()]} / ${ms.last}');
    for (final w in wrong) {
      // ignore: avoid_print
      print('틀림 $w');
    }
  }, timeout: const Timeout(Duration(minutes: 10)));
}
