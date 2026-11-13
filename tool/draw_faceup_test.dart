// 유국 공개 합성 사진(experiments/draw_reveal/manifest.json)에 앱의 앞면 판정(analyzeGridShot)을 그대로 돌린다(2026-11-13, API 없음).
// 전체 테스트에는 안 들어간다.
//   flutter test tool/draw_faceup_test.dart  → experiments/draw_reveal/faceup.json, 채점은 experiments/draw_reveal/score.py
import 'dart:convert';
import 'dart:io';

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/fixed_layout.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';

const _feltPads = [0.01, 0.02, 0.03, 0.05, 0.08];

/// 사각형 꼭짓점을 무게중심에서 [pad](정규화)만큼 바깥으로.
List<math.Point<double>> _grow(List<math.Point<double>> c, double pad) {
  final cx = c.map((p) => p.x).reduce((a, b) => a + b) / 4, cy = c.map((p) => p.y).reduce((a, b) => a + b) / 4;
  return [
    for (final p in c)
      () {
        final dx = p.x - cx, dy = p.y - cy, d = math.sqrt(dx * dx + dy * dy);
        return math.Point(p.x + dx / d * pad, p.y + dy / d * pad);
      }()
  ];
}

bool _inQuad(List<math.Point<double>> q, double x, double y) {
  var pos = 0, neg = 0;
  for (var i = 0; i < 4; i++) {
    final a = q[i], b = q[(i + 1) % 4];
    final cr = (b.x - a.x) * (y - a.y) - (b.y - a.y) * (x - a.x);
    if (cr > 0) pos++;
    if (cr < 0) neg++;
  }
  return pos == 0 || neg == 0;
}

void main() {
  test('유국 공개 합성 앞면 판정', () {
    const dir = 'experiments/draw_reveal';
    final rows = jsonDecode(File('$dir/manifest.json').readAsStringSync()) as List;
    final out = <Object?>[];
    final sw = Stopwatch();
    for (final r in rows.cast<Map<String, dynamic>>()) {
      final g = r['grid'] as Map<String, dynamic>;
      final grid = GridZones(x1: g['x1'] as int, x2: g['x2'] as int, y1: g['y1'] as int, y2: g['y2'] as int);
      final small = shrinkForLocate(File(r['file'] as String).readAsBytesSync());
      sw
        ..reset()
        ..start();
      final a = analyzeGridShot((small, grid));
      sw.stop();
      // 펠트 밖(흰 테두리·자동탁 홈) 지우고 다시: 앱 readFelt 사각형을 바깥으로 [_feltPad] 넓힌 것 밖의 흰색을 0 으로.
      final im = decodeSmall(small);
      final felt = readFelt(im);
      final white = whiteMask(im);
      final feltPatterns = <String, Map<String, int>>{};
      if (felt != null) {
        for (final pad in _feltPads) {
          final w = Uint8List.fromList(white);
          final q = _grow(felt.quad.corners, pad);
          for (var y = 0; y < im.height; y++) {
            for (var x = 0; x < im.width; x++) {
              if (!_inQuad(q, (x + 0.5) / im.width, (y + 0.5) / im.height)) w[y * im.width + x] = 0;
            }
          }
          feltPatterns['$pad'] = {for (final s in Side.values) s.name: tilePatternArea(im, w, grid.handCell(s))};
        }
      }
      out.add({
        'file': r['file'],
        'scene': r['scene'],
        'set': r['set'],
        'tenpai': r['tenpai'],
        'faceUp': [for (final s in a.faceUp) s.name],
        'patterns': {for (final e in a.tilePatterns.entries) e.key.name: e.value},
        'ms': sw.elapsedMilliseconds,
        'feltPatterns': feltPatterns,
      });
    }
    File('$dir/faceup.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
    // ignore: avoid_print
    print('판정 ${out.length}장');
    expect(Side.values.length, 4);
  }, timeout: const Timeout(Duration(minutes: 10)));
}
