/// 카메라가 고정일 때 처음 locate 한 구역을 다음 촬영에 다시 쓴다. 순수 Dart(`image` 패키지).
///
/// locate(약 24초, 한 장면 비용의 절반 가까이)를 건너뛰고, 장면마다 바뀌는 것만 사진 픽셀로 정한다(API 호출 없음).
/// - 카메라가 움직였는지: 초록 펠트 모양(위에 놓인 패는 구멍으로 메움)을 기준 사진과 겹쳐 IoU 가 [movedIoU] 아래면
///   움직인 것 → locate 를 다시 한다.
/// - 앞면으로 눕힌 손패: 손패 상자 안 앞면 패 무늬 넓이([faceUpByPattern]) — 뒷면 색과 상관없다.
/// - 도라 표시패: 손패·강·가운데 판 밖에서 사방이 펠트로 둘러싸인 작은 흰 패 덩어리.
/// 울기는 화료자 손패 끝에서 그 사람 오른쪽 모서리까지([meldCorner])를 따로 잘라 울기 판독(/v2/meld)으로 읽는다.
/// 손패 크롭을 넓혀 함께 읽히면 패가 작아지고 도라 표시패가 섞여 손패를 크게 틀렸다(14:09).
///
/// 문턱값은 2026-10-24 매장 사진으로 정했다(experiments/field_20261024/NOTES.md):
/// 펠트 IoU 는 그대로일 때 0.99 이상·움직였을 때 0.76~0.94, 뒷면 비율은 앞면 손패 0.000~0.001·나머지 0.017~0.15
/// (0.03 으로 두었다가 아래 자리 0.029 를 앞면으로 봐 화료자 후보가 둘이 됨, 14:31),
/// 도라 덩어리의 펠트 둘레 비율은 0.98~0.99(다른 후보 0.91 이하).
/// 앞면 판정은 처음엔 연보라 뒷면 비율이었는데(이 매장 자동탁), 파랑·초록·노랑·주황·검정 뒷면 합성 사진에서
/// 뒷면을 하나도 못 찾아 네 자리가 다 앞면이 됐다(2026-10-27, experiments/backcolor) → 뒷면 색을 보지 않는 무늬 넓이로 바꿨다.
/// 뒷면 비율([handColors])은 기록용으로만 남긴다.
library;

import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'table_layout.dart';

/// 펠트 IoU 가 이 아래면 카메라가 움직인 것으로 본다.
const double movedIoU = 0.97;

/// 앞면 손패 자리: 손패 칸의 앞면 패 무늬 넓이가 [faceUpPatternMinArea](긴 변 1024 기준 픽셀) 이상이고
/// 1등의 1/[faceUpPatternRatio] 이상인 자리(더블론이면 둘). 갤러리 B·C·D 손패 칸(울기 모서리 칸 제외)에서 화료자 1570~2870px,
/// 2등과 6.6배 이상 — 원본과 뒷면 5색 합성 36장 모두 같다(자리 구역 전체로 재면 D 는 왼쪽 자리 앞면 울기 때문에 2.0배).
const double faceUpPatternRatio = 2.0;
const int faceUpPatternMinArea = 300;

/// [patterns](자리별 무늬 넓이, [tilePatternArea])로 앞면 손패 자리를 무늬 많은 순으로. [scale] = 축소본 긴 변 / 1024.
List<Side> faceUpByPattern(Map<Side, int> patterns, double scale) {
  final minArea = faceUpPatternMinArea * scale * scale;
  final sorted = patterns.keys.toList()..sort((a, b) => patterns[b]!.compareTo(patterns[a]!));
  if (sorted.isEmpty || patterns[sorted.first]! < minArea) return const [];
  final top = patterns[sorted.first]!;
  return [
    for (final s in sorted)
      if (patterns[s]! >= minArea && patterns[s]! * faceUpPatternRatio >= top) s
  ];
}

/// 도라 덩어리의 둘레 중 펠트 비율 하한.
const double doraRingGreen = 0.95;

/// 펠트 마스크 해상도(locate 축소본을 다시 줄인 것).
const int _feltW = 256, _feltH = 192;

bool _isGreen(num r, num g, num b) => g > r + 20 && g > b;

bool _isBack(num r, num g, num b) {
  final mx = r > g ? (r > b ? r : b) : (g > b ? g : b);
  final mn = r < g ? (r < b ? r : b) : (g < b ? g : b);
  final s = mx == 0 ? 0 : (mx - mn) / mx;
  return b > r && b > g + 10 && r > g - 5 && s > 0.12 && mx > 115;
}

bool _isWhite(num r, num g, num b, {double minValue = 0.70, double maxSat = 0.13}) {
  final mx = r > g ? (r > b ? r : b) : (g > b ? g : b);
  final mn = r < g ? (r < b ? r : b) : (g < b ? g : b);
  final s = mx == 0 ? 0 : (mx - mn) / mx;
  return mx > minValue * 255 && s < maxSat;
}

/// 0/1 격자. 형태학 연산 몇 가지만.
class _Grid {
  final int w, h;
  final Uint8List v;
  _Grid(this.w, this.h) : v = Uint8List(w * h);

  bool at(int x, int y) => x >= 0 && y >= 0 && x < w && y < h && v[y * w + x] == 1;

  _Grid _morph(bool dilate) {
    final out = _Grid(w, h);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var hit = !dilate;
        for (var dy = -1; dy <= 1 && hit != dilate; dy++) {
          for (var dx = -1; dx <= 1; dx++) {
            final on = at(x + dx, y + dy);
            if (dilate && on) {
              hit = true;
              break;
            }
            if (!dilate && !on) {
              hit = false;
              break;
            }
          }
        }
        if (hit) out.v[y * w + x] = 1;
      }
    }
    return out;
  }

  _Grid dilate([int n = 1]) {
    var g = this;
    for (var i = 0; i < n; i++) {
      g = g._morph(true);
    }
    return g;
  }

  _Grid erode([int n = 1]) {
    var g = this;
    for (var i = 0; i < n; i++) {
      g = g._morph(false);
    }
    return g;
  }

  /// 4-이웃 연결 성분. 성분 번호(1부터) 격자와 성분별 픽셀 수.
  (Int32List, List<int>) label() {
    final lab = Int32List(w * h);
    final sizes = <int>[0];
    final stack = <int>[];
    for (var i = 0; i < v.length; i++) {
      if (v[i] == 0 || lab[i] != 0) continue;
      final id = sizes.length;
      var n = 0;
      lab[i] = id;
      stack.add(i);
      while (stack.isNotEmpty) {
        final p = stack.removeLast();
        n++;
        final x = p % w, y = p ~/ w;
        for (final q in [if (x > 0) p - 1, if (x < w - 1) p + 1, if (y > 0) p - w, if (y < h - 1) p + w]) {
          if (v[q] == 1 && lab[q] == 0) {
            lab[q] = id;
            stack.add(q);
          }
        }
      }
      sizes.add(n);
    }
    return (lab, sizes);
  }

  /// 가장 큰 성분만 남기고 그 안의 구멍을 메운다.
  _Grid largestFilled() {
    final (lab, sizes) = label();
    if (sizes.length < 2) return _Grid(w, h);
    var best = 1;
    for (var i = 2; i < sizes.length; i++) {
      if (sizes[i] > sizes[best]) best = i;
    }
    // 테두리에서 성분 밖으로 번져 닿지 않는 곳 = 구멍.
    final outside = Uint8List(w * h);
    final stack = <int>[];
    void seed(int p) {
      if (lab[p] != best && outside[p] == 0) {
        outside[p] = 1;
        stack.add(p);
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
      final p = stack.removeLast();
      final x = p % w, y = p ~/ w;
      if (x > 0) seed(p - 1);
      if (x < w - 1) seed(p + 1);
      if (y > 0) seed(p - w);
      if (y < h - 1) seed(p + w);
    }
    final out = _Grid(w, h);
    for (var i = 0; i < out.v.length; i++) {
      if (outside[i] == 0) out.v[i] = 1;
    }
    return out;
  }
}

/// 초록 펠트 영역(위에 놓인 패 자리는 메움). 카메라 움직임 판정용.
class FeltMask {
  final int width, height;
  final Uint8List bits;
  const FeltMask(this.width, this.height, this.bits);

  factory FeltMask.of(img.Image small) {
    final im = img.copyResize(small, width: _feltW, height: _feltH, interpolation: img.Interpolation.average);
    final g = _Grid(_feltW, _feltH);
    for (final p in im) {
      if (_isGreen(p.r, p.g, p.b)) g.v[p.y * _feltW + p.x] = 1;
    }
    final felt = g.dilate(2).erode(2).largestFilled();
    return FeltMask(_feltW, _feltH, felt.v);
  }

  double iou(FeltMask o) {
    if (o.width != width || o.height != height) return 0;
    var inter = 0, uni = 0;
    for (var i = 0; i < bits.length; i++) {
      final a = bits[i] == 1, b = o.bits[i] == 1;
      if (a && b) inter++;
      if (a || b) uni++;
    }
    return uni == 0 ? 0 : inter / uni;
  }

  bool atNorm(double nx, double ny) {
    final x = (nx * width).floor().clamp(0, width - 1);
    final y = (ny * height).floor().clamp(0, height - 1);
    return bits[y * width + x] == 1;
  }
}

/// 다시 쓸 구역과 그때의 펠트 모양.
class FixedTable {
  final TableLayout layout;
  final FeltMask felt;
  const FixedTable(this.layout, this.felt);

  /// 강 4개·가운데가 다 잡힌 locate 만 기준으로 삼는다.
  static bool usable(TableLayout l) => l.rivers.length == 4 && l.center != null && l.hands.isNotEmpty;

  /// 이번 촬영용 구역: 앞면 자리와 도라 위치만 바꾼다. 울기 상자는 화료자가 정해진 뒤 [meldCorner] 로 만든다.
  TableLayout layoutFor(ShotAnalysis a) => TableLayout(
        hands: [for (final h in layout.hands) HandZone(h.side, h.box, faceUp: a.faceUp.contains(h.side), conf: h.conf)],
        rivers: layout.rivers,
        deadWall: a.doraBox == null ? null : Zone(a.doraBox!),
        center: layout.center,
        notes: '고정 구역(locate 생략)',
        model: 'fixed',
      );
}

/// 한 장의 픽셀 판정 결과.
class ShotAnalysis {
  final double iou;
  final List<Side> faceUp;
  final NormBox? doraBox;

  /// 자리별 (뒷면 비율, 흰 면 비율). 기록·문턱값 조정용.
  final Map<Side, (double, double)> handColors;

  /// 자리별 앞면 패 무늬 넓이([tilePatternArea], 축소본 픽셀). 격자 판독에서만 채운다.
  final Map<Side, int> tilePatterns;
  const ShotAnalysis({
    required this.iou,
    required this.faceUp,
    this.doraBox,
    this.handColors = const {},
    this.tilePatterns = const {},
  });

  bool get moved => iou < movedIoU;

  Map<String, dynamic> toJson() => {
        'felt_iou': double.parse(iou.toStringAsFixed(3)),
        'moved': moved,
        'face_up': [for (final s in faceUp) s.name],
        'dora_box': doraBox?.toList(),
        'hand_colors': {
          for (final e in handColors.entries)
            e.key.name: {
              'back': double.parse(e.value.$1.toStringAsFixed(3)),
              'white': double.parse(e.value.$2.toStringAsFixed(3)),
            },
        },
        if (tilePatterns.isNotEmpty) 'tile_patterns': {for (final e in tilePatterns.entries) e.key.name: e.value},
      };
}

/// 기준 만들기: locate 축소본(JPEG) + 그 locate 결과. `compute()` 에 넘길 수 있다.
FixedTable calibrateFixed((Uint8List, TableLayout) args) {
  final (small, layout) = args;
  return FixedTable(layout, FeltMask.of(decodeSmall(small)));
}

/// 이번 촬영 판정: locate 축소본(JPEG) + 기준. `compute()` 에 넘길 수 있다.
ShotAnalysis analyzeShot((Uint8List, FixedTable) args) {
  final (small, fixed) = args;
  final im = decodeSmall(small);
  final felt = FeltMask.of(im);
  final iou = felt.iou(fixed.felt);
  final white = whiteMask(im);
  final colors = {for (final h in fixed.layout.hands) h.side: handColors(im, h.box)};
  final patterns = {for (final h in fixed.layout.hands) h.side: tilePatternArea(im, white, h.box)};
  final scale = (im.width > im.height ? im.width : im.height) / 1024;
  return ShotAnalysis(
    iou: iou,
    faceUp: faceUpByPattern(patterns, scale),
    doraBox: _findDora(im, felt, fixed.layout),
    handColors: colors,
    tilePatterns: patterns,
  );
}

img.Image decodeSmall(Uint8List jpeg) {
  final im = img.decodeImage(jpeg);
  if (im == null) throw const FormatException('이미지를 디코딩할 수 없습니다');
  return im;
}

/// 상자 안 (뒷면 비율, 흰 면 비율).
(double, double) handColors(img.Image im, NormBox box, {double pad = 0.1}) {
  final r = box.toPixels(im.width, im.height, pad: pad);
  var back = 0, white = 0, n = 0;
  for (var y = r.y; y < r.y + r.height; y++) {
    for (var x = r.x; x < r.x + r.width; x++) {
      final p = im.getPixel(x, y);
      n++;
      if (_isBack(p.r, p.g, p.b)) back++;
      if (_isWhite(p.r, p.g, p.b)) white++;
    }
  }
  return n == 0 ? (1.0, 0.0) : (back / n, white / n);
}

/// [tilePatternArea] 에 쓸 흰 면 마스크(1 = 흰색). 축소본 한 장에 한 번만 만든다.
Uint8List whiteMask(img.Image im) {
  final m = Uint8List(im.width * im.height);
  var i = 0;
  for (var y = 0; y < im.height; y++) {
    for (var x = 0; x < im.width; x++, i++) {
      final p = im.getPixel(x, y);
      if (_isWhite(p.r, p.g, p.b)) m[i] = 1;
    }
  }
  return m;
}

/// 상자 안 앞면 패 무늬 넓이(픽셀): 흰 덩어리 안에 갇힌 흰색 아닌 구멍(패 면의 검정·빨강·초록 무늬) 중
/// 긴 변 1024 기준 3~400px 인 것의 합. 테이블 흰 테두리·연보라 패산·엎은 손패에는 갇힌 구멍이 거의 없다.
/// 뒷면 비율로 앞면을 못 정할 때(패산이 같이 들어간 자리, 넓어진 구역) 화료자를 고르는 데 쓴다.
int tilePatternArea(img.Image im, Uint8List white, NormBox box) {
  final r = box.toPixels(im.width, im.height);
  final w = r.width, h = r.height;
  if (w <= 2 || h <= 2) return 0;
  final scale = (im.width > im.height ? im.width : im.height) / 1024;
  final minHole = (3 * scale * scale).round(), maxHole = (400 * scale * scale).round();
  bool isWhite(int x, int y) => white[(r.y + y) * im.width + r.x + x] == 1;
  // 상자 가장자리에서 흰색 아닌 칸을 따라 채운다. 끝까지 안 닿은 흰색 아닌 칸이 구멍.
  final seen = Uint8List(w * h);
  final stack = <int>[];
  void push(int x, int y) {
    final k = y * w + x;
    if (seen[k] == 0 && !isWhite(x, y)) {
      seen[k] = 1;
      stack.add(k);
    }
  }

  for (var x = 0; x < w; x++) {
    push(x, 0);
    push(x, h - 1);
  }
  for (var y = 0; y < h; y++) {
    push(0, y);
    push(w - 1, y);
  }
  void flood() {
    while (stack.isNotEmpty) {
      final k = stack.removeLast();
      final x = k % w, y = k ~/ w;
      if (x > 0) push(x - 1, y);
      if (x < w - 1) push(x + 1, y);
      if (y > 0) push(x, y - 1);
      if (y < h - 1) push(x, y + 1);
    }
  }

  flood();
  // 남은 구멍을 덩어리별로 세어 크기가 맞는 것만 더한다.
  var area = 0;
  for (var y = 1; y < h - 1; y++) {
    for (var x = 1; x < w - 1; x++) {
      final k = y * w + x;
      if (seen[k] != 0 || isWhite(x, y)) continue;
      final before = stack.length;
      push(x, y);
      var size = 0;
      while (stack.length > before) {
        final q = stack.removeLast();
        size++;
        final qx = q % w, qy = q ~/ w;
        if (qx > 0) push(qx - 1, qy);
        if (qx < w - 1) push(qx + 1, qy);
        if (qy > 0) push(qx, qy - 1);
        if (qy < h - 1) push(qx, qy + 1);
      }
      if (size >= minHole && size <= maxHole) area += size;
    }
  }
  return area;
}

/// 손패 끝에서 그 사람의 오른쪽(울기 놓는 쪽) 테이블 모서리까지. 손패 상자는 빼고 가장자리 쪽으로는 넓힌다.
/// 2026-10-24 위 자리 발 퐁은 손패 시작에서 손패 길이의 0.82배, 손패 두께의 0.63배 떨어진 모서리에 있었다.
NormBox meldCorner(NormBox b, Side side, {double along = 0.9, double out = 0.7}) {
  final horizontal = side == Side.bottom || side == Side.top;
  final l = horizontal ? b.width : b.height;
  final t = horizontal ? b.height : b.width;
  final a = (l * along).round(), o = (t * out).round();
  int c(int v) => v.clamp(0, 1000);
  return switch (side) {
    Side.bottom => NormBox(b.ymin, b.xmax, c(b.ymax + o), c(b.xmax + a)),
    Side.top => NormBox(c(b.ymin - o), c(b.xmin - a), b.ymax, b.xmin),
    Side.right => NormBox(c(b.ymin - a), b.xmin, b.ymin, c(b.xmax + o)),
    Side.left => NormBox(b.ymax, c(b.xmin - o), c(b.ymax + a), b.xmax),
  };
}

NormBox? _findDora(img.Image im, FeltMask felt, TableLayout layout) {
  final excl = <(NormBox, double)>[
    for (final hz in layout.hands) (hz.box, 0.1),
    for (final rz in layout.rivers) (rz.box, 0.08),
  ];
  // 가운데 자동탁 판: 네 강 상자의 안쪽 끝으로 둘러싼 곳.
  final top = layout.river(Side.top), bottom = layout.river(Side.bottom);
  final left = layout.river(Side.left), right = layout.river(Side.right);
  if (top != null && bottom != null && left != null && right != null) {
    final y0 = top.box.ymin, y1 = bottom.box.ymax, x0 = left.box.xmin, x1 = right.box.xmax;
    if (y0 < y1 && x0 < x1) excl.add((NormBox(y0, x0, y1, x1), 0));
  }
  return findDoraBlob(im, felt, excl);
}

/// 펠트 위에 따로 놓인 작은 흰 패 덩어리(도라 표시패). [exclude] 의 상자(패딩 비율과 함께)는 보지 않는다.
/// 강처럼 큰 덩어리와 가운데 판에 붙은 덩어리는 크기·둘레 펠트 비율로 걸러진다.
NormBox? findDoraBlob(img.Image im, FeltMask felt, List<(NormBox, double)> exclude) {
  final w = im.width, h = im.height;
  final excl = _Grid(w, h);
  for (final (b, pad) in exclude) {
    final r = b.toPixels(w, h, pad: pad);
    for (var y = r.y; y < r.y + r.height; y++) {
      excl.v.fillRange(y * w + r.x, y * w + r.x + r.width, 1);
    }
  }

  final green = _Grid(w, h);
  final cand = _Grid(w, h);
  for (final p in im) {
    final i = p.y * w + p.x;
    if (_isGreen(p.r, p.g, p.b)) {
      green.v[i] = 1;
    } else if (excl.v[i] == 0 &&
        _isWhite(p.r, p.g, p.b, minValue: 0.55, maxSat: 0.2) &&
        felt.atNorm(p.x / w, p.y / h)) {
      cand.v[i] = 1;
    }
  }
  final blobs = cand.erode().dilate().dilate(2).erode(2);
  final (lab, sizes) = blobs.label();
  // 성분별 경계 상자.
  final n = sizes.length;
  final x0 = List.filled(n, w), y0 = List.filled(n, h), x1 = List.filled(n, -1), y1 = List.filled(n, -1);
  for (var i = 0; i < lab.length; i++) {
    final id = lab[i];
    if (id == 0) continue;
    final x = i % w, y = i ~/ w;
    if (x < x0[id]) x0[id] = x;
    if (x > x1[id]) x1[id] = x;
    if (y < y0[id]) y0[id] = y;
    if (y > y1[id]) y1[id] = y;
  }
  // 패 한두 장 크기(1024px 축소본 기준 실험값 760~1300px)만, 둘레 6px 중 펠트 비율이 가장 높은 것.
  final minArea = (w * h * 300 / (1024 * 768)).round(), maxArea = (w * h * 6000 / (1024 * 768)).round();
  const ring = 6;
  NormBox? best;
  var bestRatio = doraRingGreen;
  for (var id = 1; id < n; id++) {
    if (sizes[id] < minArea || sizes[id] > maxArea) continue;
    var g = 0, total = 0;
    for (var y = y0[id] - ring; y <= y1[id] + ring; y++) {
      for (var x = x0[id] - ring; x <= x1[id] + ring; x++) {
        final inside = x >= x0[id] && x <= x1[id] && y >= y0[id] && y <= y1[id];
        if (inside || x < 0 || y < 0 || x >= w || y >= h) continue;
        total++;
        if (green.v[y * w + x] == 1) g++;
      }
    }
    final ratio = total == 0 ? 0.0 : g / total;
    if (ratio >= bestRatio) {
      bestRatio = ratio;
      best = NormBox(
        (y0[id] * 1000 / h).round(),
        (x0[id] * 1000 / w).round(),
        ((y1[id] + 1) * 1000 / h).round(),
        ((x1[id] + 1) * 1000 / w).round(),
      );
    }
  }
  return best;
}

