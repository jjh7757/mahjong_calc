// 작탁 바깥 끝 상자(tableBoxOf)를 여유별로 B·C·D 원본 6장에 그린다(자르기만 하기의 여유 정하기, NOTES 38).
//   flutter test tool/table_box_test.dart   → experiments/rectify/results/table_box/<사진>.jpg
// 선 색: 노랑 = 펠트 모서리, 빨강 4% · 초록 7% · 파랑 10%.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/rectify.dart';

const _photos = 'experiments/field_20261024/kakao_photos';
const _out = 'experiments/rectify/results/table_box';

void main() {
  test('table box', () {
    Directory(_out).createSync(recursive: true);
    for (final photo in ['k25', 'k28', 'k15', 'k26', 'k12', 'k16']) {
      final im = img.bakeOrientation(img.decodeJpg(File('$_photos/$photo.jpg').readAsBytesSync())!);
      final small = img.copyResize(im, width: 1000);
      final q = findFeltQuad(small)!;
      final out = img.copyResize(im, width: 1200);
      final w = out.width, h = out.height;
      final felt = q.corners;
      for (var i = 0; i < 4; i++) {
        final a = felt[i], b = felt[(i + 1) % 4];
        img.drawLine(out, x1: (a.x * w).round(), y1: (a.y * h).round(), x2: (b.x * w).round(), y2: (b.y * h).round(),
            color: img.ColorRgb8(255, 220, 0), thickness: 2);
      }
      for (final (m, c) in [(0.04, img.ColorRgb8(230, 30, 30)), (0.07, img.ColorRgb8(0, 200, 0)), (0.10, img.ColorRgb8(0, 120, 255))]) {
        final t = tableBoxOf(q, margin: m);
        img.drawRect(out, x1: t.xmin * w ~/ 1000, y1: t.ymin * h ~/ 1000, x2: t.xmax * w ~/ 1000, y2: t.ymax * h ~/ 1000,
            color: c, thickness: 3);
        // ignore: avoid_print
        print('$photo margin $m box $t');
      }
      File('$_out/$photo.jpg').writeAsBytesSync(img.encodeJpg(out, quality: 85));
    }
  });
}
