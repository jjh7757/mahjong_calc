// 펠트 감시 입력 해상도 비교(2026-11-12): 같은 장면의 1020(건너뛰기, 헤드 /preview)·2040(면적 평균, 헤드 녹화)으로
// feltQuadOfJpeg → gridFromFelt 를 돌려 펠트 찾음 여부·네 모서리·격자 선이 같은지, 시간은 얼마인지 본다.
// 입력은 mk_res_eval40.py 가 만든 폴더(<이름>_1020.jpg·_2040.jpg + names.json).
//
//   RES_DIR=experiments/speed/results/res_eval40 flutter test experiments/speed/felt_res_compare_test.dart
// 결과 RES_DIR/felt_compare.json.
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;

void main() {
  test('펠트 1020 / 2040', () {
    final dir = Platform.environment['RES_DIR'] ?? 'experiments/speed/results/res_eval40';
    final names = (jsonDecode(File('$dir/names.json').readAsStringSync()) as List).cast<String>();
    final rows = <Map<String, dynamic>>[];
    final ms = {'1020': <int>[], '2040': <int>[]};
    for (final n in names) {
      final q = <String, FeltQuad?>{};
      for (final r in ['1020', '2040']) {
        final bytes = File('$dir/${n}_$r.jpg').readAsBytesSync();
        feltQuadOfJpeg(bytes);
        final sw = Stopwatch()..start();
        q[r] = feltQuadOfJpeg(bytes);
        ms[r]!.add(sw.elapsedMilliseconds);
      }
      final a = q['1020'], b = q['2040'];
      double? cornerMax;
      Map<String, int>? gridDiff;
      if (a != null && b != null) {
        final pa = a.corners, pb = b.corners;
        cornerMax = [for (var i = 0; i < 4; i++) math.max((pa[i].x - pb[i].x).abs(), (pa[i].y - pb[i].y).abs())].reduce(math.max);
        final ga = gridFromFelt(a), gb = gridFromFelt(b);
        if (ga != null && gb != null) {
          gridDiff = {'x1': (ga.x1 - gb.x1).abs(), 'x2': (ga.x2 - gb.x2).abs(), 'y1': (ga.y1 - gb.y1).abs(), 'y2': (ga.y2 - gb.y2).abs()};
        }
      }
      rows.add({
        'name': n,
        'found_1020': a != null,
        'found_2040': b != null,
        'corner_max': cornerMax,
        'grid_diff': gridDiff,
        'same_felt': a != null && b != null ? sameFelt(a, b) : null,
      });
    }
    File('$dir/felt_compare.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert({'ms': ms, 'rows': rows}));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
