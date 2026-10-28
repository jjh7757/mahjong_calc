// 앞면(화료자) 픽셀 판정을 실제 갤러리 사진 B·C·D 에 돌려 본다(서버 호출 없음).
// 앱과 같은 축소본(TableImage.shrunkJpeg, 긴 변 1024) → analyzeGridShot. 수동 격자와 YOLO26 자동 격자 둘 다.
//   flutter test experiments/field_20261024/faceup_check_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';

const _manual = {
  'B': GridZones(x1: 272, x2: 735, y1: 137, y2: 727),
  'C': GridZones(x1: 320, x2: 760, y1: 142, y2: 717),
  'D': GridZones(x1: 280, x2: 745, y1: 173, y2: 713),
};
const _photos = {'B': ['k25', 'k28'], 'C': ['k15', 'k26'], 'D': ['k12', 'k16']};
const _winner = {'B': Side.right, 'C': Side.left, 'D': Side.bottom};

void main() {
  test('B·C·D 화료자 픽셀 판정', () {
    final auto = jsonDecode(File('experiments/yolo/results/auto_grid/auto_grid.json').readAsStringSync()) as Map<String, dynamic>;
    var ok = 0, n = 0;
    for (final s in _photos.keys) {
      for (final p in _photos[s]!) {
        final small = TableImage.decode(File('experiments/field_20261024/kakao_photos/$p.jpg').readAsBytesSync()).shrunkJpeg();
        final grids = {
          '수동': _manual[s]!,
          '자동': GridZones.fromJson((auto['$s/$p'] as Map<String, dynamic>)['grid'] as Map<String, dynamic>)!,
        };
        for (final g in grids.entries) {
          final sw = Stopwatch()..start();
          final a = analyzeGridShot((small, g.value));
          final good = a.faceUp.length == 1 && a.faceUp.single == _winner[s];
          n++;
          if (good) ok++;
          // ignore: avoid_print
          print('$s $p ${g.key}: 앞면 ${a.faceUp.map((x) => x.name).toList()} (정답 ${_winner[s]!.name}) '
              '${good ? '맞음' : '틀림/못 정함'} 무늬 ${a.tilePatterns.map((k, v) => MapEntry(k.name, v))} ${sw.elapsedMilliseconds}ms');
        }
      }
    }
    // ignore: avoid_print
    print('한 자리로 맞게 정함 $ok/$n');
  });
}
