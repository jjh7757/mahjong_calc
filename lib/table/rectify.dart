/// 기운 탁자 펴기(원근 보정). 순수 Dart.
///
/// 카메라가 탁자를 비스듬히 보면(10/24 매장 삼각대: 탁자 약 25° 기움) 축에 평행한 격자 선 4개로 자리를 나눌 수 없다
/// (기운 손패가 두 칸에 걸림). 초록 펠트의 네 모서리를 찾아 펠트가 정사각형이 되게 사진을 펴고, 펠트 밖 [margin] 만큼
/// (흰 테두리 위 울기·손패) 더 넣는다. 편 사진에서는 탁자 모양이 늘 같아 격자 하나([standardGrid])로 나눌 수 있다.
///
/// 개발은 갤러리 B·C·D 와 그것을 합성으로 기울인 사진으로만 한다(매장 사진 15장은 테스트 세트, 2026-10-27 사용자 결정).
library;

import 'dart:math' as math;

import 'package:image/image.dart' as img;

import 'fixed_layout.dart' show FeltMask;
import 'grid_zones.dart';
import 'table_layout.dart' show NormBox;

/// 펠트 네 모서리(사진 정규화 좌표 0~1). 위·오른쪽·아래·왼쪽은 사진 기준이다(펴면 그대로 위·오른쪽…).
class FeltQuad {
  final math.Point<double> topLeft, topRight, bottomRight, bottomLeft;
  const FeltQuad(this.topLeft, this.topRight, this.bottomRight, this.bottomLeft);

  List<math.Point<double>> get corners => [topLeft, topRight, bottomRight, bottomLeft];

  /// 펠트가 사진에서 차지하는 넓이 비율(신발끈 공식).
  double get area {
    final c = corners;
    var s = 0.0;
    for (var i = 0; i < 4; i++) {
      final a = c[i], b = c[(i + 1) % 4];
      s += a.x * b.y - b.x * a.y;
    }
    return s.abs() / 2;
  }

  /// 가운데에서 모서리를 [scale] 배로 밀어낸 사각형(펠트 밖 테두리까지 넣으려고).
  FeltQuad grown(double scale) {
    final cx = corners.map((p) => p.x).reduce((a, b) => a + b) / 4;
    final cy = corners.map((p) => p.y).reduce((a, b) => a + b) / 4;
    math.Point<double> g(math.Point<double> p) => math.Point(cx + (p.x - cx) * scale, cy + (p.y - cy) * scale);
    return FeltQuad(g(topLeft), g(topRight), g(bottomRight), g(bottomLeft));
  }

  Map<String, Object> toJson() => {
        for (final (k, p) in [('tl', topLeft), ('tr', topRight), ('br', bottomRight), ('bl', bottomLeft)])
          k: [double.parse(p.x.toStringAsFixed(4)), double.parse(p.y.toStringAsFixed(4))],
      };
}

/// 펠트(초록 가장 큰 덩어리, 구멍 메움)의 네 모서리. 대각선 방향 끝점: x+y 최소 = 왼쪽 위, x−y 최대 = 오른쪽 위 …
/// 탁자가 45° 미만으로 기울었을 때 맞다. 펠트가 사진의 [minArea] 미만이면 null(펠트를 못 찾음 → 펴지 않음).
FeltQuad? findFeltQuad(img.Image small, {double minArea = 0.15}) {
  final m = FeltMask.of(small);
  double? tlS, trS, brS, blS;
  math.Point<double>? tl, tr, br, bl;
  for (var y = 0; y < m.height; y++) {
    for (var x = 0; x < m.width; x++) {
      if (m.bits[y * m.width + x] != 1) continue;
      // 픽셀 가운데, 가로세로 비를 사진과 같게(정규화 좌표로 두면 4:3 사진에서 대각선이 기운다).
      final nx = (x + 0.5) / m.width, ny = (y + 0.5) / m.height;
      final ax = nx * small.width, ay = ny * small.height;
      final p = math.Point(nx, ny);
      if (tlS == null || ax + ay < tlS) (tlS, tl) = (ax + ay, p);
      if (brS == null || ax + ay > brS) (brS, br) = (ax + ay, p);
      if (trS == null || ax - ay > trS) (trS, tr) = (ax - ay, p);
      if (blS == null || ax - ay < blS) (blS, bl) = (ax - ay, p);
    }
  }
  if (tl == null) return null;
  final q = FeltQuad(tl, tr!, br!, bl!);
  return q.area < minArea ? null : q;
}

/// 작탁 기울기(도, 사진에서 시계 방향 +): 펠트 네 변이 가로·세로에서 벗어난 각도의 평균. 원근으로 위·아래 변(왼쪽·오른쪽 변)의
/// 기울기가 서로 다르게 보여도 네 변을 평균하면 상쇄된다. [aspect] = 사진 가로/세로(모서리는 정규화 좌표라 픽셀처럼 되돌린다).
/// 사용자 제안(2026-10-29): 수직 격자를 그대로 쓰지 말고 작탁 기울기를 재서 사진을 돌려 탁자를 반듯하게 세운 뒤 격자로 나눈다
/// (원근까지 펴는 [rectify] 는 반듯한 B·C·D 에서 점수 정답 23 → 12 로 나빠져 기본 끔).
double tableTilt(FeltQuad q, {double aspect = 4 / 3}) {
  double a(math.Point<double> p, math.Point<double> r) => math.atan2(r.y - p.y, (r.x - p.x) * aspect);
  double v(math.Point<double> p, math.Point<double> r) => math.atan2(-(r.x - p.x) * aspect, r.y - p.y);
  final edges = [a(q.topLeft, q.topRight), a(q.bottomLeft, q.bottomRight), v(q.topLeft, q.bottomLeft), v(q.topRight, q.bottomRight)];
  return edges.reduce((x, y) => x + y) / 4 * 180 / math.pi;
}

/// 펠트를 정사각형으로 편 사진(한 변 [size]px). 펠트 둘레에 한 변의 [margin] 만큼 테두리를 더 넣는다
/// (편 사진에서 펠트는 [feltSpan] 안). 사진 밖은 검게.
img.Image rectify(img.Image src, FeltQuad quad, {double margin = rectifyMargin, int size = 2800}) {
  final q = quad.grown(1 + 2 * margin);
  img.Point px(math.Point<double> p) => img.Point(p.x * src.width, p.y * src.height);
  return img.copyRectify(
    src,
    topLeft: px(q.topLeft),
    topRight: px(q.topRight),
    bottomLeft: px(q.bottomLeft),
    bottomRight: px(q.bottomRight),
    interpolation: img.Interpolation.linear,
    toImage: img.Image(width: size, height: size),
  );
}

/// 펠트 둘레 테두리(펠트 한 변 대비).
const double rectifyMargin = 0.12;

/// 작탁 바깥 끝(펠트 + 둘레 흰 테두리)을 감싸는 축 정렬 상자(0~1000). 펴지 않고 구역 크롭만 이 상자로 자를 때 쓴다
/// (사용자 제안 2026-10-28 "처음 자를 때 작탁만"). [margin] 은 펠트 한 변 대비 테두리 몫.
NormBox tableBoxOf(FeltQuad quad, {double margin = tableClipMargin}) {
  final c = quad.grown(1 + 2 * margin).corners;
  int n(double v) => (v * 1000).round().clamp(0, 1000);
  return NormBox(
    n(c.map((p) => p.y).reduce(math.min)),
    n(c.map((p) => p.x).reduce(math.min)),
    n(c.map((p) => p.y).reduce(math.max)),
    n(c.map((p) => p.x).reduce(math.max)),
  );
}

/// 작탁 흰 테두리 몫(펠트 한 변 대비). B·C·D 갤러리 사진에서 테두리 바깥 끝을 보고 정함.
const double tableClipMargin = 0.07;

/// 편 사진에서 펠트가 차지하는 구간(0~1000).
(int, int) get feltSpan {
  final a = (rectifyMargin / (1 + 2 * rectifyMargin) * 1000).round();
  return (a, 1000 - a);
}

/// 편 사진의 표준 격자. 갤러리 B·C·D(원본·합성 기울기)를 펴서 정했다(개발 세트): 편 사진에서 손패 줄은 가장자리에서
/// 0.11~0.15(펠트 안쪽 끝 0.097), 강·가운데 기기는 0.25~0.75 안이라 그 사이 0.20·0.80 에 선을 둔다.
const GridZones standardGrid = GridZones(x1: 200, x2: 800, y1: 200, y2: 800);
