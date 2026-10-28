import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/rectify.dart';

/// 회색 바닥에 [deg] 만큼 돌린 초록 정사각형(펠트)과 그 위 흰 패 한 줄을 그린 합성 사진(4:3).
(img.Image, List<math.Point<double>>) _table(double deg, {int w = 800, int h = 600}) {
  final im = img.Image(width: w, height: h);
  img.fill(im, color: img.ColorRgb8(90, 90, 90));
  final c = math.Point(w / 2, h / 2);
  const half = 200.0;
  final th = deg * math.pi / 180;
  math.Point<double> rot(double x, double y) =>
      math.Point(c.x + x * math.cos(th) - y * math.sin(th), c.y + x * math.sin(th) + y * math.cos(th));
  final corners = [rot(-half, -half), rot(half, -half), rot(half, half), rot(-half, half)];
  img.fillPolygon(im,
      vertices: [for (final p in corners) img.Point(p.x, p.y)], color: img.ColorRgb8(30, 110, 60));
  // 위 자리 손패 자리에 흰 패 줄(펠트 안, 가장자리 가까이)
  final strip = [rot(-120, -185), rot(120, -185), rot(120, -165), rot(-120, -165)];
  img.fillPolygon(im, vertices: [for (final p in strip) img.Point(p.x, p.y)], color: img.ColorRgb8(240, 240, 235));
  return (im, [for (final p in corners) math.Point(p.x / w, p.y / h)]);
}

void main() {
  test('반듯한 펠트: 네 모서리를 펠트 꼭짓점 근처로', () {
    final (im, truth) = _table(0);
    final q = findFeltQuad(im)!;
    for (final (got, want) in [(q.topLeft, truth[0]), (q.topRight, truth[1]), (q.bottomRight, truth[2]), (q.bottomLeft, truth[3])]) {
      expect((got.x - want.x).abs(), lessThan(0.02));
      expect((got.y - want.y).abs(), lessThan(0.02));
    }
  });

  test('25° 기운 펠트: 모서리 순서(위 왼쪽부터 시계 방향)와 위치', () {
    final (im, truth) = _table(25);
    final q = findFeltQuad(im)!;
    // 25° 시계 방향으로 돌리면 원래 왼쪽 위 꼭짓점이 x+y 최소인 자리에 남는다.
    for (final (got, want) in [(q.topLeft, truth[0]), (q.topRight, truth[1]), (q.bottomRight, truth[2]), (q.bottomLeft, truth[3])]) {
      expect((got.x - want.x).abs(), lessThan(0.03), reason: '$got vs $want');
      expect((got.y - want.y).abs(), lessThan(0.03), reason: '$got vs $want');
    }
  });

  test('편 사진: 펠트가 정사각형 가운데(feltSpan), 위 자리 패 줄이 표준 격자 위 칸에', () {
    final (im, _) = _table(25);
    final q = findFeltQuad(im)!;
    final r = rectify(im, q, size: 500);
    final (a, b) = feltSpan;
    bool green(int x, int y) {
      final p = r.getPixel(x, y);
      return p.g > p.r + 20 && p.g > p.b;
    }

    int px(int norm) => norm * 500 ~/ 1000;
    // 펠트 안쪽 네 군데(위쪽은 흰 패 줄을 피해 왼쪽 끝)는 초록, 펠트 밖 테두리는 초록 아님
    for (final (x, y) in [(a + 30, 500 - 60), (b - 30, 500 - 60), (a + 60, a + 30), (500 - 60, b - 30)]) {
      expect(green(px(x), px(y)), isTrue, reason: '($x,$y)');
    }
    expect(green(px(a - 40), px(500)), isFalse);
    // 흰 패 줄: 편 사진 가운데 세로줄에서 펠트 위 끝과 표준 격자 y1 사이에 있다(모서리 찾기 오차 몇 px 는 허용).
    final whiteYs = [
      for (var y = px(feltSpan.$1); y < px(standardGrid.y1); y++)
        if (r.getPixel(px(500), y).r > 200 && r.getPixel(px(500), y).g > 200) y,
    ];
    expect(whiteYs, isNotEmpty);
  });

  test('펠트가 없으면 null(펴지 않고 원래 격자로)', () {
    final im = img.Image(width: 400, height: 300);
    img.fill(im, color: img.ColorRgb8(90, 90, 90));
    expect(findFeltQuad(im), isNull);
  });
}
