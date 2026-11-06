/// 탁자 기준점([TableFrame]) + 패 단위 구역표([ZoneTable]) — 개선 계획 8b "할 일 2"(2026-11-06). 순수 Dart.
///
/// 구역표는 `assets/table_frame/zones.json` 하나(규칙 몫 `rules` / 탁자 프로필 `profiles`)이고, 서버 쪽
/// `experiments/zone_points/table_frame.py`(뒤에 서버 `app/` 로)와 이 파일이 같은 기준점 + 사진 크기에 같은 구역 상자를 낸다.
/// 예제·기대 출력은 `test/fixtures/table_frame.json`(Python 이 만들고 이쪽이 맞춤, 점 허용 오차 0.5px).
///
/// 기준점 = 가운데 기기 가운데(사진 픽셀) · 방향 θ · 패 한 장 짧은 변 u(픽셀) · 기기 반폭 D(u). 사진 → 탁자 좌표는 비슷변환뿐
/// (호모그래피 없음): x = ((p − c)·ex)/u, y = ((p − c)·ey)/u, ex = (cos θ, sin θ), ey = (−sin θ, cos θ), y 가 큰 쪽이 아래 자리.
/// 자리 기준 (a, r): a = 그 사람 오른쪽, r = 그 사람 쪽(바깥). 아래 (x, y), 오른쪽 (−y, x), 위 (−x, −y), 왼쪽 (y, −x).
///
/// 지금 격자([GridZones], 사진 축 평행 선 4개)를 대체할 자료다. 격자·거치 화면·서버는 아직 이것을 안 쓴다(8b 3·4번 몫).
library;

import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/services.dart' show rootBundle;

import 'table_layout.dart';

/// 기준점을 어디서 잡았나: 화료 시점 기기 / 배패 때 패산이 올라온 첫 프레임 / 사용자가 찍음.
enum FrameSource { device, wall, manual }

typedef Pt = ({double x, double y});

/// 두 방향 차이(도, 90° 주기) 0~45.
double thetaDiffDeg(double a, double b) => ((((a - b) * 180 / math.pi) + 45) % 90 - 45).abs();

class TableFrame {
  /// 가운데 기기 가운데(사진 픽셀).
  final double cx, cy;

  /// 방향(라디안) — 패 회전 상자 각도의 90° 주기 평균.
  final double theta;

  /// 패 한 장 짧은 변(픽셀).
  final double u;

  /// 기기 반폭(u).
  final double d;

  /// 이 기준점을 잰 사진 크기. 다른 크기 사진에 쓸 때는 [scaledTo].
  final double width, height;

  final FrameSource source;

  /// 잰 시각(ISO 문자열 그대로, 없으면 null).
  final String? at;

  const TableFrame({
    required this.cx,
    required this.cy,
    required this.theta,
    required this.u,
    required this.d,
    required this.width,
    required this.height,
    this.source = FrameSource.device,
    this.at,
  });

  static TableFrame fromJson(Map<String, dynamic> j) {
    final size = (j['size'] as List<dynamic>).cast<num>();
    final src = j['source'] as String? ?? 'device';
    return TableFrame(
      cx: (j['cx'] as num).toDouble(),
      cy: (j['cy'] as num).toDouble(),
      theta: (j['theta'] as num).toDouble(),
      u: (j['u'] as num).toDouble(),
      d: (j['D'] as num).toDouble(),
      width: size[0].toDouble(),
      height: size[1].toDouble(),
      source: FrameSource.values.firstWhere((s) => s.name == src),
      at: j['at'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'cx': cx,
        'cy': cy,
        'theta': theta,
        'u': u,
        'D': d,
        'size': [width, height],
        'source': source.name,
        'at': at,
      };

  /// 같은 카메라·같은 화각의 다른 크기 사진(1020 미리보기 프레임 → 4080 사진 등). 비슷변환이라 가로 비 하나로 늘린다.
  TableFrame scaledTo(double w, double h) {
    final k = w / width;
    return TableFrame(cx: cx * k, cy: cy * k, theta: theta, u: u * k, d: d, width: w, height: h, source: source, at: at);
  }

  /// 패산 사각형(배패 때 첫 프레임)에서: u = 눕힌 뒷면 짧은 변 × `u_per_back_short`, D = (패산 반폭 / u) / `wall_half_per_device`.
  static TableFrame fromWall({
    required double cx,
    required double cy,
    required double theta,
    required double backShortPx,
    required double wallHalfPx,
    required double width,
    required double height,
    required Map<String, dynamic> profile,
    String? at,
  }) {
    final u = backShortPx * (profile['u_per_back_short'] as num).toDouble();
    return TableFrame(
      cx: cx,
      cy: cy,
      theta: theta,
      u: u,
      d: wallHalfPx / u / (profile['wall_half_per_device'] as num).toDouble(),
      width: width,
      height: height,
      source: FrameSource.wall,
      at: at,
    );
  }

  /// 두 기준점이 거치 이동으로 볼 만큼 다른지(가운데 > `move_center_u` 또는 방향 > `move_theta_deg`).
  bool movedFrom(TableFrame other, ZoneTable table) {
    final o = other.scaledTo(width, height);
    final fc = table.rules['frame_check'] as Map<String, dynamic>;
    final dc = math.sqrt((cx - o.cx) * (cx - o.cx) + (cy - o.cy) * (cy - o.cy)) / u;
    return dc > (fc['move_center_u'] as num) || thetaDiffDeg(theta, o.theta) > (fc['move_theta_deg'] as num);
  }
}

/// 구역표(`assets/table_frame/zones.json`).
class ZoneTable {
  final Map<String, dynamic> rules;
  final Map<String, dynamic> profiles;
  final String defaultProfile;

  const ZoneTable._(this.rules, this.profiles, this.defaultProfile);

  static const String assetPath = 'assets/table_frame/zones.json';

  static ZoneTable fromJson(Map<String, dynamic> j) {
    if (j['version'] != 1) throw FormatException('구역표 version ${j['version']}');
    final rules = j['rules'] as Map<String, dynamic>;
    for (final MapEntry(:key, :value) in (rules['zones'] as Map<String, dynamic>).entries) {
      final z = value as Map<String, dynamic>;
      if (!const ['side', 'center'].contains(z['kind']) || (z['a'] as List).length != 2 || (z['r'] as List).length != 2) {
        throw FormatException('구역 $key');
      }
    }
    return ZoneTable._(rules, j['profiles'] as Map<String, dynamic>, j['default_profile'] as String);
  }

  static Future<ZoneTable> load() async =>
      fromJson(jsonDecode(await rootBundle.loadString(assetPath)) as Map<String, dynamic>);

  Map<String, dynamic> profile([String? name]) => profiles[name ?? defaultProfile] as Map<String, dynamic>;

  Map<String, dynamic> zone(String name) => (rules['zones'] as Map<String, dynamic>)[name] as Map<String, dynamic>;

  Iterable<String> get zoneNames => (rules['zones'] as Map<String, dynamic>).keys;
}

/// 회전 사각형. [pts] = 사진 픽셀 네 점((a0,r0) (a1,r0) (a1,r1) (a0,r1) — 그 자리 사람이 아래에 오게 세웠을 때 왼쪽 위부터 시계 방향),
/// [angleDeg] = a 축이 사진에서 향하는 각(이 크롭을 −angleDeg 돌리면 그 사람이 아래). 끝값이 엇갈리면(사진이 거기까지 안 닿음) [pts] 가 비었다.
class RotRect {
  final List<Pt> pts;
  final double angleDeg;
  final double a0, a1, r0, r1;

  const RotRect(this.pts, this.angleDeg, this.a0, this.a1, this.r0, this.r1);

  bool get isEmpty => pts.isEmpty;

  /// 축 평행 외접 상자(x0, y0, x1, y1)를 사진 안으로 자른 것. 사진 밖이면 null.
  ({double x0, double y0, double x1, double y1})? bbox(double w, double h) {
    if (isEmpty) return null;
    final xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    final x0 = math.max(0.0, xs.reduce(math.min)), y0 = math.max(0.0, ys.reduce(math.min));
    final x1 = math.min(w, xs.reduce(math.max)), y1 = math.min(h, ys.reduce(math.max));
    return x1 > x0 && y1 > y0 ? (x0: x0, y0: y0, x1: x1, y1: y1) : null;
  }

  /// 지금 크롭 코드가 받는 [NormBox](0~1000). 사진 밖이면 null.
  NormBox? norm(double w, double h) {
    final b = bbox(w, h);
    if (b == null) return null;
    int r(double v) => (v + 0.5).floor();
    return NormBox(r(b.y0 / h * 1000), r(b.x0 / w * 1000), r(b.y1 / h * 1000), r(b.x1 / w * 1000));
  }
}

/// 기준점 + 사진 크기 → 구역 상자. 기준점이 다른 크기 사진에서 잰 것이면 이 사진 크기로 옮겨 쓴다.
class TableZones {
  final ZoneTable table;
  final TableFrame frame;
  final double width, height;
  late final double _c = math.cos(frame.theta), _s = math.sin(frame.theta);

  /// 가운데 칸 반폭(u).
  late final double r = _expr(table.rules['center_half'] as Map<String, dynamic>, rOverride: 0);

  /// 사진 끝(가운데에서 가장 먼 사진 모서리의 max(|x|,|y|), u).
  late final double edge = [
    for (final (x, y) in [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]) _maxAbs(toFrame(x, y)),
  ].reduce(math.max);

  TableZones(this.table, TableFrame frame, this.width, this.height)
      : frame = frame.width == width && frame.height == height ? frame : frame.scaledTo(width, height);

  static double _maxAbs(Pt q) => math.max(q.x.abs(), q.y.abs());

  Pt toFrame(double x, double y) {
    final dx = x - frame.cx, dy = y - frame.cy;
    return (x: (dx * _c + dy * _s) / frame.u, y: (-dx * _s + dy * _c) / frame.u);
  }

  Pt fromFrame(double qx, double qy) =>
      (x: frame.cx + frame.u * (qx * _c - qy * _s), y: frame.cy + frame.u * (qx * _s + qy * _c));

  static Pt sideToFrame(Side side, double a, double r) => switch (side) {
        Side.bottom => (x: a, y: r),
        Side.right => (x: r, y: -a),
        Side.top => (x: -a, y: -r),
        Side.left => (x: -r, y: a),
      };

  /// 사진 픽셀 → [side] 자리 기준 (a, r)(u).
  ({double a, double r}) local(Side side, double x, double y) {
    final q = toFrame(x, y);
    return switch (side) {
      Side.bottom => (a: q.x, r: q.y),
      Side.right => (a: -q.y, r: q.x),
      Side.top => (a: -q.x, r: -q.y),
      Side.left => (a: q.y, r: -q.x),
    };
  }

  double angleDeg(Side side) {
    final rot = switch (side) { Side.bottom => 0.0, Side.right => -90.0, Side.top => 180.0, Side.left => 90.0 };
    return (frame.theta * 180 / math.pi + rot + 180) % 360 - 180;
  }

  double _expr(Map<String, dynamic> e, {double? rOverride}) {
    double v(String k) => (e[k] as num?)?.toDouble() ?? 0;
    if (e.containsKey('edge')) return v('edge') * edge;
    return v('c') + v('D') * frame.d + v('R') * (rOverride ?? r);
  }

  /// 구역 끝값 (a0, a1, r0, r1)(u, 그 자리 기준). kind=center 는 [side] 무시(아래 자리 기준).
  ({double a0, double a1, double r0, double r1}) bounds(String name, {Side side = Side.bottom, Set<Side> except = const {}}) {
    final z = table.zone(name);
    final a = (z['a'] as List).cast<Map<String, dynamic>>(), rr = (z['r'] as List).cast<Map<String, dynamic>>();
    var a0 = _expr(a[0]), a1 = _expr(a[1]), r0 = _expr(rr[0]), r1 = _expr(rr[1]);
    final g = (z['grow_u'] as num?)?.toDouble();
    if (g != null && g != 0) {
      // 표시패 탐색: except 가 아닌 자리 쪽으로 넓힘(아래 자리 기준 a = x 오른쪽, r = y 아래).
      if (!except.contains(Side.left)) a0 -= g;
      if (!except.contains(Side.right)) a1 += g;
      if (!except.contains(Side.top)) r0 -= g;
      if (!except.contains(Side.bottom)) r1 += g;
    }
    return (a0: a0, a1: a1, r0: r0, r1: r1);
  }

  RotRect rect(String name, {Side side = Side.bottom, Set<Side> except = const {}}) {
    if (table.zone(name)['kind'] == 'center') side = Side.bottom;
    final b = bounds(name, side: side, except: except);
    final ang = angleDeg(side);
    if (b.a1 <= b.a0 || b.r1 <= b.r0) return RotRect(const [], ang, b.a0, b.a1, b.r0, b.r1);
    Pt p(double a, double r) {
      final q = sideToFrame(side, a, r);
      return fromFrame(q.x, q.y);
    }

    return RotRect([p(b.a0, b.r0), p(b.a1, b.r0), p(b.a1, b.r1), p(b.a0, b.r1)], ang, b.a0, b.a1, b.r0, b.r1);
  }

  /// 사진 점이 그 구역 안인지(끝 포함).
  bool inside(String name, double x, double y, {Side side = Side.bottom, Set<Side> except = const {}}) {
    if (table.zone(name)['kind'] == 'center') side = Side.bottom;
    final l = local(side, x, y);
    final b = bounds(name, side: side, except: except);
    return b.a0 <= l.a && l.a <= b.a1 && b.r0 <= l.r && l.r <= b.r1;
  }

  /// 바람개비 5칸 중 어디인지: 자리 또는 null(가운데). 자리 칸은 아래쪽 끝값을 넘어야(a > a0 · r > r0) — [GridZones] 와 같은 경계.
  Side? zoneOf(double x, double y) {
    for (final s in Side.values) {
      final l = local(s, x, y);
      final b = bounds('seat', side: s);
      if (l.a > b.a0 && l.r > b.r0) return s;
    }
    return null;
  }

  // 앱 GridZones 와 같은 종류의 크롭 ------------------------------------------
  RotRect seat(Side side) => rect('seat', side: side);
  RotRect hand(Side side) => rect('hand', side: side);
  RotRect corner(Side side) => rect('corner', side: side);
  RotRect river(Side side) => rect('river', side: side);
  RotRect stickStrip(Side side) => rect('stick_strip', side: side);
  RotRect deadWall(Side side) => rect('dead_wall', side: side);
  RotRect get center => rect('center');
  RotRect get device => rect('device');
  RotRect get sticks => rect('sticks');
  RotRect doraSearch({Set<Side> except = const {}}) => rect('dora_search', except: except);

  /// 'seat.bottom' … 'center' 처럼 이름(.자리) → 상자(예제 파일과 같은 이름).
  Map<String, RotRect> allRects({Set<Side> except = const {}}) => {
        for (final name in table.zoneNames)
          if (table.zone(name)['kind'] == 'side')
            for (final s in Side.values) '$name.${s.name}': rect(name, side: s)
          else
            name: rect(name, except: except),
      };
}
