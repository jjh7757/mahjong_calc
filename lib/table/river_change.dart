/// 강 띠·리치봉 띠의 거친 블록 스냅샷과 변화 척도. 판 상태 추적 2단계([RiverTracker])의 입력이다. 순수 Dart, API 호출 없음.
///
/// 모서리 통계([CornerStats])는 "얼마나 바뀌었나" 만 알면 됐지만, 강은 **어디에** 패가 더해졌는지(론 패 위치)까지 알아야 한다.
/// 그래서 띠를 블록(기본 가로 40칸)으로 나눠 블록마다 밝기 평균과 흰 면 여부를 둔다. 새로 흰 블록이 된 곳의 상자가
/// 마지막 버림패 위치다. 밝기 블록의 차이는 색과 무관한 변화 척도라 파란 리치봉·손·검은 기기도 잡는다.
/// 문턱값은 패 장수 단위([tileFracOf] 계열)로 적는다 — 사진 6장에 맞춘 픽셀 값을 두지 않기 위해(problem_log 24).
/// 설계: docs/state_tracking_design.md 6절(2단계 후보).
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'corner_change.dart' show CornerStats, analyzeCorners, cornerStats;
import 'fixed_layout.dart' show decodeSmall, whiteMask;
import 'grid_zones.dart';
import 'stick_slots.dart';
import 'table_layout.dart';

/// 상자 하나를 블록으로 나눈 스냅샷. 좌표는 모두 상자 안 블록 번호, [box] 는 이미지 기준(0~1000).
class ZoneSnapshot {
  final NormBox box;
  final int cols;
  final int rows;

  /// 블록 밝기 평균(0~255).
  final Uint8List gray;

  /// 블록 안 흰 픽셀이 절반 이상이면 1.
  final Uint8List white;

  /// 상자 전체의 흰 픽셀 비율(0~1).
  final double whiteFrac;

  const ZoneSnapshot({
    required this.box,
    required this.cols,
    required this.rows,
    required this.gray,
    required this.white,
    required this.whiteFrac,
  });

  static ZoneSnapshot emptyFor(NormBox box) =>
      ZoneSnapshot(box: box, cols: 0, rows: 0, gray: Uint8List(0), white: Uint8List(0), whiteFrac: 0);

  int get blocks => cols * rows;

  bool _sameShape(ZoneSnapshot o) => o.cols == cols && o.rows == rows;

  /// 밝기 블록 평균 절대 차(0~1). 모양이 다르면 1(전부 바뀐 것으로).
  double diff(ZoneSnapshot o) {
    if (!_sameShape(o) || blocks == 0) return blocks == 0 && o.blocks == 0 ? 0 : 1;
    var sum = 0;
    for (var i = 0; i < gray.length; i++) {
      sum += (gray[i] - o.gray[i]).abs();
    }
    return sum / gray.length / 255;
  }

  /// 밝기가 [minDelta] 이상 바뀐 블록의 비율(0~1). 넓은 띠 안의 작은 물건(홈에 꽂은 리치봉)은 평균 차([diff])로는 묽어진다.
  double changedFrac(ZoneSnapshot o, {int minDelta = 25}) {
    if (!_sameShape(o) || blocks == 0) return blocks == 0 && o.blocks == 0 ? 0 : 1;
    var n = 0;
    for (var i = 0; i < gray.length; i++) {
      if ((gray[i] - o.gray[i]).abs() >= minDelta) n++;
    }
    return n / gray.length;
  }

  /// 흰 면이 패 몇 장 분량인지.
  double tiles(double tileFrac) => tileFrac <= 0 ? 0 : whiteFrac / tileFrac;

  /// [base] 에는 없고 지금은 흰 블록들의 상자(이미지 기준 0~1000). 그런 블록이 [minBlocks] 미만이면 null.
  /// 떨어진 잡음 블록에 끌리지 않게 가장 큰 덩어리(4방향 이웃)만 쓴다.
  NormBox? newWhite(ZoneSnapshot base, {int minBlocks = 2}) {
    if (!_sameShape(base) || blocks == 0) return null;
    final fresh = Uint8List(blocks);
    var n = 0;
    for (var i = 0; i < blocks; i++) {
      if (white[i] == 1 && base.white[i] == 0) {
        fresh[i] = 1;
        n++;
      }
    }
    if (n < minBlocks) return null;
    // 가장 큰 덩어리.
    final seen = Uint8List(blocks);
    List<int> best = const [];
    for (var i = 0; i < blocks; i++) {
      if (fresh[i] == 0 || seen[i] == 1) continue;
      final comp = <int>[];
      final todo = [i];
      seen[i] = 1;
      while (todo.isNotEmpty) {
        final k = todo.removeLast();
        comp.add(k);
        final x = k % cols, y = k ~/ cols;
        for (final (dx, dy) in const [(1, 0), (-1, 0), (0, 1), (0, -1)]) {
          final nx = x + dx, ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= cols || ny >= rows) continue;
          final j = ny * cols + nx;
          if (fresh[j] == 1 && seen[j] == 0) {
            seen[j] = 1;
            todo.add(j);
          }
        }
      }
      if (comp.length > best.length) best = comp;
    }
    if (best.length < minBlocks) return null;
    var x0 = cols, y0 = rows, x1 = -1, y1 = -1;
    for (final k in best) {
      final x = k % cols, y = k ~/ cols;
      x0 = math.min(x0, x);
      y0 = math.min(y0, y);
      x1 = math.max(x1, x);
      y1 = math.max(y1, y);
    }
    final bw = box.width / cols, bh = box.height / rows;
    return NormBox(
      (box.ymin + y0 * bh).round(),
      (box.xmin + x0 * bw).round(),
      (box.ymin + (y1 + 1) * bh).round(),
      (box.xmin + (x1 + 1) * bw).round(),
    );
  }

  Map<String, dynamic> toJson() => {'box': box.toList(), 'cols': cols, 'rows': rows, 'white': whiteFrac};

  @override
  String toString() => 'ZoneSnapshot(${cols}x$rows, white ${(whiteFrac * 100).toStringAsFixed(1)}%)';
}

/// [box] 의 스냅샷. [white] 는 [whiteMask] 로 만든 전체 마스크. 블록 한 변은 상자 너비를 [cols] 로 나눈 크기(최소 2px).
ZoneSnapshot snapshotIn(img.Image im, Uint8List white, NormBox box, {int cols = 40}) {
  final r = box.toPixels(im.width, im.height);
  if (r.width < 2 || r.height < 2) return ZoneSnapshot.emptyFor(box);
  final bs = math.max(2, r.width ~/ cols);
  final c = math.max(1, r.width ~/ bs), rows = math.max(1, r.height ~/ bs);
  final gray = Uint8List(c * rows);
  final wh = Uint8List(c * rows);
  var whiteCount = 0;
  final n = bs * bs;
  for (var by = 0; by < rows; by++) {
    for (var bx = 0; bx < c; bx++) {
      var lum = 0, w = 0;
      for (var y = r.y + by * bs; y < r.y + (by + 1) * bs; y++) {
        final row = y * im.width;
        for (var x = r.x + bx * bs; x < r.x + (bx + 1) * bs; x++) {
          final p = im.getPixel(x, y);
          lum += (p.r * 299 + p.g * 587 + p.b * 114) ~/ 1000;
          w += white[row + x];
        }
      }
      final k = by * c + bx;
      gray[k] = lum ~/ n;
      wh[k] = w * 2 >= n ? 1 : 0;
      whiteCount += w;
    }
  }
  return ZoneSnapshot(box: box, cols: c, rows: rows, gray: gray, white: wh, whiteFrac: whiteCount / (n * c * rows));
}

/// 한 프레임의 추적 입력 전부: 모서리 통계(1단계) + 강 띠·리치봉 띠 스냅샷(2단계). 한 번 디코딩으로.
class TableFrameStats {
  final Map<Side, CornerStats> corners;
  final Map<Side, ZoneSnapshot> rivers;
  final Map<Side, ZoneSnapshot> strips;

  /// 자리별 홈에 리치봉이 보이는지([stickSlotsIn], 색 무관 픽셀 판정, 2026-11-10). 격자에 리치봉 상자가 없으면 빈 맵.
  final Map<Side, bool> sticksSeen;
  const TableFrameStats({required this.corners, required this.rivers, required this.strips, this.sticksSeen = const {}});
}

/// 미리보기 JPEG → 프레임 통계. `compute()` 에 그대로 넘길 수 있다. [analyzeCorners] 의 확장판.
TableFrameStats analyzeTableFrame((Uint8List, GridZones) args) {
  final (jpeg, grid) = args;
  final im = decodeSmall(jpeg);
  final white = whiteMask(im);
  return TableFrameStats(
    corners: cornerStats(im, white, grid),
    rivers: {for (final s in Side.values) s: snapshotIn(im, white, grid.riverBand(s))},
    strips: {for (final s in Side.values) s: snapshotIn(im, white, grid.stickStrip(s))},
    // 리치봉 상자(자동 맞추기·격자 편집)가 있을 때만: 없으면 가운데 칸 70% 라 홈 위치가 맞지 않는다.
    sticksSeen: grid.sticks == null ? const {} : stickSlotsIn(im, grid.sticksZone),
  );
}

/// 패 한 장의 앞면이 [side] 강 띠에서 차지하는 비율 어림([tileFracOf] 와 같은 기준: 긴 변 4000 사진에서 앞면 폭 100px).
double riverTileFracOf(GridZones grid, Side side, {double tileW = 0.025, double tileH = 0.044}) {
  final b = grid.riverBand(side);
  final w = b.width / 1000, h = b.height / 1000;
  if (w <= 0 || h <= 0) return 0;
  return (tileW * tileH) / (w * h);
}

Map<Side, double> riverTileFracsOf(GridZones grid) => {for (final s in Side.values) s: riverTileFracOf(grid, s)};
