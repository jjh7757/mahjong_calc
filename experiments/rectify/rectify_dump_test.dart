// 개발 세트(B·C·D 원본·합성 기울기)를 펴서 미리보기(긴 변 800, 표준 격자 선)를 저장한다. 서버 호출 없음.
// flutter test experiments/rectify/rectify_dump_test.dart  → experiments/rectify/out/
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/rectify.dart';

const _photos = ['k25', 'k28', 'k15', 'k26', 'k12', 'k16'];

void main() {
  final src = 'experiments/field_20261024/kakao_photos';
  final out = Directory('experiments/rectify/out')..createSync(recursive: true);
  for (final p in [for (final p in _photos) p, for (final p in _photos) for (final v in 'abc'.split('')) 'tilted/${p}_$v']) {
    test(p, () {
      final im = img.decodeJpg(File('$src/$p.jpg').readAsBytesSync())!;
      final small = img.copyResize(im, width: 1000);
      final q = findFeltQuad(small);
      expect(q, isNotNull, reason: '펠트를 못 찾음');
      final r = rectify(im, q!, size: 1000);
      final g = standardGrid;
      final red = img.ColorRgb8(255, 0, 0);
      // 바람개비 5구역 선(GridZones.seat 와 같은 모양)
      img.drawLine(r, x1: 0, y1: g.y1, x2: g.x2, y2: g.y1, color: red, thickness: 3);
      img.drawLine(r, x1: g.x2, y1: 0, x2: g.x2, y2: g.y2, color: red, thickness: 3);
      img.drawLine(r, x1: g.x1, y1: g.y2, x2: 1000, y2: g.y2, color: red, thickness: 3);
      img.drawLine(r, x1: g.x1, y1: g.y1, x2: g.x1, y2: 1000, color: red, thickness: 3);
      final (a, b) = feltSpan;
      img.drawRect(r, x1: a, y1: a, x2: b, y2: b, color: img.ColorRgb8(255, 255, 0), thickness: 2);
      // 원본에 찾은 모서리
      final c = q.corners;
      for (var i = 0; i < 4; i++) {
        img.drawLine(small,
            x1: (c[i].x * small.width).round(), y1: (c[i].y * small.height).round(),
            x2: (c[(i + 1) % 4].x * small.width).round(), y2: (c[(i + 1) % 4].y * small.height).round(),
            color: img.ColorRgb8(255, 0, 255), thickness: 4);
      }
      final name = p.replaceAll('/', '_');
      File('${out.path}/${name}_rect.jpg').writeAsBytesSync(img.encodeJpg(r, quality: 85));
      File('${out.path}/${name}_quad.jpg').writeAsBytesSync(img.encodeJpg(img.copyResize(small, width: 600), quality: 80));
      // ignore: avoid_print
      print('QUAD $p ${q.toJson()} area=${q.area.toStringAsFixed(3)}');
    });
  }
}
