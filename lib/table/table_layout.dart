/// 거치 촬영 모드의 구역 모델. 서버 `/v1/locate` 응답을 담는다. 순수 Dart.
///
/// 좌표는 0~1000 정규화 `[ymin, xmin, ymax, xmax]`, 자리는 **이미지 기준** [Side].
/// 자리(동남서북)로 바꾸는 것은 [SeatMap] 이 대국 기록으로 한다.
/// 설계: docs/table_reading_design.md
library;

/// 이미지 기준 자리. 순서가 반시계 차례(아래→오른쪽→위→왼쪽)와 같다.
enum Side { bottom, right, top, left }

extension SideX on Side {
  static Side? parse(String? s) {
    for (final v in Side.values) {
      if (v.name == s) return v;
    }
    return null;
  }

  String get label => const ['아래', '오른쪽', '위', '왼쪽'][index];

  /// 크롭을 바로 세우기 위해 **시계 방향**으로 돌릴 각도.
  ///
  /// 패는 그 사람이 읽도록 놓이므로 글자 윗부분이 테이블 중앙을 향한다.
  /// right 는 윗부분이 왼쪽 → 시계 90, top 은 180, left 는 윗부분이 오른쪽 → 시계 270.
  int get uprightRotationCw => const [0, 90, 180, 270][index];
}

/// 0~1000 정규화 상자.
class NormBox {
  final int ymin, xmin, ymax, xmax;
  const NormBox(this.ymin, this.xmin, this.ymax, this.xmax);

  static NormBox? fromList(List<dynamic>? l) {
    if (l == null || l.length != 4) return null;
    final v = <int>[];
    for (final x in l) {
      if (x is! num) return null;
      v.add(x.round().clamp(0, 1000));
    }
    if (v[0] >= v[2] || v[1] >= v[3]) return null;
    return NormBox(v[0], v[1], v[2], v[3]);
  }

  List<int> toList() => [ymin, xmin, ymax, xmax];

  int get width => xmax - xmin;
  int get height => ymax - ymin;

  /// [o] 의 가운데가 이 상자 안에 있는지.
  bool containsCenterOf(NormBox o) {
    final cx = (o.xmin + o.xmax) / 2, cy = (o.ymin + o.ymax) / 2;
    return cx >= xmin && cx <= xmax && cy >= ymin && cy <= ymax;
  }

  NormBox union(NormBox o) => NormBox(
        ymin < o.ymin ? ymin : o.ymin,
        xmin < o.xmin ? xmin : o.xmin,
        ymax > o.ymax ? ymax : o.ymax,
        xmax > o.xmax ? xmax : o.xmax,
      );

  /// 픽셀 좌표로. [pad] 는 상자 너비·높이의 비율로 사방을 넓힌다(이미지 밖은 잘림).
  PixelRect toPixels(int imageWidth, int imageHeight, {double pad = 0}) {
    final bw = width * pad, bh = height * pad;
    final x0 = ((xmin - bw) * imageWidth / 1000).floor().clamp(0, imageWidth);
    final x1 = ((xmax + bw) * imageWidth / 1000).ceil().clamp(0, imageWidth);
    final y0 = ((ymin - bh) * imageHeight / 1000).floor().clamp(0, imageHeight);
    final y1 = ((ymax + bh) * imageHeight / 1000).ceil().clamp(0, imageHeight);
    return PixelRect(x0, y0, (x1 - x0).clamp(1, imageWidth), (y1 - y0).clamp(1, imageHeight));
  }

  @override
  bool operator ==(Object other) =>
      other is NormBox &&
      other.ymin == ymin &&
      other.xmin == xmin &&
      other.ymax == ymax &&
      other.xmax == xmax;
  @override
  int get hashCode => Object.hash(ymin, xmin, ymax, xmax);
  @override
  String toString() => '[$ymin, $xmin, $ymax, $xmax]';
}

class PixelRect {
  final int x, y, width, height;
  const PixelRect(this.x, this.y, this.width, this.height);
  @override
  String toString() => 'PixelRect($x, $y, $width×$height)';
}

/// 손패 구역.
class HandZone {
  final Side side;
  final NormBox box;
  final bool faceUp;
  final double conf;
  const HandZone(this.side, this.box, {required this.faceUp, this.conf = 0});

  static HandZone? fromJson(Map<String, dynamic> j) {
    final side = SideX.parse(j['side'] as String?);
    final box = NormBox.fromList(j['box'] as List<dynamic>?);
    if (side == null || box == null) return null;
    return HandZone(side, box,
        faceUp: j['face_up'] == true, conf: ((j['conf'] as num?) ?? 0).toDouble());
  }

  Map<String, dynamic> toJson() =>
      {'side': side.name, 'box': box.toList(), 'face_up': faceUp, 'conf': conf};
}

/// 자리가 있는 구역(강).
class SidedZone {
  final Side side;
  final NormBox box;
  final double conf;
  const SidedZone(this.side, this.box, {this.conf = 0});

  static SidedZone? fromJson(Map<String, dynamic> j) {
    final side = SideX.parse(j['side'] as String?);
    final box = NormBox.fromList(j['box'] as List<dynamic>?);
    if (side == null || box == null) return null;
    return SidedZone(side, box, conf: ((j['conf'] as num?) ?? 0).toDouble());
  }

  Map<String, dynamic> toJson() => {'side': side.name, 'box': box.toList(), 'conf': conf};
}

/// 자리 없는 구역(왕패).
class Zone {
  final NormBox box;
  final double conf;
  const Zone(this.box, {this.conf = 0});

  static Zone? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    final box = NormBox.fromList(j['box'] as List<dynamic>?);
    return box == null ? null : Zone(box, conf: ((j['conf'] as num?) ?? 0).toDouble());
  }

  Map<String, dynamic> toJson() => {'box': box.toList(), 'conf': conf};
}

/// `/v1/locate` 결과. 폰이 움직이지 않으면 다음 촬영에 다시 쓸 수 있도록 저장 가능하다.
/// 서버 응답의 `usage` → {input_tokens, output_tokens}. 없으면 빈 맵.
Map<String, int> parseUsage(Object? j) => {
      if (j is Map)
        for (final e in j.entries)
          if (e.value is num) e.key.toString(): (e.value as num).toInt(),
    };

class TableLayout {
  final List<HandZone> hands;
  final List<SidedZone> rivers;

  /// 손패 줄과 따로 놓인 울기 묶음마다 상자 하나(한 자리에 여럿일 수 있다).
  final List<SidedZone> melds;
  final Zone? deadWall;
  final NormBox? center;
  final String notes;
  final String model;
  final int latencyMs;

  /// 서버가 알려 준 토큰 수(input_tokens·output_tokens). 비용 집계용.
  final Map<String, int> usage;

  const TableLayout({
    this.hands = const [],
    this.rivers = const [],
    this.melds = const [],
    this.deadWall,
    this.center,
    this.notes = '',
    this.model = '',
    this.latencyMs = 0,
    this.usage = const {},
  });

  factory TableLayout.fromJson(Map<String, dynamic> j) {
    final hands = <HandZone>[];
    final seen = <Side>{};
    for (final h in (j['hands'] as List<dynamic>?) ?? const []) {
      final z = h is Map<String, dynamic> ? HandZone.fromJson(h) : null;
      if (z != null && seen.add(z.side)) hands.add(z);
    }
    final rivers = <SidedZone>[];
    seen.clear();
    for (final r in (j['rivers'] as List<dynamic>?) ?? const []) {
      final z = r is Map<String, dynamic> ? SidedZone.fromJson(r) : null;
      if (z != null && seen.add(z.side)) rivers.add(z);
    }
    var center = NormBox.fromList((j['center'] as Map<String, dynamic>?)?['box'] as List<dynamic>?);
    if (center == null && rivers.isNotEmpty) {
      center = rivers.map((r) => r.box).reduce((a, b) => a.union(b));
    }
    return TableLayout(
      hands: hands,
      rivers: rivers,
      melds: [
        for (final m in (j['melds'] as List<dynamic>?) ?? const [])
          if (m is Map<String, dynamic>) ?SidedZone.fromJson(m),
      ],
      deadWall: Zone.fromJson(j['dead_wall'] as Map<String, dynamic>?),
      center: center,
      notes: (j['notes'] as String?) ?? '',
      model: (j['model'] as String?) ?? '',
      latencyMs: ((j['latency_ms'] as num?) ?? 0).toInt(),
      usage: parseUsage(j['usage']),
    );
  }

  Map<String, dynamic> toJson() => {
        'hands': hands.map((h) => h.toJson()).toList(),
        'rivers': rivers.map((r) => r.toJson()).toList(),
        'melds': melds.map((m) => m.toJson()).toList(),
        'dead_wall': deadWall?.toJson(),
        'center': center == null ? null : {'box': center!.toList()},
        'notes': notes,
        'model': model,
        'latency_ms': latencyMs,
        'usage': usage,
      };

  HandZone? hand(Side side) {
    for (final h in hands) {
      if (h.side == side) return h;
    }
    return null;
  }

  SidedZone? river(Side side) {
    for (final r in rivers) {
      if (r.side == side) return r;
    }
    return null;
  }

  List<SidedZone> meldsOf(Side side) => [for (final m in melds) if (m.side == side) m];

  /// [side] 의 울기 중 그 사람의 오른쪽(울기를 놓는 쪽)에 있는 것만. 손패 상자가 없으면 [meldsOf] 그대로.
  /// locate 가 옆자리 모서리의 울기를 이 자리 것으로 넣는 일이 있다(2026-10-24 갤러리 사진: 오른쪽 자리 발 퐁을
  /// 위 자리 울기로). 이미지 기준 오른쪽은 아래 +x, 위 -x, 오른쪽 자리 -y, 왼쪽 자리 +y.
  List<SidedZone> meldsRightOf(Side side) {
    final h = hand(side)?.box;
    if (h == null) return meldsOf(side);
    bool right(NormBox b) {
      final cx = b.xmin + b.xmax, cy = b.ymin + b.ymax;
      final hx = h.xmin + h.xmax, hy = h.ymin + h.ymax;
      return switch (side) {
        Side.bottom => cx > hx,
        Side.top => cx < hx,
        Side.right => cy < hy,
        Side.left => cy > hy,
      };
    }

    return [for (final m in meldsOf(side)) if (right(m.box)) m];
  }

  /// 앞면으로 눕힌 자리들(화료자 후보).
  List<Side> get faceUpSides => [for (final h in hands) if (h.faceUp) h.side];

  /// 눕힌 자리가 정확히 하나면 그 자리.
  Side? get singleFaceUp {
    final s = faceUpSides;
    return s.length == 1 ? s.first : null;
  }
}
