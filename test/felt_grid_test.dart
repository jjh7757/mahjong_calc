import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;

math.Point<double> _pt(double x, double y) => math.Point(x, y);

/// 회색 바닥 위 초록 펠트(모서리 [felt], 비율 좌표)와 남색 기기를 그린 사진. [arm] 이면 오른쪽 변을 가리는 팔, [tiles] 면 강 자리에 흰 패.
img.Image _photo(List<math.Point<double>> felt, {bool arm = false, bool tiles = false, bool device = true, int w = 1020, int h = 765}) {
  final im = img.Image(width: w, height: h);
  img.fill(im, color: img.ColorRgb8(90, 90, 90));
  img.Point px(math.Point<double> p) => img.Point(p.x * w, p.y * h);
  img.fillPolygon(im, vertices: felt.map(px).toList(), color: img.ColorRgb8(25, 95, 65));
  final plane = FeltPlane.of(FeltQuad(felt[0], felt[1], felt[2], felt[3]))!;
  List<img.Point> rect(double u0, double v0, double u1, double v1) =>
      [plane.at(u0, v0), plane.at(u1, v0), plane.at(u1, v1), plane.at(u0, v1)].map(px).toList();
  if (device) img.fillPolygon(im, vertices: rect(0.402, 0.403, 0.598, 0.597), color: img.ColorRgb8(30, 40, 95));
  if (tiles) {
    for (var i = 0; i < 6; i++) {
      final u = 0.41 + i * 0.03;
      img.fillPolygon(im, vertices: rect(u, 0.61, u + 0.027, 0.65), color: img.ColorRgb8(240, 240, 235));
    }
  }
  if (arm) {
    final a = plane.at(1.15, 0.45), b = plane.at(0.75, 0.45), c = plane.at(0.75, 0.6), d = plane.at(1.15, 0.6);
    img.fillPolygon(im, vertices: [a, b, c, d].map(px).toList(), color: img.ColorRgb8(200, 160, 140));
  }
  return im;
}

const _straight = [math.Point(0.2, 0.1), math.Point(0.8, 0.1), math.Point(0.8, 0.9), math.Point(0.2, 0.9)];

FeltQuad _q(List<math.Point<double>> c) => FeltQuad(c[0], c[1], c[2], c[3]);

FeltQuad _shift(FeltQuad q, double dx, double dy) =>
    _q([for (final p in q.corners) _pt(p.x + dx, p.y + dy)]);

void main() {
  group('펠트 찾기', () {
    test('반듯한 탁자: 네 모서리가 맞고 믿을 만함', () {
      final r = readFelt(_photo(_straight, tiles: true))!;
      expect(r.ok, isTrue);
      for (var i = 0; i < 4; i++) {
        expect((r.quad.corners[i].x - _straight[i].x).abs(), lessThan(0.004));
        expect((r.quad.corners[i].y - _straight[i].y).abs(), lessThan(0.004));
      }
    });

    test('기운 탁자와 원근', () {
      final tilted = [_pt(0.25, 0.15), _pt(0.78, 0.08), _pt(0.85, 0.82), _pt(0.3, 0.92)];
      final r = readFelt(_photo(tilted))!;
      expect(r.ok, isTrue);
      for (var i = 0; i < 4; i++) {
        expect((r.quad.corners[i].x - tilted[i].x).abs(), lessThan(0.005));
        expect((r.quad.corners[i].y - tilted[i].y).abs(), lessThan(0.005));
      }
    });

    test('팔이 변을 가려도 곧은 구간으로 변을 찾는다', () {
      final r = readFelt(_photo(_straight, arm: true))!;
      expect(r.ok, isTrue);
      expect((r.quad.topRight.x - 0.8).abs(), lessThan(0.005));
      expect((r.quad.bottomRight.x - 0.8).abs(), lessThan(0.005));
    });

    test('펠트가 없으면 null', () {
      final im = img.Image(width: 400, height: 300);
      img.fill(im, color: img.ColorRgb8(90, 90, 90));
      expect(readFelt(im), isNull);
    });

    test('가운데에 기기가 없는 초록 사각형은 믿지 않는다', () {
      final r = readFelt(_photo(_straight, device: false))!;
      expect(r.deviceShare, lessThan(feltMinDevice));
      expect(r.ok, isFalse);
    });

    test('파란 펠트도 그 사진의 색을 재서 찾는다', () {
      final im = _photo(_straight, tiles: true);
      for (final p in im) {
        final g = p.g, b = p.b;
        p.g = b;
        p.b = g;
      }
      final r = readFelt(im)!;
      expect(r.ok, isTrue);
      expect((r.quad.topLeft.x - 0.2).abs(), lessThan(0.005));
    });

    test('어두운 사진·따뜻한 조명에서도 찾는다', () {
      for (final (rr, gg, bb) in [(0.5, 0.5, 0.5), (1.2, 1.0, 0.75)]) {
        final im = _photo(_straight, tiles: true);
        for (final p in im) {
          p.r = (p.r * rr).round().clamp(0, 255);
          p.g = (p.g * gg).round().clamp(0, 255);
          p.b = (p.b * bb).round().clamp(0, 255);
        }
        final r = readFelt(im)!;
        expect(r.ok, isTrue, reason: '$rr $gg $bb');
        expect((r.quad.bottomRight.x - 0.8).abs(), lessThan(0.005));
      }
    });

    test('곧은 패 줄을 변으로 잡으면 믿지 않는다', () {
      // 펠트 아래 끝이 사진 밖이고, 그 앞에 흰 패 줄이 사진 끝까지 가로질러 윤곽이 패 줄 위에서 끊긴다. 패 줄 너머에도 펠트가 있다.
      final far = [_pt(0.2, 0.1), _pt(0.8, 0.1), _pt(0.8, 1.3), _pt(0.2, 1.3)];
      final im = _photo(far);
      img.fillRect(im, x1: 0, y1: (765 * 0.72).round(), x2: 1019, y2: (765 * 0.77).round(), color: img.ColorRgb8(240, 240, 235));
      final r = readFelt(im);
      expect(r == null || !r.ok, isTrue);
    });

    test('탁자 절반이 사진 밖이면 믿지 않는다', () {
      final half = [_pt(0.2, -0.6), _pt(0.8, -0.6), _pt(0.8, 0.5), _pt(0.2, 0.5)];
      final r = readFelt(_photo(half));
      expect(r == null || !r.ok, isTrue);
    });
  });

  group('격자 계산', () {
    test('반듯한 탁자: 가운데 칸은 편 좌표 0.30, 리치봉은 기기 + 여유', () {
      final g = gridFromFelt(_q(_straight))!;
      expect(g.x1, 320); // 0.2 + 0.6 * 0.2
      expect(g.x2, 680);
      expect(g.y1, 260); // 0.1 + 0.8 * 0.2
      expect(g.y2, 740);
      expect(g.valid, isTrue);
      final s = g.sticks!;
      expect(s.xmin, closeTo(1000 * (0.2 + 0.6 * (0.5 - feltDeviceW / 2)) - feltSticksPad, 1));
      expect(s.ymax, closeTo(1000 * (0.1 + 0.8 * (0.5 + feltDeviceH / 2)) + feltSticksPad, 1));
    });

    test('선이 사진을 벗어나면 null', () {
      final big = [_pt(-1.5, -1.5), _pt(2.5, -1.5), _pt(2.5, 2.5), _pt(-1.5, 2.5)];
      expect(gridFromFelt(_q(big)), isNull);
    });
  });

  group('카메라 이동 감지', () {
    final a = _q(_straight);

    test('처음 안정된 위치는 기준만 잡고 알리지 않는다', () {
      final w = FeltWatch();
      expect(w.add(a), isNull);
      expect(w.add(a), isNull);
      expect(w.add(a), isNull);
      expect(w.basis, isNotNull);
    });

    test('새 자리에 3장 연속이면 알린다', () {
      final w = FeltWatch()..reset(a);
      final b = _shift(a, 0.05, 0);
      expect(w.add(b), isNull);
      expect(w.add(b), isNull);
      expect(w.add(b), isNotNull);
      expect((w.basis!.topLeft.x - b.topLeft.x).abs(), lessThan(1e-9));
    });

    test('한두 장 튀는 판독은 무시한다', () {
      final w = FeltWatch()..reset(a);
      expect(w.add(_shift(a, 0.05, 0)), isNull);
      expect(w.add(a), isNull);
      expect(w.add(_shift(a, 0.05, 0)), isNull);
      expect(w.add(a), isNull);
      expect((w.basis!.topLeft.x - a.topLeft.x).abs(), lessThan(1e-9));
    });

    test('움직이는 중(프레임마다 다름)에는 알리지 않는다', () {
      final w = FeltWatch()..reset(a);
      for (var i = 1; i <= 8; i++) {
        expect(w.add(_shift(a, 0.03 * i, 0)), isNull);
      }
    });

    test('못 읽은 프레임은 세지 않는다', () {
      final w = FeltWatch()..reset(a);
      final b = _shift(a, 0.05, 0);
      expect(w.add(b), isNull);
      expect(w.add(null), isNull);
      expect(w.add(b), isNull);
      expect(w.add(null), isNull);
      expect(w.add(b), isNotNull);
    });

    test('손이 모서리 하나를 끌어도 같은 위치', () {
      final moved = FeltQuad(_pt(a.topLeft.x + 0.05, a.topLeft.y), a.topRight, a.bottomRight, a.bottomLeft);
      expect(sameFelt(a, moved), isTrue);
      final w = FeltWatch()..reset(a);
      for (var i = 0; i < 5; i++) {
        expect(w.add(moved), isNull);
      }
    });
  });

  test('중앙값은 튄 값 하나에 끌리지 않는다', () {
    final a = _q(_straight);
    final m = medianFelt([a, a, _shift(a, 0.2, 0)]);
    expect(m.topLeft.x, closeTo(0.2, 1e-9));
  });
}
