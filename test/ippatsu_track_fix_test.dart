// 11-14 매장 동4국 1본장(리치 → 일발 쯔모인데 일발 빠짐, 2026-11-16)의 두 원인을 고친 것:
// ① 기준 없이 처음 잡은 펠트 위치와 저장 격자를 견줘 어긋났으면 다시 맞춤 ② 울기 픽셀 추적 칸을 펠트 안쪽으로 자름.
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/fixed_layout.dart' show whiteMask;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/tracker.dart';

math.Point<double> _pt(double x, double y) => math.Point(x, y);
FeltQuad _rect(double x0, double y0, double x1, double y1) => FeltQuad(_pt(x0, y0), _pt(x1, y0), _pt(x1, y1), _pt(x0, y1));
FeltQuad _shift(FeltQuad q, double dx, double dy) {
  final c = [for (final p in q.corners) _pt(p.x + dx, p.y + dy)];
  return FeltQuad(c[0], c[1], c[2], c[3]);
}

void main() {
  final a = _rect(0.2, 0.1, 0.8, 0.9);

  group('처음 잡은 펠트 기준', () {
    test('기준 없이 처음 안정되면 adoptedFirst 로 한 번 알리고, 옮겨진 것은 반환값으로 알린다', () {
      final w = FeltWatch();
      w.add(a);
      w.add(a);
      expect(w.adoptedFirst, isFalse);
      expect(w.add(a), isNull);
      expect(w.adoptedFirst, isTrue);
      expect(w.add(a), isNull);
      expect(w.adoptedFirst, isFalse);
      final b = _shift(a, 0.05, 0);
      w.add(b);
      w.add(b);
      expect(w.add(b), isNotNull);
      expect(w.adoptedFirst, isFalse);
    });

    test('기준을 주고 시작하면(펠트로 맞춘 격자) adoptedFirst 는 안 선다', () {
      final w = FeltWatch()..reset(a);
      for (var i = 0; i < 5; i++) {
        w.add(a);
        expect(w.adoptedFirst, isFalse);
      }
    });

    test('gridShiftOf 는 리치봉 상자 중심만 본다', () {
      final g = gridFromFelt(a)!;
      expect(gridShiftOf(g, g), 0);
      // 11-14 2반장: 격자를 맞춘 뒤 카메라가 가로 7.5%·세로 6% 옮겨짐.
      final moved = gridFromFelt(_shift(a, -0.075, 0.06))!;
      expect(gridShiftOf(g, moved), closeTo(75, 1));
      expect(gridShiftOf(g, moved), greaterThanOrEqualTo(feltGridShiftMax));
      // 손으로 선만 옮긴 격자는 같은 자리.
      expect(gridShiftOf(g.copyWith(x2: g.x2 + 90, y1: g.y1 - 60), g), 0);
      // 손으로 맞춘 리치봉 상자가 넉넉해 중심이 조금 치우친 것(10-31 매장 21~24)은 문턱 아래.
      final s = g.sticks!;
      final loose = g.copyWith(sticks: NormBox(s.ymin - 40, s.xmin, s.ymax, s.xmax + 46));
      expect(gridShiftOf(loose, g), lessThan(feltGridShiftMax));
      // 리치봉 상자가 없는 격자는 견주지 않는다.
      expect(gridShiftOf(GridZones.initial, moved), 0);
    });

    test('펠트 안쪽 상자: 변에서 feltBoxMargin 안쪽, gridFromFelt 가 채운다', () {
      expect(feltBoxOf(a)!.toList(), [100 + feltBoxMargin, 200 + feltBoxMargin, 900 - feltBoxMargin, 800 - feltBoxMargin]);
      expect(gridFromFelt(a)!.feltBox, feltBoxOf(a));
      // 기운 사각형(11-14 14:32 펠트)은 네 모서리 안에 드는 상자.
      final skew = FeltQuad(_pt(0.065, 0.095), _pt(0.95, 0.064), _pt(0.961, 0.927), _pt(0.115, 0.96));
      expect(feltBoxOf(skew)!.toList(), [95 + feltBoxMargin, 115 + feltBoxMargin, 927 - feltBoxMargin, 950 - feltBoxMargin]);
      expect(feltBoxOf(_rect(0.4, 0.4, 0.6, 0.6)), isNull);
    });
  });

  group('울기 추적 칸', () {
    const g = GridZones(x1: 250, x2: 750, y1: 200, y2: 800);
    final f = g.withFeltBox(const NormBox(110, 130, 910, 940));

    test('펠트 안쪽 상자로 자르고, 판독 크롭 칸은 그대로', () {
      expect(g.cornerWatchCell(Side.bottom), g.cornerCell(Side.bottom));
      expect(f.cornerWatchCell(Side.bottom).toList(), [800, 750, 910, 940]);
      expect(f.cornerWatchCell(Side.right).toList(), [110, 750, 200, 940]);
      expect(f.cornerWatchCell(Side.top).toList(), [110, 130, 200, 250]);
      expect(f.cornerWatchCell(Side.left).toList(), [800, 130, 910, 250]);
      expect(f.cornerCell(Side.bottom).toList(), [800, 750, 1000, 1000]);
    });

    test('격자와 펠트가 안 맞아 칸이 너무 작아지면 자르지 않는다', () {
      final bad = g.withFeltBox(const NormBox(110, 130, 820, 940));
      expect(bad.cornerWatchCell(Side.bottom).toList(), [800, 750, 1000, 1000]);
      expect(bad.cornerWatchCell(Side.top).toList(), [110, 130, 200, 250]);
    });

    test('JSON 왕복·복사·지우기', () {
      expect(GridZones.fromJson(f.toJson()), f);
      expect(GridZones.fromJson(g.toJson())!.feltBox, isNull);
      expect(f.copyWith(x1: 260).feltBox, f.feltBox);
      expect(f.withFeltBox(null), g);
      expect(f == g, isFalse);
    });

    test('탁자의 흰 테두리가 밝아져도 울기 추적 통계는 그대로, 장면 변화용 통계는 바뀐다', () {
      const w = 600, h = 600;
      img.Image table(int rim) {
        final im = img.Image(width: w, height: h)..clear(img.ColorRgb8(rim, rim, rim));
        img.fillRect(im, x1: 60, y1: 60, x2: 560, y2: 560, color: img.ColorRgb8(30, 110, 70)); // 펠트 0.10~0.93
        return im;
      }

      final grid = g.withFeltBox(feltBoxOf(_rect(0.10, 0.10, 0.935, 0.935)));
      TableFrameStats st(img.Image im) => tableFrameStatsOf(im, whiteMask(im), grid);
      final dim = st(table(150)), bright = st(table(250));
      final frac = tileFracOf(grid, Side.right);
      for (final s in Side.values) {
        expect(bright.watchCorners[s]!.white, 0, reason: s.name);
        expect(dim.watchCorners[s]!.white, 0, reason: s.name);
      }
      // 예전 칸(테두리 포함)은 패 한 장 문턱을 훌쩍 넘게 바뀐다 — 이것이 헛 "울기 늘어남" 이었다.
      expect((bright.corners[Side.right]!.white - dim.corners[Side.right]!.white) / frac, greaterThan(1));
      // 펠트 상자가 없으면 두 통계가 같다.
      final plain = tableFrameStatsOf(table(250), whiteMask(table(250)), g);
      expect(plain.watchCorners[Side.right]!.white, plain.corners[Side.right]!.white);
    });

    test('펠트 위에 놓은 퐁 3장은 자른 칸에서도 패 3장쯤 늘어난다', () {
      const w = 600, h = 600;
      final grid = g.withFeltBox(feltBoxOf(_rect(0.10, 0.10, 0.935, 0.935)));
      img.Image table({bool pon = false}) {
        final im = img.Image(width: w, height: h)..clear(img.ColorRgb8(250, 250, 250));
        img.fillRect(im, x1: 60, y1: 60, x2: 560, y2: 560, color: img.ColorRgb8(30, 110, 70));
        if (pon) {
          // 아래 자리 모서리(오른쪽 아래) 펠트 위에 패 3장. 정사각 사진에서 패 한 장 = 가로 3.3%·세로 4.4% → 20×26 화소.
          for (var i = 0; i < 3; i++) {
            img.fillRect(im, x1: 470 + i * 22, y1: 500, x2: 470 + i * 22 + 19, y2: 525, color: img.ColorRgb8(245, 242, 235));
          }
        }
        return im;
      }

      final frac = tileFracOf(grid, Side.bottom, aspect: 1);
      final a0 = cornerWatchStats(table(), whiteMask(table()), grid)[Side.bottom]!;
      final a1 = cornerWatchStats(table(pon: true), whiteMask(table(pon: true)), grid)[Side.bottom]!;
      expect((a1.white - a0.white) / frac, closeTo(3, 0.8));
    });
  });

  group('리치한 사람 자기 모서리', () {
    test('grewSince 는 except 자리를 빼고 본다', () {
      final t = MeldTracker(tileFrac: {for (final s in Side.values) s: 0.1}, config: const TrackerConfig(pixelOnly: true));
      final t0 = DateTime(2026, 11, 16, 12);
      CornerStats st(double white) => CornerStats(white: white, pattern: 0, cx: 0.5, cy: 0.5);
      Map<Side, CornerStats> frame(double bottom) => {for (final s in Side.values) s: st(s == Side.bottom ? bottom : 0)};
      for (var i = 0; i < 4; i++) {
        t.onFrame(frame(0), t0.add(Duration(seconds: 3 * i)));
      }
      final before = t0.add(const Duration(seconds: 10));
      for (var i = 4; i < 8; i++) {
        t.onFrame(frame(0.3), t0.add(Duration(seconds: 3 * i)));
      }
      expect(t.grewSince(before), isTrue);
      expect(t.grewSince(before, except: Side.bottom), isFalse);
      expect(t.grewSince(before, except: Side.top), isTrue);
    });
  });
}
