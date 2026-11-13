/// 초록 펠트 네 모서리로 격자를 자동 계산한다. 순수 Dart, API 호출 없음.
///
/// 펠트 윤곽의 곧은 구간에 변마다 직선을 맞춰(손·모서리 패가 가려도 나머지 구간으로) 모서리를 구하고, 펠트를 편 좌표에서
/// 구역을 나눈다. 패 상자를 편 좌표로 옮겨 보니 강은 가운데에서 0.24 까지, 손패·울기는 0.32 바깥이고 사이에 패가 거의 없었다
/// (experiments/zone_points, metrics 표 1-40: 사람이 맞춘 격자와 같은 30/34, 틀린 자동 반영 0). 모델 학습은 펠트 모서리를
/// 못 배워 쓰지 않는다(표 1-39). 안 본 사진에서 곧은 패 줄을 변으로 잡고, 어두운 사진에서 틀린 채 통과해(표 1-42) 펠트 색을
/// 사진에서 재고 변 바깥·안쪽을 검사한다. 이 탁자 기종에서만 재 본 값이라 믿지 못하면 기존 자동 맞추기로 넘어간다.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'fixed_layout.dart' show decodeSmall;
import 'grid_zones.dart';
import 'rectify.dart' show FeltQuad;
import 'table_layout.dart' show NormBox;

/// 재는 사진 긴 변. 카메라 헤드 미리보기와 같은 크기.
const int feltLongSide = 1020;

/// 가운데 칸 = 편 좌표에서 가운데 거리 이 값 안. 손패 크롭이 안쪽으로 [seatReadGrow] 넓어져도 강에 닿지 않는 값.
const double feltRiverReach = 0.30;

/// 기기(리치봉 상자)의 편 좌표 폭·높이. 펠트 대비 크기가 이 탁자 기종에서 일정했다(반사광에 흔들리는 기기 색 대신 쓴다).
const double feltDeviceW = 0.197, feltDeviceH = 0.194;

/// 리치봉 상자 여유(0~1000).
const int feltSticksPad = 10;

/// 변 하나를 곧은 윤곽이 덮어야 하는 비율. 밑돌면 그 변이 사진 밖이거나 다 가려진 것이라 모서리를 믿지 못한다.
const double feltMinSpan = 0.25;

/// 편 좌표 가운데 기기 자리에서 어두운 기기 면이어야 하는 비율. 펠트로 잘못 잡은 사각형을 거른다.
const double feltMinDevice = 0.25;

/// 변 바깥 띠(펠트 폭의 1.5~10%)의 펠트 색 비율 상한. 넘으면 그 선은 펠트 끝이 아니다(곧은 패 줄을 변으로 잡은 경우).
/// 개발 자료에서 맞는 판독은 99% 가 0.02 이하, 틀린 판독은 90% 가 0.08 이상이다.
const double feltMaxOutside = 0.05;

/// 변 안쪽 띠(펠트 폭의 0.5~4%)의 펠트 색 비율 하한. 밑돌면 선이 펠트 밖에 있다(패·손이 덮는 몫은 남겨 둔다).
const double feltMinInside = 0.30;

/// 기기 사각형 바로 바깥 띠에서 기기 면 비율의 상한(네 변 중 가장 높은 값). 넘으면 사각형이 기기에서 밀린 것이다.
/// 위 변이 사진 밖이면 바깥 띠로 검사할 수 없어 이것으로 잡는다. 개발 자료에서 맞는 판독은 99% 가 0.69 이하(팔이 기기를 덮은 경우 포함),
/// 위 변을 잘못 잡은 프레임은 0.80 이상이다.
const double feltMaxDeviceEdge = 0.75;

/// 모서리가 사진 밖으로 나가도 되는 거리(사진 비율). 넘으면 보이지 않는 부분을 너무 멀리 짐작한 것.
const double feltMaxOffImage = 0.20;

/// 마주 보는 변 길이 비(사진 픽셀)의 상한. 원근이 강한 갤러리 사진도 약 1.6 이다.
const double feltMaxSideRatio = 2.2;

/// 편 좌표 → 사진 비율 좌표 변환(왼위부터 시계 방향 네 점이 단위 정사각형의 네 꼭짓점).
class FeltPlane {
  final double _a, _b, _c, _d, _e, _f, _g, _h;
  const FeltPlane._(this._a, this._b, this._c, this._d, this._e, this._f, this._g, this._h);

  /// 사각형이 찌그러져 풀 수 없으면 null.
  static FeltPlane? of(FeltQuad q) {
    final p = q.corners;
    final dx1 = p[1].x - p[2].x, dx2 = p[3].x - p[2].x, sx = p[0].x - p[1].x + p[2].x - p[3].x;
    final dy1 = p[1].y - p[2].y, dy2 = p[3].y - p[2].y, sy = p[0].y - p[1].y + p[2].y - p[3].y;
    final den = dx1 * dy2 - dx2 * dy1;
    if (den.abs() < 1e-12) return null;
    final g = (sx * dy2 - dx2 * sy) / den, h = (dx1 * sy - sx * dy1) / den;
    return FeltPlane._(p[1].x - p[0].x + g * p[1].x, p[3].x - p[0].x + h * p[3].x, p[0].x, p[1].y - p[0].y + g * p[1].y,
        p[3].y - p[0].y + h * p[3].y, p[0].y, g, h);
  }

  math.Point<double> at(double u, double v) {
    final w = _g * u + _h * v + 1;
    return math.Point((_a * u + _b * v + _c) / w, (_d * u + _e * v + _f) / w);
  }
}

/// 펠트 판독 한 번의 결과. [quad] 는 검사와 상관없이 구한 값, [ok] 가 믿어도 되는지.
class FeltReading {
  final FeltQuad quad;

  /// 네 변 중 곧은 윤곽이 덮은 비율이 가장 낮은 값.
  final double minSpan;

  /// 기기 자리에서 어두운 기기 면인 비율.
  final double deviceShare;

  /// 네 변 바깥 띠의 펠트 색 비율 중 가장 높은 값. 띠가 대부분 사진 밖인 변은 뺀다.
  final double outsideMax;

  /// 네 변 안쪽 띠의 펠트 색 비율 중 가장 낮은 값. 띠가 대부분 사진 밖인 변은 뺀다.
  final double insideMin;

  /// 기기 사각형 바로 바깥 네 띠의 기기 면 비율 중 가장 높은 값.
  final double deviceEdge;

  /// 모서리가 사진 밖으로 나간 가장 먼 거리(사진 비율).
  final double offImage;

  /// 마주 보는 변 길이 비 중 큰 값(1 이상).
  final double sideRatio;

  const FeltReading(this.quad, this.minSpan, this.deviceShare, this.deviceEdge, this.outsideMax, this.insideMin, this.offImage, this.sideRatio);

  bool get ok =>
      minSpan >= feltMinSpan &&
      deviceShare >= feltMinDevice &&
      deviceEdge <= feltMaxDeviceEdge &&
      outsideMax <= feltMaxOutside &&
      insideMin >= feltMinInside &&
      offImage <= feltMaxOffImage &&
      sideRatio <= feltMaxSideRatio;
}

/// 선 ax + by = c.
typedef _Line = ({double a, double b, double c});

/// 펠트 색 판정에 쓰는 HSV(H 0~180, S·V 0~255).
(double, double, double) _hsv(num r, num g, num b) {
  final v = math.max(r, math.max(g, b)).toDouble();
  final mn = math.min(r, math.min(g, b)).toDouble();
  final d = v - mn;
  if (d == 0) return (0, 0, v);
  final s = 255 * d / v;
  double h;
  if (v == r) {
    h = 60 * (g - b) / d;
  } else if (v == g) {
    h = 120 + 60 * (b - r) / d;
  } else {
    h = 240 + 60 * (r - g) / d;
  }
  if (h < 0) h += 360;
  return (h / 2, s, v);
}

/// 그 사진의 펠트 색. 조명·채도가 달라도 잡히게 고정 색 범위 대신 사진 가운데에서 가장 많은 색상을 잡는다.
class _FeltColor {
  final double hue, minS, minV, midV;
  const _FeltColor(this.hue, this.minS, this.minV, this.midV);

  bool has(num r, num g, num b) {
    final (h, s, v) = _hsv(r, g, b);
    final d = (h - hue).abs();
    return math.min(d, 180 - d) < _feltHueWindow && s > minS && v > minV;
  }

  /// 기기 면: 펠트가 아니고 펠트보다 눈에 띄게 밝지 않다(흰 패·반사광 제외).
  bool isDevice(num r, num g, num b) {
    final (_, _, v) = _hsv(r, g, b);
    return v < midV * 1.4 && !has(r, g, b);
  }
}

const double _feltHueWindow = 18;

/// 사진 가운데 70% 에서 색이 있는 픽셀의 가장 많은 색상(폭 ±[_feltHueWindow]) → 펠트 색. 그 색이 가운데 칸의 16%(사진의 약 8%)가 안 되면 null.
_FeltColor? _measureFelt(img.Image im) {
  const bins = 45; // 4 단위
  final hist = List<int>.filled(bins, 0);
  final w = im.width, h = im.height;
  final samples = <(double, double, double)>[];
  var seen = 0;
  for (var y = (h * 0.15).floor(); y < h * 0.85; y += 2) {
    for (var x = (w * 0.15).floor(); x < w * 0.85; x += 2) {
      final p = im.getPixel(x, y);
      final c = _hsv(p.r, p.g, p.b);
      seen++;
      if (c.$2 > 35 && c.$3 > 20) {
        samples.add(c);
        hist[(c.$1 / 4).floor() % bins]++;
      }
    }
  }
  // 봉우리는 좁게 찾는다. 판정 폭만큼 넓게 합치면 패 뒷면·기기 색까지 더해져 가운데가 펠트 색에서 밀린다(색상 76 을 98 로 잡았다).
  var best = 0, bestN = -1;
  for (var i = 0; i < bins; i++) {
    final n = hist[(i - 1) % bins] + hist[i] + hist[(i + 1) % bins];
    if (n > bestN) {
      bestN = n;
      best = i;
    }
  }
  final weight = hist[(best - 1) % bins] + hist[best] + hist[(best + 1) % bins];
  final hue = weight == 0 ? 0.0 : ((best * 4 + 2.0) + 4.0 * (hist[(best + 1) % bins] - hist[(best - 1) % bins]) / weight) % 180;
  final ss = <double>[], vs = <double>[];
  for (final (hu, s, v) in samples) {
    final d = (hu - hue).abs();
    if (math.min(d, 180 - d) < _feltHueWindow) {
      ss.add(s);
      vs.add(v);
    }
  }
  if (ss.length < 0.16 * seen) return null;
  ss.sort();
  vs.sort();
  final midS = ss[ss.length ~/ 2], midV = vs[vs.length ~/ 2];
  return _FeltColor(hue, math.max(25, 0.45 * midS), math.max(15, 0.42 * midV), midV);
}

/// 3×3 열기(침식 뒤 팽창). 패의 초록 글씨·잡티가 펠트와 이어지지 않게.
Uint8List _open3(Uint8List m, int w, int h) {
  Uint8List pass(Uint8List src, bool erode) {
    final out = Uint8List(w * h);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var hit = erode ? 1 : 0;
        for (var dy = -1; dy <= 1 && hit == (erode ? 1 : 0); dy++) {
          for (var dx = -1; dx <= 1; dx++) {
            final nx = x + dx, ny = y + dy;
            final on = nx >= 0 && nx < w && ny >= 0 && ny < h && src[ny * w + nx] == 1;
            if (erode ? !on : on) {
              hit = erode ? 0 : 1;
              break;
            }
          }
        }
        out[y * w + x] = hit;
      }
    }
    return out;
  }

  return pass(pass(m, true), false);
}

/// 가장 큰 덩어리(8방향)와 그 넓이.
(Uint8List, int) _largest(Uint8List m, int w, int h) {
  final label = Int32List(w * h);
  final stack = <int>[];
  var best = 0, bestArea = 0, next = 0;
  for (var i = 0; i < m.length; i++) {
    if (m[i] != 1 || label[i] != 0) continue;
    next++;
    var area = 0;
    label[i] = next;
    stack.add(i);
    while (stack.isNotEmpty) {
      final c = stack.removeLast();
      area++;
      final x = c % w, y = c ~/ w;
      for (var dy = -1; dy <= 1; dy++) {
        for (var dx = -1; dx <= 1; dx++) {
          final nx = x + dx, ny = y + dy;
          if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
          final n = ny * w + nx;
          if (m[n] == 1 && label[n] == 0) {
            label[n] = next;
            stack.add(n);
          }
        }
      }
    }
    if (area > bestArea) {
      bestArea = area;
      best = next;
    }
  }
  final out = Uint8List(w * h);
  for (var i = 0; i < out.length; i++) {
    if (label[i] == best && best != 0) out[i] = 1;
  }
  return (out, bestArea);
}

/// 덩어리의 바깥 윤곽 점. 안쪽 구멍(패) 둘레는 빼고, 사진 끝에 닿은 윤곽은 펠트 변이 아니라 뺀다.
List<math.Point<double>> _outline(Uint8List m, int w, int h) {
  final outside = Uint8List(w * h);
  final stack = <int>[];
  void seed(int i) {
    if (m[i] == 0 && outside[i] == 0) {
      outside[i] = 1;
      stack.add(i);
    }
  }

  for (var x = 0; x < w; x++) {
    seed(x);
    seed((h - 1) * w + x);
  }
  for (var y = 0; y < h; y++) {
    seed(y * w);
    seed(y * w + w - 1);
  }
  while (stack.isNotEmpty) {
    final c = stack.removeLast();
    final x = c % w, y = c ~/ w;
    if (x > 0) seed(c - 1);
    if (x < w - 1) seed(c + 1);
    if (y > 0) seed(c - w);
    if (y < h - 1) seed(c + w);
  }
  final out = <math.Point<double>>[];
  for (var y = 2; y < h - 2; y++) {
    for (var x = 2; x < w - 2; x++) {
      final i = y * w + x;
      if (m[i] == 1 && (outside[i - 1] == 1 || outside[i + 1] == 1 || outside[i - w] == 1 || outside[i + w] == 1)) {
        out.add(math.Point(x.toDouble(), y.toDouble()));
      }
    }
  }
  return out;
}

/// 점들에 맞는 직선(직교 최소제곱).
_Line? _fitLine(List<math.Point<double>> pts) {
  if (pts.length < 2) return null;
  var mx = 0.0, my = 0.0;
  for (final p in pts) {
    mx += p.x;
    my += p.y;
  }
  mx /= pts.length;
  my /= pts.length;
  var sxx = 0.0, syy = 0.0, sxy = 0.0;
  for (final p in pts) {
    final dx = p.x - mx, dy = p.y - my;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  }
  final th = 0.5 * math.atan2(2 * sxy, sxx - syy);
  final a = -math.sin(th), b = math.cos(th);
  return (a: a, b: b, c: a * mx + b * my);
}

math.Point<double>? _meet(_Line l, _Line m) {
  final den = l.a * m.b - m.a * l.b;
  if (den.abs() < 1e-6) return null;
  return math.Point((l.c * m.b - m.c * l.b) / den, (l.a * m.c - m.a * l.c) / den);
}

/// 펠트 색 덩어리가 사진을 덮은 정도. 거치 점검(`mount_check.dart`)이 "탁자가 사진 밖으로 잘렸나" 를 볼 때 쓴다 —
/// 변이 사진 밖이면 [readFelt] 는 그 변을 못 믿어 거절만 하고 어느 쪽이 잘렸는지는 말해 주지 않는다.
class FeltCoverage {
  /// 가장 큰 펠트 색 덩어리의 넓이(사진 비율).
  final double area;

  /// 사진의 위·오른쪽·아래·왼쪽 변(끝 3픽셀 띠)에 그 덩어리가 닿은 길이 비율.
  final List<double> touch;

  const FeltCoverage(this.area, this.touch);
}

/// [readFelt] 판독과 [FeltCoverage] 를 한 번의 색 판정으로. 펠트 색을 못 잡으면 둘 다 null.
typedef FeltProbe = ({FeltReading? reading, FeltCoverage? coverage});

/// 긴 변 [feltLongSide] 이하로 줄인 사진에서 펠트를 읽는다. 펠트 색 덩어리가 사진의 8% 미만이면 null.
FeltReading? readFelt(img.Image src) => probeFelt(src).reading;

FeltProbe probeFelt(img.Image src) {
  final long = math.max(src.width, src.height);
  final im = long > feltLongSide
      ? img.copyResize(src,
          width: (src.width * feltLongSide / long).round(),
          height: (src.height * feltLongSide / long).round(),
          interpolation: img.Interpolation.linear)
      : src;
  final w = im.width, h = im.height;
  final color = _measureFelt(im);
  if (color == null) return (reading: null, coverage: null);
  final raw = Uint8List(w * h);
  for (final p in im) {
    if (color.has(p.r, p.g, p.b)) raw[p.y * w + p.x] = 1;
  }
  final (felt, area) = _largest(_open3(raw, w, h), w, h);
  return (reading: _readingOf(im, color, felt, area), coverage: FeltCoverage(area / (w * h), _borderTouch(felt, w, h)));
}

/// 사진 네 변(위·오른쪽·아래·왼쪽)의 끝 3픽셀 띠에 덩어리가 닿은 길이 비율.
List<double> _borderTouch(Uint8List m, int w, int h) {
  const band = 3;
  var top = 0, bottom = 0, left = 0, right = 0;
  for (var x = 0; x < w; x++) {
    var t = false, b = false;
    for (var k = 0; k < band && k < h; k++) {
      t = t || m[k * w + x] == 1;
      b = b || m[(h - 1 - k) * w + x] == 1;
    }
    if (t) top++;
    if (b) bottom++;
  }
  for (var y = 0; y < h; y++) {
    var l = false, r = false;
    for (var k = 0; k < band && k < w; k++) {
      l = l || m[y * w + k] == 1;
      r = r || m[y * w + w - 1 - k] == 1;
    }
    if (l) left++;
    if (r) right++;
  }
  return [top / w, right / h, bottom / w, left / h];
}

FeltReading? _readingOf(img.Image im, _FeltColor color, Uint8List felt, int area) {
  final w = im.width, h = im.height;
  if (area < 0.08 * w * h) return null;
  final pts = _outline(felt, w, h);
  if (pts.length < 100) return null;

  // 대각선 방향 끝점 = 네 모서리 어림. 탁자가 45° 미만으로 기울었을 때 맞다. 손이 모서리를 가려도 변 어림으로는 충분하다.
  var tl = pts.first, tr = pts.first, br = pts.first, bl = pts.first;
  for (final p in pts) {
    if (p.x + p.y < tl.x + tl.y) tl = p;
    if (p.x + p.y > br.x + br.y) br = p;
    if (p.x - p.y > tr.x - tr.y) tr = p;
    if (p.x - p.y < bl.x - bl.y) bl = p;
  }
  final rough = [tl, tr, br, bl];
  final rng = math.Random(0);
  final lines = <_Line>[];
  var minSpan = 1.0;
  for (var i = 0; i < 4; i++) {
    final a = rough[i], b = rough[(i + 1) % 4];
    final dx = b.x - a.x, dy = b.y - a.y;
    final len = math.sqrt(dx * dx + dy * dy);
    if (len < 1) return null;
    final side = <math.Point<double>>[];
    for (final p in pts) {
      final t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / (len * len);
      final dist = ((p.x - a.x) * -dy + (p.y - a.y) * dx).abs() / len;
      if (t > -0.05 && t < 1.05 && dist < 0.08 * len) side.add(p);
    }
    // 손·패가 윤곽을 끌어도 곧은 구간이 가장 많은 점을 모으는 직선을 고른다.
    var bestN = 0;
    double bnx = 0, bny = 0;
    math.Point<double>? bp;
    if (side.length >= 25) {
      for (var k = 0; k < 400; k++) {
        final p = side[rng.nextInt(side.length)], q = side[rng.nextInt(side.length)];
        final vx = q.x - p.x, vy = q.y - p.y;
        final n = math.sqrt(vx * vx + vy * vy);
        // 변 방향에서 약 14° 넘게 벗어난 짝은 버린다.
        if (n < 0.15 * len || (vx * dx + vy * dy).abs() / (n * len) < 0.97) continue;
        final nx = -vy / n, ny = vx / n;
        var c = 0;
        for (final s in side) {
          if (((s.x - p.x) * nx + (s.y - p.y) * ny).abs() < 2) c++;
        }
        if (c > bestN) {
          bestN = c;
          bnx = nx;
          bny = ny;
          bp = p;
        }
      }
    }
    if (bp == null || bestN < 25) {
      minSpan = 0;
      lines.add((a: -dy / len, b: dx / len, c: (-dy * a.x + dx * a.y) / len));
      continue;
    }
    final origin = bp;
    final near = [
      for (final s in side)
        if (((s.x - origin.x) * bnx + (s.y - origin.y) * bny).abs() < 3) s,
    ];
    var lo = double.infinity, hi = -double.infinity;
    for (final s in near) {
      final t = ((s.x - a.x) * dx + (s.y - a.y) * dy) / (len * len);
      lo = math.min(lo, t);
      hi = math.max(hi, t);
    }
    minSpan = math.min(minSpan, hi - lo);
    lines.add(_fitLine(near)!);
  }
  final corners = <math.Point<double>>[];
  for (var i = 0; i < 4; i++) {
    final c = _meet(lines[(i + 3) % 4], lines[i]);
    if (c == null) return null;
    corners.add(math.Point(c.x / w, c.y / h));
  }
  final quad = FeltQuad(corners[0], corners[1], corners[2], corners[3]);
  final plane = FeltPlane.of(quad);
  if (plane == null) return null;

  // 편 좌표 [u0, v0]~[u1, v1] 를 고르게 뽑아 [test] 비율. 대부분 사진 밖이면 null.
  double? share(double u0, double v0, double u1, double v1, bool Function(num, num, num) test) {
    var seen = 0, hit = 0;
    const steps = 40;
    for (var j = 0; j < steps; j++) {
      for (var i = 0; i < steps; i++) {
        final q = plane.at(u0 + (u1 - u0) * i / (steps - 1), v0 + (v1 - v0) * j / (steps - 1));
        final px = (q.x * w).round(), py = (q.y * h).round();
        if (px < 0 || px >= w || py < 0 || py >= h) continue;
        seen++;
        final c = im.getPixel(px, py);
        if (test(c.r, c.g, c.b)) hit++;
      }
    }
    return seen < steps * steps * 0.3 ? null : hit / seen;
  }

  final hw = feltDeviceW / 2, hh = feltDeviceH / 2;
  final device = share(0.5 - hw, 0.5 - hh, 0.5 + hw, 0.5 + hh, color.isDevice) ?? 0;
  const ring0 = 0.008, ring1 = 0.024;
  final ring = [
    share(0.5 - hw, 0.5 - hh - ring1, 0.5 + hw, 0.5 - hh - ring0, color.isDevice),
    share(0.5 + hw + ring0, 0.5 - hh, 0.5 + hw + ring1, 0.5 + hh, color.isDevice),
    share(0.5 - hw, 0.5 + hh + ring0, 0.5 + hw, 0.5 + hh + ring1, color.isDevice),
    share(0.5 - hw - ring1, 0.5 - hh, 0.5 - hw - ring0, 0.5 + hh, color.isDevice),
  ].whereType<double>();
  // 네 변의 바깥 띠(펠트 끝이면 흰 테두리·바닥), 안쪽 띠(펠트 끝이면 펠트).
  const near = 0.015, far = 0.10, inNear = 0.005, inFar = 0.04;
  final outside = [
    share(0.05, -far, 0.95, -near, color.has),
    share(1 + near, 0.05, 1 + far, 0.95, color.has),
    share(0.05, 1 + near, 0.95, 1 + far, color.has),
    share(-far, 0.05, -near, 0.95, color.has),
  ].whereType<double>();
  final inside = [
    share(0.05, inNear, 0.95, inFar, color.has),
    share(1 - inFar, 0.05, 1 - inNear, 0.95, color.has),
    share(0.05, 1 - inFar, 0.95, 1 - inNear, color.has),
    share(inNear, 0.05, inFar, 0.95, color.has),
  ].whereType<double>();
  var off = 0.0;
  for (final c in corners) {
    off = math.max(off, math.max(math.max(-c.x, c.x - 1), math.max(-c.y, c.y - 1)));
  }
  double len(int i) {
    final a = corners[i], b = corners[(i + 1) % 4];
    final dx = (a.x - b.x) * w, dy = (a.y - b.y) * h;
    return math.sqrt(dx * dx + dy * dy);
  }

  double ratio(double a, double b) => a > b ? a / math.max(b, 1e-9) : b / math.max(a, 1e-9);
  return FeltReading(
    quad,
    minSpan,
    device,
    ring.isEmpty ? 0 : ring.reduce(math.max),
    outside.isEmpty ? 0 : outside.reduce(math.max),
    inside.isEmpty ? 0 : inside.reduce(math.min),
    off,
    math.max(ratio(len(0), len(2)), ratio(len(1), len(3))),
  );
}

/// JPEG 한 장 → 믿을 만한 펠트 네 모서리, 못 찾으면 null. `compute()` 에 넘길 수 있다.
FeltQuad? feltQuadOfJpeg(Uint8List jpeg) {
  final r = readFelt(decodeSmall(jpeg));
  return r != null && r.ok ? r.quad : null;
}

/// [FeltQuad.toJson] 되읽기. 모양이 다르면 null.
FeltQuad? feltQuadFromJson(Map<String, dynamic> j) {
  math.Point<double>? at(String k) {
    final v = j[k];
    if (v is! List || v.length != 2) return null;
    return math.Point((v[0] as num).toDouble(), (v[1] as num).toDouble());
  }

  final tl = at('tl'), tr = at('tr'), br = at('br'), bl = at('bl');
  return tl == null || tr == null || br == null || bl == null ? null : FeltQuad(tl, tr, br, bl);
}

/// 펠트 네 모서리 → 격자. 선은 가운데 칸 사각형의 변 평균이라 기운 탁자에서는 근사다. 도라 구역 모양은 [keep] 것.
/// 선이 사진 안에서 제 순서가 아니면 null.
GridZones? gridFromFelt(FeltQuad q, {GridZones? keep}) {
  final plane = FeltPlane.of(q);
  if (plane == null) return null;
  final lo = 0.5 - feltRiverReach, hi = 0.5 + feltRiverReach;
  final a = plane.at(lo, lo), b = plane.at(hi, lo), c = plane.at(hi, hi), d = plane.at(lo, hi);
  final x1 = ((a.x + d.x) * 500).round(), x2 = ((b.x + c.x) * 500).round();
  final y1 = ((a.y + b.y) * 500).round(), y2 = ((c.y + d.y) * 500).round();
  if (!(0 < x1 && x1 < x2 && x2 < 1000 && 0 < y1 && y1 < y2 && y2 < 1000)) return null;
  final hw = feltDeviceW / 2, hh = feltDeviceH / 2;
  final dev = [plane.at(0.5 - hw, 0.5 - hh), plane.at(0.5 + hw, 0.5 - hh), plane.at(0.5 + hw, 0.5 + hh), plane.at(0.5 - hw, 0.5 + hh)];
  int box(double v, int pad) => ((v * 1000).round() + pad).clamp(0, 1000);
  final xs = dev.map((p) => p.x), ys = dev.map((p) => p.y);
  return GridZones(
    x1: x1,
    x2: x2,
    y1: y1,
    y2: y2,
    doraRel: keep?.doraRel ?? doraRelDefault,
    sticks: NormBox(box(ys.reduce(math.min), -feltSticksPad), box(xs.reduce(math.min), -feltSticksPad), box(ys.reduce(math.max), feltSticksPad),
        box(xs.reduce(math.max), feltSticksPad)),
  );
}

double _median(List<double> v) {
  final s = [...v]..sort();
  final n = s.length;
  return n.isOdd ? s[n ~/ 2] : (s[n ~/ 2 - 1] + s[n ~/ 2]) / 2;
}

/// 모서리별 중앙값.
FeltQuad medianFelt(List<FeltQuad> quads) {
  math.Point<double> at(int i) => math.Point(_median([for (final q in quads) q.corners[i].x]), _median([for (final q in quads) q.corners[i].y]));
  return FeltQuad(at(0), at(1), at(2), at(3));
}

/// 같은 탁자 위치로 보는 모서리 차이(사진 비율, 긴 변 1020 에서 약 12px).
const double feltSameNear = 0.012;

/// 네 모서리 중 3개 이상이 [feltSameNear] 안이면 같은 위치(손이 모서리 하나를 끌어도).
bool sameFelt(FeltQuad a, FeltQuad b) {
  var n = 0;
  for (var i = 0; i < 4; i++) {
    final p = a.corners[i], q = b.corners[i];
    if ((p.x - q.x).abs() < feltSameNear && (p.y - q.y).abs() < feltSameNear) n++;
  }
  return n >= 3;
}

/// 프레임의 펠트 위치를 지켜보다 카메라가 움직여 **새 자리에 멈추면** 그 위치를 알려 준다.
/// 움직이는 중인 프레임은 서로 달라 확정되지 않고, 못 읽은 프레임(손·탁자 밖)은 세지 않는다.
class FeltWatch {
  /// 이만큼 잇따라 서로 같고 지금 위치와 다르면 카메라가 옮겨진 것.
  static const int confirm = 3;
  static const int _keep = 8;

  FeltQuad? _basis;
  final List<FeltQuad> _pending = [];

  /// 지금 격자를 잡은 펠트 위치. null 이면 다음 안정된 위치를 격자를 건드리지 않고 기준으로 삼는다(손으로 맞춘 격자).
  FeltQuad? get basis => _basis;

  void reset(FeltQuad? basis) {
    _basis = basis;
    _pending.clear();
  }

  /// 새 프레임의 판독. 카메라가 옮겨져 안정됐으면 새 위치, 아니면 null.
  FeltQuad? add(FeltQuad? q) {
    if (q == null) return null;
    final basis = _basis;
    if (basis != null && sameFelt(q, basis)) {
      _pending.clear();
      return null;
    }
    _pending.add(q);
    if (_pending.length > _keep) _pending.removeAt(0);
    if (_pending.length < confirm) return null;
    final recent = _pending.sublist(_pending.length - confirm);
    final mid = medianFelt(recent);
    if (!recent.every((p) => sameFelt(p, mid))) return null;
    _basis = mid;
    _pending.clear();
    return basis == null ? null : mid;
  }
}
