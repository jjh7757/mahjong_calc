import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/fixed_layout.dart' show whiteMask;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 모서리 칸 픽셀 통계. 합성 그림(펠트 + 흰 패 면 + 검은 무늬)으로 잰다.
void main() {
  const grid = GridZones.initial;
  const w = 960, h = 720;

  img.Image felt() => img.Image(width: w, height: h)..clear(img.ColorRgb8(30, 110, 70));

  /// 패 한 장(24×32, 가운데 검은 무늬).
  void tile(img.Image im, int x, int y) {
    img.fillRect(im, x1: x, y1: y, x2: x + 23, y2: y + 31, color: img.ColorRgb8(245, 242, 235));
    img.fillRect(im, x1: x + 9, y1: y + 13, x2: x + 14, y2: y + 18, color: img.ColorRgb8(20, 20, 20));
  }

  /// 아래 자리 모서리 칸(오른쪽 아래) 안에 퐁 3장.
  img.Image withPon() {
    final im = felt();
    final r = grid.cornerCell(Side.bottom).toPixels(w, h);
    for (var i = 0; i < 3; i++) {
      tile(im, r.x + 30 + i * 27, r.y + 80);
    }
    return im;
  }

  CornerStats stats(img.Image im, Side side) => cornerStatsIn(im, whiteMask(im), grid.cornerCell(side));

  test('빈 펠트는 흰 면 0, 무늬 0', () {
    final s = stats(felt(), Side.bottom);
    expect(s.white, 0);
    expect(s.pattern, 0);
  });

  test('퐁 3장은 패 3장 분량으로 재고 무늬가 잡힌다', () {
    final s = stats(withPon(), Side.bottom);
    final frac = tileFracOf(grid, Side.bottom);
    expect(frac, closeTo(0.015, 0.003));
    expect(s.tiles(frac), closeTo(3, 0.8));
    expect(s.pattern, greaterThan(0));
    // 무게중심은 패를 둔 곳(칸 왼쪽 위쪽).
    expect(s.cx, lessThan(0.5));
    expect(s.cy, lessThan(0.6));
    // 다른 자리는 그대로 비어 있다.
    expect(stats(withPon(), Side.top).white, 0);
  });

  test('같은 그림끼리 차이 0, 퐁이 놓이면 패 3장 분량만큼 달라진다', () {
    final a = stats(felt(), Side.bottom), b = stats(withPon(), Side.bottom);
    expect(a.diff(a), 0);
    expect(b.diff(b), 0);
    final frac = tileFracOf(grid, Side.bottom);
    expect((b.white - a.white) / frac, closeTo(3, 0.8));
  });

  test('소매(큰 흰 덩어리)가 들어오면 움직임 문턱(0.03)을 훌쩍 넘는다', () {
    final im = withPon();
    final r = grid.cornerCell(Side.bottom).toPixels(w, h);
    img.fillRect(im, x1: r.x + 60, y1: r.y + 40, x2: r.x + 180, y2: r.y + 160, color: img.ColorRgb8(240, 240, 240));
    final before = stats(withPon(), Side.bottom), after = stats(im, Side.bottom);
    expect(after.diff(before), greaterThan(0.03));
  });

  test('analyzeCorners 는 JPEG 바이트로 네 자리를 같은 값으로 잰다(compute 용)', () {
    final im = withPon();
    final jpeg = Uint8List.fromList(img.encodeJpg(im, quality: 92));
    final all = analyzeCorners((jpeg, grid));
    expect(all.keys, containsAll(Side.values));
    final direct = stats(im, Side.bottom);
    expect(all[Side.bottom]!.white, closeTo(direct.white, 0.005));
    expect(all[Side.left]!.white, closeTo(0, 0.005));
    expect(all[Side.bottom]!.toJson().keys, containsAll(['white', 'pattern', 'cx', 'cy']));
  });

  test('tileFracsOf 는 칸이 작을수록 한 장 비율이 크다', () {
    final f = tileFracsOf(grid);
    for (final s in Side.values) {
      expect(f[s], greaterThan(0));
    }
    // 위 자리 모서리(왼쪽 위, 280×173)는 아래 자리(255×287)보다 작다 → 비율이 크다.
    expect(f[Side.top]!, greaterThan(f[Side.bottom]!));
  });
}
