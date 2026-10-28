// [참고 — 평가 밖] 앞면 판정(손패 칸 무늬 넓이)을 갤러리 A·E 에 YOLO26 자동 격자로 돌린다. 규칙은 이 결과로 고치지 않는다.
//   flutter test experiments/backcolor/faceup_ae_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';

const _photos = {'A': ['k20', 'k24'], 'E': ['k00', 'k04']};
const _winner = {'A': Side.top, 'E': Side.left};

void main() {
  test('A·E 화료자 픽셀 판정(참고)', () {
    final auto = jsonDecode(File('experiments/yolo/results/auto_grid/auto_grid.json').readAsStringSync()) as Map<String, dynamic>;
    var ok = 0, n = 0;
    for (final s in _photos.keys) {
      for (final p in _photos[s]!) {
        final small = TableImage.decode(File('experiments/field_20261024/kakao_photos/$p.jpg').readAsBytesSync()).shrunkJpeg();
        final g = GridZones.fromJson((auto['$s/$p'] as Map<String, dynamic>)['grid'] as Map<String, dynamic>)!;
        final a = analyzeGridShot((small, g));
        final good = a.faceUp.length == 1 && a.faceUp.single == _winner[s];
        n++;
        if (good) ok++;
        // ignore: avoid_print
        print('$s $p: 앞면 ${a.faceUp.map((x) => x.name).toList()} (정답 ${_winner[s]!.name}) ${good ? '맞음' : '틀림/못 정함'} '
            '무늬 ${a.tilePatterns.map((k, v) => MapEntry(k.name, v))}');
      }
    }
    // ignore: avoid_print
    print('한 자리로 맞게 정함 $ok/$n');
  });
}
