/// 가운데 기기 홈의 리치봉을 픽셀로 본다 — 색과 무관하게(파랑·노랑·빨강 봉), 서버 호출 없이. 순수 Dart.
///
/// 매장 리치봉은 파란 막대지만 모자라면 노랑·빨강 봉으로 대신 꽂는다(2026-11-10 사용자). 그래서 색상이 아니라
/// "진한 색(채도 높음)의 가늘고 긴 덩어리가 기기 가장자리에 홈 방향으로 누워 있나" 로 판정한다.
/// 빨간 버튼·파란 마름모 버튼·LED·주사위 점은 짧아서 빠진다. 펠트 초록은 뺀다(초록 봉은 못 잡음),
/// 흰 봉은 채도가 없어 못 잡는다(매장은 안 씀).
/// 11-07 매장 크롭 292장(Python 원형 `experiments/tracking/stick_color_free.py`): 봉 있음 105/109, 헛 잡음 0/1059,
/// 노랑·빨강 합성 같음(metrics 표 11-1). 놓친 것은 손·팔 가림과 크롭 어긋남 — 추적기는 연속 프레임으로 확정한다.
library;

import 'package:image/image.dart' as img;

import 'table_layout.dart';

class StickSlotConfig {
  final double satMin;
  final double valMin;

  /// 덩어리 길이 ≥ 구역 변의 이 비율.
  final double lenMin;

  /// 길이/두께 ≥ 이 값(실제 봉 4~6, 문턱 3~5 사이 평탄).
  final double ratioMin;

  /// 길이/두께 ≤ 이 값. 실제 봉은 크롭 4.2~7.3·추적 프레임 4.3~5.6, 오전 연출 프레임의 헛 잡음(구역 가장자리의
  /// 가는 색 줄, 두께 1~6px)은 11~17(2026-11-10, 11-07 하루 프레임).
  final double ratioMax;

  /// 덩어리 중심이 구역 가장자리 이 비율 안이어야 그 자리 홈.
  final double edge;

  /// 구역을 이 긴 변 화소로 줄여(블록 평균) 본다. 크롭 292장: 120px 105/109 · 160px 104 · 240px 100 · 640px 105, 헛 잡음 모두 0.
  final int sampleLong;

  const StickSlotConfig({
    this.satMin = 0.45,
    this.valMin = 0.25,
    this.lenMin = 0.25,
    this.ratioMin = 4.0,
    this.ratioMax = 9.0,
    this.edge = 0.30,
    this.sampleLong = 120,
  });
}

/// 진한 색 화소인가(펠트 초록 제외). r,g,b 0~255.
bool isStickColor(int r, int g, int b, {double satMin = 0.45, double valMin = 0.25}) {
  final mx = r > g ? (r > b ? r : b) : (g > b ? g : b);
  final mn = r < g ? (r < b ? r : b) : (g < b ? g : b);
  if (mx < valMin * 255) return false;
  final d = mx - mn;
  if (d < satMin * mx || d == 0) return false;
  double h;
  if (mx == r) {
    h = ((g - b) / d) % 6;
  } else if (mx == g) {
    h = (b - r) / d + 2;
  } else {
    h = (r - g) / d + 4;
  }
  h *= 60;
  if (h < 0) h += 360;
  return !(h >= 70 && h <= 170);
}

/// [zone](이미지 기준 0~1000, 보통 [GridZones.sticksZone]) 안에서 자리별 봉이 보이는지.
/// [trace] 를 주면 긴 덩어리(구역 변의 10% 넘는 것)를 적는다(점검용).
Map<Side, bool> stickSlotsIn(img.Image im, NormBox zone, {StickSlotConfig config = const StickSlotConfig(), List<String>? trace}) {
  final x0 = (zone.xmin / 1000 * im.width).floor().clamp(0, im.width - 1);
  final x1 = (zone.xmax / 1000 * im.width).ceil().clamp(x0 + 1, im.width);
  final y0 = (zone.ymin / 1000 * im.height).floor().clamp(0, im.height - 1);
  final y1 = (zone.ymax / 1000 * im.height).ceil().clamp(y0 + 1, im.height);
  final zw = x1 - x0, zh = y1 - y0;
  final long = zw > zh ? zw : zh;
  final scale = long > config.sampleLong ? config.sampleLong / long : 1.0;
  final w = (zw * scale).round().clamp(1, zw), h = (zh * scale).round().clamp(1, zh);
  var mask = List<bool>.filled(w * h, false);
  // 줄일 때는 블록 평균(가장 가까운 화소 하나만 집으면 얇은 봉이 끊김).
  for (var y = 0; y < h; y++) {
    final ya = y0 + (y * zh) ~/ h, yb = y0 + ((y + 1) * zh) ~/ h;
    for (var x = 0; x < w; x++) {
      final xa = x0 + (x * zw) ~/ w, xb = x0 + ((x + 1) * zw) ~/ w;
      var r = 0, g = 0, b = 0, n = 0;
      for (var yy = ya; yy < (yb > ya ? yb : ya + 1); yy++) {
        for (var xx = xa; xx < (xb > xa ? xb : xa + 1); xx++) {
          final p = im.getPixel(xx, yy);
          r += p.r.toInt();
          g += p.g.toInt();
          b += p.b.toInt();
          n++;
        }
      }
      mask[y * w + x] = isStickColor(r ~/ n, g ~/ n, b ~/ n, satMin: config.satMin, valMin: config.valMin);
    }
  }
  // 열기(점 잡음 빼기)는 구역이 클 때만 — 추적 프레임(1020px)에선 구역이 160px 안팎이라 봉 두께가 4~6px 이고
  // 3×3 침식이 봉을 끊는다(크롭 292장: 160px 에서 열기를 하면 봉 있음 71/109).
  if ((w > h ? w : h) >= 320) mask = _dilate(_erode(mask, w, h), w, h);
  mask = _erode(_dilate(mask, w, h), w, h); // 닫기: 봉 가운데 무늬(점·화살표)로 끊긴 것 잇기
  return _sides(mask, w, h, config, trace);
}

Map<Side, bool> _sides(List<bool> mask, int w, int h, StickSlotConfig c, [List<String>? trace]) {
  final found = {for (final s in Side.values) s: false};
  final seen = List<bool>.filled(w * h, false);
  final stack = <int>[];
  for (var i = 0; i < mask.length; i++) {
    if (!mask[i] || seen[i]) continue;
    var minX = w, minY = h, maxX = -1, maxY = -1;
    seen[i] = true;
    stack.add(i);
    while (stack.isNotEmpty) {
      final k = stack.removeLast();
      final x = k % w, y = k ~/ w;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      for (final (dx, dy) in const [(1, 0), (-1, 0), (0, 1), (0, -1)]) {
        final nx = x + dx, ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
        final n = ny * w + nx;
        if (mask[n] && !seen[n]) {
          seen[n] = true;
          stack.add(n);
        }
      }
    }
    final bw = maxX - minX + 1, bh = maxY - minY + 1;
    final cx = (minX + maxX + 1) / 2 / w, cy = (minY + maxY + 1) / 2 / h;
    if (trace != null && (bw > 0.1 * w || bh > 0.1 * h)) {
      trace.add('${bw}x$bh 중심 ${cx.toStringAsFixed(2)},${cy.toStringAsFixed(2)} (구역 ${w}x$h)');
    }
    if (bw >= bh) {
      if (bw < c.lenMin * w || bw / bh < c.ratioMin || bw / bh > c.ratioMax) continue;
      if (cy < c.edge) found[Side.top] = true;
      if (cy > 1 - c.edge) found[Side.bottom] = true;
    } else {
      if (bh < c.lenMin * h || bh / bw < c.ratioMin || bh / bw > c.ratioMax) continue;
      if (cx < c.edge) found[Side.left] = true;
      if (cx > 1 - c.edge) found[Side.right] = true;
    }
  }
  return found;
}

List<bool> _erode(List<bool> m, int w, int h) => _morph(m, w, h, erode: true);
List<bool> _dilate(List<bool> m, int w, int h) => _morph(m, w, h, erode: false);

/// 3×3 침식/팽창. 테두리 밖은 침식이면 참, 팽창이면 거짓으로 친다(scipy binary_opening/closing 과 같은 효과).
List<bool> _morph(List<bool> m, int w, int h, {required bool erode}) {
  final out = List<bool>.filled(w * h, false);
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      var v = erode;
      for (var dy = -1; dy <= 1 && v == erode; dy++) {
        for (var dx = -1; dx <= 1; dx++) {
          final nx = x + dx, ny = y + dy;
          final on = (nx < 0 || ny < 0 || nx >= w || ny >= h) ? erode : m[ny * w + nx];
          if (erode && !on) {
            v = false;
            break;
          }
          if (!erode && on) {
            v = true;
            break;
          }
        }
      }
      out[y * w + x] = v;
    }
  }
  return out;
}
