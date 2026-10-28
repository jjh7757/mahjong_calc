/// 모서리 칸(울기 놓는 곳)의 픽셀 통계와 변화 척도. 판 상태 추적([MeldTracker])의 입력이다. 순수 Dart, API 호출 없음.
///
/// 카메라 헤드 미리보기(긴 변 960)를 3초마다 받아 격자의 모서리 칸 4개만 본다. 통계는 상자 안 흰 면(패 앞면) 비율,
/// 무늬 넓이 비율, 흰 픽셀 무게중심이다. "패 한 장" 의 크기는 사진마다 다르므로 [tileFracOf] 가 격자 칸 크기에서 어림하고,
/// 문턱값은 전부 패 장수 단위로 적는다(사진 6장에 맞춘 픽셀 값을 두지 않기 위해 — problem_log 24 교훈).
/// 설계: docs/state_tracking_design.md 3절·5절.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'fixed_layout.dart' show decodeSmall, tilePatternArea, whiteMask;
import 'grid_zones.dart';
import 'table_layout.dart';

/// 상자 하나의 통계. 비율은 모두 상자 넓이 기준(0~1), 무게중심은 상자 안 위치(0~1).
class CornerStats {
  final double white;
  final double pattern;
  final double cx;
  final double cy;
  const CornerStats({required this.white, required this.pattern, required this.cx, required this.cy});

  static const CornerStats empty = CornerStats(white: 0, pattern: 0, cx: 0.5, cy: 0.5);

  /// 두 통계의 차이. 흰 면·무늬 비율 차에, 흰 덩어리가 있을 때만 무게중심 이동을 더한다(빈 상자끼리는 중심이 의미 없음).
  double diff(CornerStats o) {
    final w = math.min(white, o.white);
    return (white - o.white).abs() + (pattern - o.pattern).abs() + ((cx - o.cx).abs() + (cy - o.cy).abs()) * w;
  }

  /// 흰 면이 패 몇 장 분량인지([tileFrac] 은 패 한 장의 상자 비율).
  double tiles(double tileFrac) => tileFrac <= 0 ? 0 : white / tileFrac;

  Map<String, dynamic> toJson() => {'white': white, 'pattern': pattern, 'cx': cx, 'cy': cy};

  @override
  String toString() => 'CornerStats(white ${(white * 100).toStringAsFixed(1)}%, pattern ${(pattern * 100).toStringAsFixed(2)}%, '
      'c ${cx.toStringAsFixed(2)},${cy.toStringAsFixed(2)})';
}

/// [box] 안 통계. [white] 는 [whiteMask] 로 만든 전체 마스크.
CornerStats cornerStatsIn(img.Image im, Uint8List white, NormBox box) {
  final r = box.toPixels(im.width, im.height);
  final n = r.width * r.height;
  if (n <= 0) return CornerStats.empty;
  var count = 0;
  var sx = 0, sy = 0;
  for (var y = r.y; y < r.y + r.height; y++) {
    final row = y * im.width;
    for (var x = r.x; x < r.x + r.width; x++) {
      if (white[row + x] == 1) {
        count++;
        sx += x - r.x;
        sy += y - r.y;
      }
    }
  }
  final pattern = tilePatternArea(im, white, box) / n;
  if (count == 0) return CornerStats(white: 0, pattern: pattern, cx: 0.5, cy: 0.5);
  return CornerStats(
    white: count / n,
    pattern: pattern,
    cx: sx / count / r.width,
    cy: sy / count / r.height,
  );
}

/// 네 자리 모서리 칸의 통계.
Map<Side, CornerStats> cornerStats(img.Image im, Uint8List white, GridZones grid) =>
    {for (final s in Side.values) s: cornerStatsIn(im, white, grid.cornerCell(s))};

/// 미리보기 JPEG → 네 자리 통계. `compute()` 에 그대로 넘길 수 있다.
Map<Side, CornerStats> analyzeCorners((Uint8List, GridZones) args) {
  final (jpeg, grid) = args;
  final im = decodeSmall(jpeg);
  return cornerStats(im, whiteMask(im), grid);
}

/// 패 한 장의 앞면이 [side] 모서리 칸에서 차지하는 비율 어림.
/// 기준은 앱의 촬영 가이드(긴 변 4000 사진에서 앞면 폭 100px): 사진 가로의 [tileW], 세로의 [tileH](4:3 사진, 패 비율 3:4).
/// 거치 높이가 가이드와 다르면 실제 장수와 비례해 어긋나지만, 추적은 "변화가 패 1장 이상인가" 만 보므로 2배 안이면 된다.
double tileFracOf(GridZones grid, Side side, {double tileW = 0.025, double tileH = 0.044}) {
  final b = grid.cornerCell(side);
  final w = b.width / 1000, h = b.height / 1000;
  if (w <= 0 || h <= 0) return 0;
  return (tileW * tileH) / (w * h);
}

Map<Side, double> tileFracsOf(GridZones grid) => {for (final s in Side.values) s: tileFracOf(grid, s)};
