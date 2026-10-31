/// 미리 그은 격자 구역. 카메라를 고정해 두고 사용자가 선 네 개를 한 번 맞춰 두면,
/// locate(약 24초, 호출마다 흔들림) 없이 구역마다 잘라 각각 읽는다. 순수 Dart.
///
/// 구역은 5개다: 자리 4개(바람개비) + 가운데.
/// ```
///            x1          x2
///   ┌────────────────────┬────────┐
///   │        위 자리       │        │
/// y1├────────┬───────────┤ 오른쪽  │
///   │        │           │  자리   │
///   │  왼쪽   │   가운데    │        │
///   │  자리   │ (강·리치봉·  │        │
/// y2│        │   도라)     ├────────┤
///   │        ├───────────┴────────┤
///   │        │       아래 자리       │
///   └────────┴────────────────────┘
/// ```
/// 자리 = 그 사람 앞 손패 + 그 사람 오른쪽 모서리(울기를 놓는 곳). 손패 옆에 둔 도라 표시패도 대개 여기 들어온다.
/// 처음엔 손패·모서리 울기 칸을 따로 나눈 9칸이었는데, 도라가 칸 경계나 손패 옆에 놓이면 못 읽었다(2026-10-25 장면 C·E).
/// 자리 구역은 크고 대부분 빈 펠트·테이블 밖이라 패가 작게 들어간다. Gemini 는 보낸 해상도와 관계없이 이미지를 같은 토큰 수로
/// 줄이므로 서버가 자리 판독만 이미지 해상도 수준을 ULTRA_HIGH 로 올린다(4삭 안깡을 8삭·2삭으로 읽던 것이 2/2 정답).
/// 패가 놓인 부분만 픽셀로 꽉 맞춰 자르는 방법은 테이블 흰 테두리 위에 둔 울기(모서리 퐁·치)를 빼 버려 쓰지 않는다.
/// 기본값은 2026-10-25 사용자가 매장 사진(AMOS 자동탁, 오른쪽 자리 뒤 삼각대)에 그은 선이다.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'fixed_layout.dart';
import 'table_layout.dart';

/// 앞면(화료자) 자리는 손패 칸의 앞면 패 무늬 넓이로 정한다([faceUpByPattern]). 처음엔 연보라 뒷면 비율이 먼저였는데
/// (장면 C 는 왼쪽 패산 때문에 그것으로 못 정해 네 자리를 다 읽었다), 다른 색 뒷면에서 무너져 무늬만 쓴다(2026-10-27).

/// 강 끝 크롭: 가운데 칸 한가운데부터 그 자리 쪽 끝까지, 옆으로는 가운데 칸 폭의 이 비율만(가운데 정렬).
/// 칸 폭 전체로 자르면 따로 놓인 도라 표시패가 섞여 모델이 오래 생각하거나(15~36초) 마지막 패를 못 찾았다(장면 D 오른쪽 강).
const double lastZoneBand = 0.6;

/// 가운데 칸 도라 크롭을 바깥으로 넓히는 폭(0~1000, 패 약 1.5장). 도라 산을 못 잡은 판에서 격자 선에 걸친 표시패까지 읽게
/// (사용자 제안 2026-10-29 "화료자 손패 구역뿐 아니라 다른 영역도" — 바깥 띠 구조 D 에서 4통·4통·7만 이 오른쪽 선에 걸려
/// 4통만 읽힘). 손패 줄(띠 선에서 패 1.5장 바깥)에는 닿지 않을 만큼.
const int doraSearchMargin = 40;

/// 리치봉 크롭: 가운데 칸 한가운데에서 이 비율만큼(가운데 기기와 그 둘레).
const double sticksZoneShare = 0.7;

/// 추적용 강 띠가 시작하는 곳(가운데에서 그 자리 쪽 반폭의 비율). 0 = [lastZone] 전체.
/// 격자 가운데 칸의 한가운데가 기기 한가운데와 다를 수 있어(장면 D: 아래쪽은 기기가 반폭의 8%, 오른쪽은 20%) 기기 몫을
/// 떼지 않는다 — 떼면 기기에 붙은 첫 줄을 잃는다. 기기(검정)는 변하지 않으니 띠에 들어 있어도 해가 없다.
const double riverStart = 0.0;

/// 추적용 리치봉 띠: 가운데에서 [stickStart]~[stickEnd](기기 가장자리 홈이 있는 곳). 강 띠와 겹친다.
const double stickStart = 0.0;
const double stickEnd = 0.25;

/// 화료자 손패를 읽을 때 자리 크롭을 격자 선에서 가운데 쪽으로 더 넓히는 폭(0~1000). 공개할 때 앞으로 내민 손패가 선에 걸려
/// 잘리던 것(10-31 매장 오후 8/15). B·C·D 12/12 그대로, 매장 오전 정답 6/7 → 7/7, 80 은 강이 섞여 6/7(metrics 표 1-2).
const int seatReadGrow = 40;

/// 가운데 칸 기준 상대 상자. 1000 = 가운데 칸 폭(u)·높이(v), 0~1000 밖이면 자리 구역으로 나간 것.
typedef RelBox = ({int u0, int v0, int u1, int v1});

/// 선(친)이 아래쪽일 때 도라 구역의 기본값([GridZones.doraRel]).
/// AMOS 자동탁 매장 관행("자5": 선 앞 패산을 오른쪽에서 5줄째에서 나눔)대로면 왕패·도라 표시패는 선 앞 패산 오른쪽 끝에 온다.
/// 패산은 손패와 강 사이, 곧 자리·가운데 경계(아래 선)에 걸치므로 경계 위아래와 오른쪽 모서리 쪽까지 잡는다.
/// 주사위로 패산을 여는 탁이면 왕패는 주사위 합에 따라 네 변 어디든(모서리를 돌아 ㄱ자로도) 오므로 이 상자는 예비일 뿐이다
/// (왕패 = 나눈 곳 오른쪽 7줄, 표시패 = 그 3번째 줄 위 — 사용자가 준 규칙 글, 2026-10-29).
const RelBox doraRelDefault = (u0: 500, v0: 750, u1: 1250, v1: 1250);

class GridZones {
  /// 세로선(왼쪽·오른쪽)과 가로선(위·아래), 0~1000.
  final int x1, x2, y1, y2;

  /// 선이 아래쪽일 때의 도라 구역(가운데 칸 기준). 다른 자리가 선이면 [doraZone] 이 그 자리 쪽으로 돌린다.
  final RelBox doraRel;

  /// 리치봉 구역(가운데 기기 둘레, 사진 좌표). 처음 설정 때 맞춰 둔 상자(사용자 2026-10-29: 손패+울기 바깥 띠 · 리치봉 상자 ·
  /// 나머지 패산 구역으로 크게 나누기). 없으면 가운데 칸 한가운데 [sticksZoneShare] 만큼.
  final NormBox? sticks;

  /// [sticks] 상자를 그 한가운데로 돌린 각도(도, 시계 방향). 기운 탁자에서 기기에 맞춘다. 자를 때는 돌린 상자를 감싸는 상자.
  final int sticksAngle;

  const GridZones({
    required this.x1,
    required this.x2,
    required this.y1,
    required this.y2,
    this.doraRel = doraRelDefault,
    this.sticks,
    this.sticksAngle = 0,
  });

  /// 오른쪽 선은 사용자가 도라 표시패(오른쪽 아래)를 감싸 휘게 그린 것을 직선으로 펴 그 패들이 가운데에 들어오게 했다.
  static const GridZones initial = GridZones(x1: 280, x2: 745, y1: 173, y2: 713);

  bool get valid => 0 < x1 && x1 < x2 && x2 < 1000 && 0 < y1 && y1 < y2 && y2 < 1000;

  NormBox get center => NormBox(y1, x1, y2, x2);

  /// [side] 사람 자리: 앞 손패 변 + 그 사람 오른쪽 모서리. 네 자리와 [center] 가 겹치지 않고 사진 전체를 덮는다.
  NormBox seat(Side side) => switch (side) {
        Side.bottom => NormBox(y2, x1, 1000, 1000),
        Side.right => NormBox(0, x2, y2, 1000),
        Side.top => NormBox(0, 0, y1, x2),
        Side.left => NormBox(y1, 0, 1000, x1),
      };

  /// [side] 자리를 나눈 손패 칸(선 사이 변)과 오른쪽 모서리 칸. 둘을 합치면 [seat]. 나눠 읽기 실험용(`TableReader.readGrid` 의 splitSeat).
  NormBox handCell(Side side) => switch (side) {
        Side.bottom => NormBox(y2, x1, 1000, x2),
        Side.right => NormBox(y1, x2, y2, 1000),
        Side.top => NormBox(0, x1, y1, x2),
        Side.left => NormBox(y1, 0, y2, x1),
      };

  /// 손패 판독에 보낼 [seat]·[handCell]: 가운데 쪽 변만 [seatReadGrow] 만큼 넓힌다. 구역을 나누는 선은 그대로라 강·리치봉 크롭은 안 바뀐다.
  NormBox seatForRead(Side side) => _growInward(seat(side), side);
  NormBox handCellForRead(Side side) => _growInward(handCell(side), side);

  NormBox _growInward(NormBox b, Side side) => switch (side) {
        Side.bottom => NormBox(b.ymin - seatReadGrow, b.xmin, b.ymax, b.xmax),
        Side.right => NormBox(b.ymin, b.xmin - seatReadGrow, b.ymax, b.xmax),
        Side.top => NormBox(b.ymin, b.xmin, b.ymax + seatReadGrow, b.xmax),
        Side.left => NormBox(b.ymin, b.xmin, b.ymax, b.xmax + seatReadGrow),
      };

  /// [seat] 크롭을 그 사람 방향으로 세웠을 때 왼쪽부터 [handCell] 이 차지하는 폭 비율(나머지가 오른쪽 모서리).
  /// `/v2/seat?hand_frac=` 로 보내면 서버가 손패 틀을 못 잡은 자리를 손패 칸·모서리 칸으로 나눠 한 번 더 잡는다.
  double handFrac(Side side) => switch (side) {
        Side.bottom => (x2 - x1) / (1000 - x1),
        Side.right => (y2 - y1) / y2,
        Side.top => (x2 - x1) / x2,
        Side.left => (y2 - y1) / (1000 - y1),
      };

  NormBox cornerCell(Side side) => switch (side) {
        Side.bottom => NormBox(y2, x2, 1000, 1000),
        Side.right => NormBox(0, x2, y1, 1000),
        Side.top => NormBox(0, 0, y1, x1),
        Side.left => NormBox(y2, 0, 1000, x1),
      };

  /// [side] 의 강 끝: 가운데 칸 한가운데부터 그 자리 쪽 끝까지, 옆으로는 가운데 [band] 만큼.
  NormBox lastZone(Side side, {double band = lastZoneBand}) {
    final cx = (x1 + x2) ~/ 2, cy = (y1 + y2) ~/ 2;
    final hw = ((x2 - x1) * band / 2).round(), hh = ((y2 - y1) * band / 2).round();
    return switch (side) {
      Side.bottom => NormBox(cy, cx - hw, y2, cx + hw),
      Side.top => NormBox(y1, cx - hw, cy, cx + hw),
      Side.left => NormBox(cy - hh, x1, cy + hh, cx),
      Side.right => NormBox(cy - hh, cx, cy + hh, x2),
    };
  }

  /// 강 띠(판 상태 추적용): [lastZone] 에서 [riverStart] 부터 그 자리 끝까지(기본은 lastZone 전체).
  NormBox riverBand(Side side, {double start = riverStart, double band = lastZoneBand}) =>
      start <= 0 ? lastZone(side, band: band) : _alongSide(side, start, 1.0, band);

  /// 리치봉 띠(판 상태 추적용): 가운데 기기 가장자리(홈) 쪽, [stickStart]~[stickEnd]. 강 띠 안쪽과 겹친다.
  NormBox stickStrip(Side side, {double start = stickStart, double end = stickEnd, double band = lastZoneBand}) {
    final b = sticks;
    if (b == null) return _alongSide(side, start, end, band);
    // 리치봉 상자가 있으면 그 상자 안, 그 자리 쪽 변을 따라 상자 두께의 30% 띠(옆으로는 가운데 60%).
    final dw = (b.width * 0.2).round(), dh = (b.height * 0.2).round();
    final tw = (b.width * 0.3).round(), th = (b.height * 0.3).round();
    return switch (side) {
      Side.bottom => NormBox(b.ymax - th, b.xmin + dw, b.ymax, b.xmax - dw),
      Side.top => NormBox(b.ymin, b.xmin + dw, b.ymin + th, b.xmax - dw),
      Side.left => NormBox(b.ymin + dh, b.xmin, b.ymax - dh, b.xmin + tw),
      Side.right => NormBox(b.ymin + dh, b.xmax - tw, b.ymax - dh, b.xmax),
    };
  }

  /// 가운데 칸 한가운데에서 [side] 쪽으로 반폭의 [from]~[to] 구간, 옆으로는 [band] 비율.
  NormBox _alongSide(Side side, double from, double to, double band) {
    final cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
    final hw = (x2 - x1) / 2, hh = (y2 - y1) / 2;
    final bw = (hw * band).round(), bh = (hh * band).round();
    return switch (side) {
      Side.bottom => NormBox((cy + hh * from).round(), (cx - bw).round(), (cy + hh * to).round(), (cx + bw).round()),
      Side.top => NormBox((cy - hh * to).round(), (cx - bw).round(), (cy - hh * from).round(), (cx + bw).round()),
      Side.left => NormBox((cy - bh).round(), (cx - hw * to).round(), (cy + bh).round(), (cx - hw * from).round()),
      Side.right => NormBox((cy - bh).round(), (cx + hw * from).round(), (cy + bh).round(), (cx + hw * to).round()),
    };
  }

  /// 가운데 칸 도라 크롭: [center] 를 [except] 가 아닌 자리 쪽으로 [margin] 만큼 넓힌 것. 화료자 쪽은 넓히지 않는다
  /// (앞면으로 눕힌 손패가 도라로 읽히지 않게. 화료자 쪽 따로 놓인 패는 자리 판독이 읽는다).
  NormBox doraSearchZone({Set<Side> except = const {}, int margin = doraSearchMargin}) {
    int grow(Side s) => except.contains(s) ? 0 : margin;
    return NormBox(
      (y1 - grow(Side.top)).clamp(0, 1000),
      (x1 - grow(Side.left)).clamp(0, 1000),
      (y2 + grow(Side.bottom)).clamp(0, 1000),
      (x2 + grow(Side.right)).clamp(0, 1000),
    );
  }

  /// 선이 [dealer] 쪽일 때 도라 표시패를 볼 곳(사진 좌표). [doraRel] 을 가운데 칸 둘레로 자리 순서(아래 → 오른쪽 → 위 → 왼쪽)만큼
  /// 90°씩 돌린다: 아래 → 오른쪽은 (u, v) → (v, 1 − u). 사진이 기울어 칸이 직사각형이 아니어도 칸 비율로 돌리므로 대략 맞는다.
  NormBox doraZone(Side dealer) {
    var r = doraRel;
    for (var i = 0; i < dealer.index; i++) {
      r = (u0: r.v0, v0: 1000 - r.u1, u1: r.v1, v1: 1000 - r.u0);
    }
    int x(int u) => (x1 + u * (x2 - x1) / 1000).round().clamp(0, 1000);
    int y(int v) => (y1 + v * (y2 - y1) / 1000).round().clamp(0, 1000);
    return NormBox(y(r.v0), x(r.u0), y(r.v1), x(r.u1));
  }

  /// 선이 [dealer] 쪽일 때 사진 좌표 [box] 를 도라 구역으로(격자 맞추기에서 상자를 옮긴 것). [doraZone] 의 반대.
  GridZones withDoraZone(Side dealer, NormBox box) {
    int u(int x) => ((x - x1) * 1000 / (x2 - x1)).round();
    int v(int y) => ((y - y1) * 1000 / (y2 - y1)).round();
    var r = (u0: u(box.xmin), v0: v(box.ymin), u1: u(box.xmax), v1: v(box.ymax));
    for (var i = 0; i < (4 - dealer.index) % 4; i++) {
      r = (u0: r.v0, v0: 1000 - r.u1, u1: r.v1, v1: 1000 - r.u0);
    }
    return GridZones(x1: x1, x2: x2, y1: y1, y2: y2, doraRel: r, sticks: sticks, sticksAngle: sticksAngle);
  }

  /// 리치봉을 볼 곳: 가운데 칸 한가운데 [share] 만큼.
  NormBox get sticksZone {
    if (sticks case final b?) return sticksAngle == 0 ? b : rotatedBounds(b, sticksAngle);
    final cx = (x1 + x2) ~/ 2, cy = (y1 + y2) ~/ 2;
    final hw = ((x2 - x1) * sticksZoneShare / 2).round(), hh = ((y2 - y1) * sticksZoneShare / 2).round();
    return NormBox(cy - hh, cx - hw, cy + hh, cx + hw);
  }

  /// 화면 표시·기록용 구역. 손패 자리에 자리 구역, 강 자리에 강 끝 크롭 상자를 넣는다.
  TableLayout toLayout({List<Side> faceUp = const []}) => TableLayout(
        hands: [for (final s in Side.values) HandZone(s, seat(s), faceUp: faceUp.contains(s))],
        rivers: [for (final s in Side.values) SidedZone(s, lastZone(s))],
        center: center,
        notes: '격자 구역(locate 생략)',
        model: 'grid',
      );

  GridZones copyWith({int? x1, int? x2, int? y1, int? y2, RelBox? doraRel, NormBox? sticks, int? sticksAngle}) =>
      GridZones(
        x1: x1 ?? this.x1,
        x2: x2 ?? this.x2,
        y1: y1 ?? this.y1,
        y2: y2 ?? this.y2,
        doraRel: doraRel ?? this.doraRel,
        sticks: sticks ?? this.sticks,
        sticksAngle: sticksAngle ?? this.sticksAngle,
      );

  Map<String, dynamic> toJson() => {
    'x1': x1,
    'x2': x2,
    'y1': y1,
    'y2': y2,
    'dora': [doraRel.u0, doraRel.v0, doraRel.u1, doraRel.v1],
    if (sticks case final b?) 'sticks': b.toList(),
    if (sticksAngle != 0) 'sticks_angle': sticksAngle,
  };

  /// 예전 저장값의 `panel`(가운데 기기 상자)은 무시한다. `dora` 가 없으면(예전 저장값) 기본 도라 구역.
  static GridZones? fromJson(Map<String, dynamic> j) {
    int? n(String k) => (j[k] as num?)?.round();
    final x1 = n('x1'), x2 = n('x2'), y1 = n('y1'), y2 = n('y2');
    if (x1 == null || x2 == null || y1 == null || y2 == null) return null;
    var dora = doraRelDefault;
    if (j['dora'] case [final num a, final num b, final num c, final num d] when a < c && b < d) {
      dora = (u0: a.round(), v0: b.round(), u1: c.round(), v1: d.round());
    }
    final g = GridZones(
      x1: x1,
      x2: x2,
      y1: y1,
      y2: y2,
      doraRel: dora,
      sticks: NormBox.fromList(j['sticks'] as List<dynamic>?),
      sticksAngle: n('sticks_angle') ?? 0,
    );
    return g.valid ? g : null;
  }

  @override
  bool operator ==(Object other) =>
      other is GridZones &&
      other.x1 == x1 &&
      other.x2 == x2 &&
      other.y1 == y1 &&
      other.y2 == y2 &&
      other.doraRel == doraRel &&
      other.sticks?.toList().join(',') == sticks?.toList().join(',') &&
      other.sticksAngle == sticksAngle;
  @override
  int get hashCode => Object.hash(x1, x2, y1, y2, doraRel, sticks?.toList().join(','), sticksAngle);
}

/// [box] 를 그 한가운데로 [deg] 도 돌린 상자를 감싸는 상자. 사진 비율 [aspect](가로/세로, 촬영 4:3)로 실제 픽셀처럼 돌린다.
NormBox rotatedBounds(NormBox box, int deg, {double aspect = 4 / 3}) {
  final a = deg * math.pi / 180;
  final cx = (box.xmin + box.xmax) / 2 * aspect, cy = (box.ymin + box.ymax) / 2;
  final hw = box.width / 2 * aspect, hh = box.height / 2;
  final ex = (hw * math.cos(a)).abs() + (hh * math.sin(a)).abs();
  final ey = (hw * math.sin(a)).abs() + (hh * math.cos(a)).abs();
  int c(double v) => v.round().clamp(0, 1000);
  return NormBox(c(cy - ey), c((cx - ex) / aspect), c(cy + ey), c((cx + ex) / aspect));
}

/// 처음 설정 틀의 손패+울기 안쪽 끝에서 가운데 쪽으로 둘 여유(패 가로 단위). 화료 때 눕혀 앞으로 나온 손패까지 띠에 들게.
const double setupStripMargin = 1.5;

/// 리치봉 상자 = 가운데 기기 틀 + 사방 이만큼(패 가로 단위). 홈 밖 기기 가장자리에 놓은 봉까지.
const double setupSticksPad = 0.5;

/// `/v2/setup` 응답(네 자리 손패·울기 틀, 가운데 기기 틀) → 처음 설정 격자(사용자 그림 2026-10-29: 손패+울기 바깥 띠 4개 ·
/// 리치봉 상자 · 나머지 패산 구역). 선 = 그 자리 손패(+울기) 안쪽 끝 − [setupStripMargin] u, 리치봉 = 기기 + [setupSticksPad] u.
/// u = 손패 줄 길이 / 13(네 자리 가운데 둘의 평균). 펠트 위 도라 표시패를 울기로 답하는 일이 있어(B·C), 손패 안쪽 끝보다
/// 패 1장 넘게 가운데로 나온 "울기" 는 넣지 않는다. 손패 틀이 하나라도 없거나 선이 엇갈리면 null. 도라 구역 모양은 [keep] 것.
/// B·C·D 실험(experiments/speed/setup_frames.py `strips`)과 같은 규칙.
GridZones? proposeGrid(Map<String, dynamic> setup, {GridZones? keep}) {
  NormBox? box(Object? v) => NormBox.fromList(v as List<dynamic>?);
  final seats = (setup['seats'] as Map<String, dynamic>?) ?? const {};
  final hand = <Side, NormBox>{};
  final melds = <Side, NormBox?>{};
  for (final s in Side.values) {
    final j = seats[s.name] as Map<String, dynamic>?;
    final h = box(j?['hand']);
    if (h == null) return null;
    hand[s] = h;
    melds[s] = box(j?['melds']);
  }
  final device = box(setup['device']);
  if (device == null) return null;
  final lens = [
    for (final s in Side.values) (s == Side.bottom || s == Side.top ? hand[s]!.width : hand[s]!.height) / 13,
  ]..sort();
  final u = (lens[1] + lens[2]) / 2;
  // 손패 ∪ (손패 줄 높이에 놓인) 울기
  NormBox seatBox(Side s) {
    final h = hand[s]!, m = melds[s];
    final atRow = m != null &&
        switch (s) {
          Side.bottom => m.ymin >= h.ymin - u,
          Side.top => m.ymax <= h.ymax + u,
          Side.left => m.xmax <= h.xmax + u,
          Side.right => m.xmin >= h.xmin - u,
        };
    if (!atRow) return h;
    return NormBox(math.min(h.ymin, m.ymin), math.min(h.xmin, m.xmin), math.max(h.ymax, m.ymax), math.max(h.xmax, m.xmax));
  }

  final margin = setupStripMargin * u;
  final y2 = (seatBox(Side.bottom).ymin - margin).round();
  final y1 = (seatBox(Side.top).ymax + margin).round();
  final x2 = (seatBox(Side.right).xmin - margin).round();
  final x1 = (seatBox(Side.left).xmax + margin).round();
  if (!(0 < x1 && x1 < x2 && x2 < 1000 && 0 < y1 && y1 < y2 && y2 < 1000)) return null;
  final p = setupSticksPad * u;
  int c(double v) => v.round().clamp(0, 1000);
  return GridZones(
    x1: x1,
    x2: x2,
    y1: y1,
    y2: y2,
    doraRel: keep?.doraRel ?? doraRelDefault,
    sticks: NormBox(c(device.ymin - p), c(device.xmin - p), c(device.ymax + p), c(device.xmax + p)),
  );
}

/// 자리 구역 픽셀 판정: 앞면으로 눕힌 손패 자리. locate 축소본(JPEG) + 격자. `compute()` 에 넘길 수 있다. API 호출 없음.
/// 도라 표시패는 픽셀로 찾지 않는다(펠트 위 흰 덩어리 찾기가 손으로 찍은 사진 10장에서 0장).
ShotAnalysis analyzeGridShot((Uint8List, GridZones) args) {
  final (small, grid) = args;
  final im = decodeSmall(small);
  final white = whiteMask(im);
  // 뒷면 비율은 기록용(뒷면 색이 연보라일 때만 의미가 있다). 판정은 손패 칸(울기 모서리 칸 제외)의 앞면 무늬 넓이로 —
  // 자리 구역 전체로 재면 다른 사람의 앞면 울기 무늬가 섞여 1·2등 차가 2배 언저리까지 줄었다(장면 D).
  final colors = {for (final s in Side.values) s: handColors(im, grid.seat(s), pad: 0)};
  final patterns = {for (final s in Side.values) s: tilePatternArea(im, white, grid.handCell(s))};
  final scale = (im.width > im.height ? im.width : im.height) / 1024;
  return ShotAnalysis(iou: 1, faceUp: faceUpByPattern(patterns, scale), handColors: colors, tilePatterns: patterns);
}
