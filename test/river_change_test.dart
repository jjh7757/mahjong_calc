import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/fixed_layout.dart' show whiteMask;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 강 띠 블록 스냅샷. 합성 그림(펠트 + 흰 패 면 + 검은 무늬)으로 잰다.
void main() {
  const grid = GridZones.initial;
  const w = 960, h = 720;

  img.Image felt() => img.Image(width: w, height: h)..clear(img.ColorRgb8(30, 110, 70));

  /// 패 한 장(24×32, 가운데 검은 무늬).
  void tile(img.Image im, int x, int y) {
    img.fillRect(im, x1: x, y1: y, x2: x + 23, y2: y + 31, color: img.ColorRgb8(245, 242, 235));
    img.fillRect(im, x1: x + 9, y1: y + 13, x2: x + 14, y2: y + 18, color: img.ColorRgb8(20, 20, 20));
  }

  /// 아래 자리 강 띠 첫 줄에 n 장.
  img.Image river(int n) {
    final im = felt();
    final r = grid.riverBand(Side.bottom).toPixels(w, h);
    for (var i = 0; i < n; i++) {
      tile(im, r.x + 20 + i * 26, r.y + 6);
    }
    return im;
  }

  ZoneSnapshot snap(img.Image im, Side side) => snapshotIn(im, whiteMask(im), grid.riverBand(side));

  test('띠 구역: 강 띠는 lastZone 전체, 리치봉 띠는 그 안쪽(기기 가장자리) 1/4', () {
    for (final s in Side.values) {
      final last = grid.lastZone(s), band = grid.riverBand(s), strip = grid.stickStrip(s);
      expect(band, last);
      expect(band.containsCenterOf(strip), isTrue);
      expect(strip.width * strip.height, lessThan(band.width * band.height ~/ 3));
    }
    // 아래 자리: 리치봉 띠는 가운데(위쪽)에 붙고, 강 띠는 그 사람 쪽 끝까지.
    expect(grid.stickStrip(Side.bottom).ymin, grid.riverBand(Side.bottom).ymin);
    expect(grid.stickStrip(Side.bottom).ymax, lessThan(grid.riverBand(Side.bottom).ymax));
    expect(grid.stickStrip(Side.top).ymax, grid.riverBand(Side.top).ymax);
  });

  test('빈 펠트는 흰 면 0, 밝기 차 0', () {
    final a = snap(felt(), Side.bottom), b = snap(felt(), Side.bottom);
    expect(a.whiteFrac, 0);
    expect(a.diff(b), 0);
    expect(a.newWhite(b), isNull);
  });

  test('패가 한 장 늘면 흰 면이 패 1장 분량 늘고 새 흰 상자가 그 패를 감싼다', () {
    final base = snap(river(5), Side.bottom);
    final cur = snap(river(6), Side.bottom);
    final frac = riverTileFracOf(grid, Side.bottom);
    final delta = (cur.whiteFrac - base.whiteFrac) / frac;
    // 합성 패(24×32 / 960)는 기준 패(폭 2.5%)보다 작아 1장 미만으로 잰다. 0.3~1.5장 사이면 된다.
    expect(delta, inInclusiveRange(0.3, 1.5));
    final box = cur.newWhite(base)!;
    final r = grid.riverBand(Side.bottom).toPixels(w, h);
    final tx = r.x + 20 + 5 * 26, ty = r.y + 6;
    final px = box.toPixels(w, h);
    // 상자가 여섯째 패를 덮고(블록 단위라 조금 넉넉), 다섯째 패까지 번지지 않는다.
    expect(px.x, lessThanOrEqualTo(tx + 2));
    expect(px.x + px.width, greaterThanOrEqualTo(tx + 22));
    expect(px.y, lessThanOrEqualTo(ty + 2));
    expect(px.x, greaterThan(tx - 26));
    // 밝기 차는 작다(패 하나만큼).
    expect(cur.diff(base), lessThan(0.2));
    expect(cur.diff(base), greaterThan(0));
  });

  test('손이 지나가면 밝기 차가 크다', () {
    final base = snap(river(5), Side.bottom);
    final hand = river(5);
    final r = grid.riverBand(Side.bottom).toPixels(w, h);
    img.fillRect(hand, x1: r.x, y1: r.y, x2: r.x + r.width ~/ 2, y2: r.y + r.height - 1, color: img.ColorRgb8(214, 176, 146));
    expect(snap(hand, Side.bottom).diff(base), greaterThan(0.1));
  });

  test('analyzeTableFrame 은 모서리·강·리치봉 띠를 한 번에 준다', () {
    final jpeg = img.encodeJpg(river(3));
    final stats = analyzeTableFrame((jpeg, grid));
    expect(stats.corners.length, 4);
    expect(stats.rivers.length, 4);
    expect(stats.strips.length, 4);
    expect(stats.rivers[Side.bottom]!.whiteFrac, greaterThan(0));
    expect(stats.rivers[Side.top]!.whiteFrac, 0);
  });
}
