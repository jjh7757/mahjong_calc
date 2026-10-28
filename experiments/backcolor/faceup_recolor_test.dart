// 뒷면 색을 바꾼 합성 사진(experiments/backcolor/recolor.py)에 앱의 앞면(화료자) 픽셀 판정을 돌린다(서버 호출 없음).
// faceup_check_test.dart 와 같은 수동 격자·축소본. 네 자리 크롭(앱과 같은 자르기)도 photos/<색>/seats/ 에 남겨 Gemini face_up 측정에 쓴다.
//   flutter test experiments/backcolor/faceup_recolor_test.dart
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
const _colors = ['original', 'blue', 'green', 'yellow', 'orange', 'black'];

void main() {
  test('뒷면 색별 화료자 픽셀 판정', () {
    final dir = 'experiments/backcolor/photos';
    final summary = <String, String>{};
    for (final c in _colors) {
      var ok = 0, byColor = 0, n = 0;
      for (final s in _photos.keys) {
        for (final p in _photos[s]!) {
          final ti = TableImage.decode(File('$dir/$c/$p.jpg').readAsBytesSync());
          final small = ti.shrunkJpeg();
          final g = _manual[s]!;
          final a = analyzeGridShot((small, g));
          // 예전(2026-10-26) 1차 판정: 연보라 뒷면 비율 0.004 미만 + 흰 면 0.03 이상
          final byBack = [
            for (final side in Side.values)
              if (a.handColors[side]!.$1 < 0.004 && a.handColors[side]!.$2 >= 0.03) side
          ];
          final good = a.faceUp.length == 1 && a.faceUp.single == _winner[s];
          n++;
          if (good) ok++;
          if (byBack.length == 1 && byBack.single == _winner[s]) byColor++;
          // ignore: avoid_print
          print('$c $s $p: 앞면 ${a.faceUp.map((x) => x.name).toList()} (정답 ${_winner[s]!.name}) ${good ? '맞음' : '틀림/못 정함'}'
              ' | 뒷면 비율로만 ${byBack.map((x) => x.name).toList()}'
              ' | 뒷면 비율 ${{for (final e in a.handColors.entries) e.key.name: e.value.$1.toStringAsFixed(3)}}'
              ' | 무늬 ${a.tilePatterns.map((k, v) => MapEntry(k.name, v))}');
          final seats = Directory('$dir/$c/seats')..createSync(recursive: true);
          for (final side in Side.values) {
            File('${seats.path}/${p}_${side.name}.jpg').writeAsBytesSync(ti.cropJpeg(g.seat(side), side: side));
          }
        }
      }
      summary[c] = '최종 $ok/$n, 뒷면 비율로만 한 자리 정답 $byColor/$n';
    }
    // ignore: avoid_print
    summary.forEach((k, v) => print('== $k: $v'));
  });
}
