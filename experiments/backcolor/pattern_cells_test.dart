// 무늬 넓이를 자리 구역 전체(seat) vs 손패 칸(handCell, 울기 모서리 칸 제외)으로 재 비교(뒷면 색 합성 사진 6색 × B·C·D).
//   flutter test experiments/backcolor/pattern_cells_test.dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/fixed_layout.dart';
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
  test('seat vs handCell 무늬 넓이', () {
    for (final c in ['original', 'blue', 'green', 'yellow', 'orange', 'black']) {
      for (final s in _photos.keys) {
        for (final p in _photos[s]!) {
          final small = TableImage.decode(File('experiments/backcolor/photos/$c/$p.jpg').readAsBytesSync()).shrunkJpeg();
          final im = img.decodeJpg(small)!;
          final white = whiteMask(im);
          final g = _manual[s]!;
          String fmt(NormBox Function(Side) box) {
            final m = {for (final x in Side.values) x: tilePatternArea(im, white, box(x))};
            final sorted = Side.values.toList()..sort((a, b) => m[b]!.compareTo(m[a]!));
            final ratio = m[sorted[1]]! == 0 ? 999 : m[sorted[0]]! / m[sorted[1]]!;
            return '1등 ${sorted[0].name}${sorted[0] == _winner[s] ? '(정답)' : '(틀림)'} ${ratio.toStringAsFixed(1)}배 ${m.map((k, v) => MapEntry(k.name, v))}';
          }
          // ignore: avoid_print
          print('$c $s $p | seat ${fmt(g.seat)} | handCell ${fmt(g.handCell)}');
        }
      }
    }
  });
}
