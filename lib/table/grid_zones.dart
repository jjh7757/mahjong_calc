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

import 'dart:typed_data';

import 'fixed_layout.dart';
import 'table_layout.dart';

/// 앞면(화료자) 자리는 손패 칸의 앞면 패 무늬 넓이로 정한다([faceUpByPattern]). 처음엔 연보라 뒷면 비율이 먼저였는데
/// (장면 C 는 왼쪽 패산 때문에 그것으로 못 정해 네 자리를 다 읽었다), 다른 색 뒷면에서 무너져 무늬만 쓴다(2026-10-27).

/// 강 끝 크롭: 가운데 칸 한가운데부터 그 자리 쪽 끝까지, 옆으로는 가운데 칸 폭의 이 비율만(가운데 정렬).
/// 칸 폭 전체로 자르면 따로 놓인 도라 표시패가 섞여 모델이 오래 생각하거나(15~36초) 마지막 패를 못 찾았다(장면 D 오른쪽 강).
const double lastZoneBand = 0.6;

/// 리치봉 크롭: 가운데 칸 한가운데에서 이 비율만큼(가운데 기기와 그 둘레).
const double sticksZoneShare = 0.7;

/// 추적용 강 띠가 시작하는 곳(가운데에서 그 자리 쪽 반폭의 비율). 0 = [lastZone] 전체.
/// 격자 가운데 칸의 한가운데가 기기 한가운데와 다를 수 있어(장면 D: 아래쪽은 기기가 반폭의 8%, 오른쪽은 20%) 기기 몫을
/// 떼지 않는다 — 떼면 기기에 붙은 첫 줄을 잃는다. 기기(검정)는 변하지 않으니 띠에 들어 있어도 해가 없다.
const double riverStart = 0.0;

/// 추적용 리치봉 띠: 가운데에서 [stickStart]~[stickEnd](기기 가장자리 홈이 있는 곳). 강 띠와 겹친다.
const double stickStart = 0.0;
const double stickEnd = 0.25;

class GridZones {
  /// 세로선(왼쪽·오른쪽)과 가로선(위·아래), 0~1000.
  final int x1, x2, y1, y2;

  const GridZones({required this.x1, required this.x2, required this.y1, required this.y2});

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
  NormBox stickStrip(Side side, {double start = stickStart, double end = stickEnd, double band = lastZoneBand}) =>
      _alongSide(side, start, end, band);

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

  /// 리치봉을 볼 곳: 가운데 칸 한가운데 [share] 만큼.
  NormBox get sticksZone {
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

  GridZones copyWith({int? x1, int? x2, int? y1, int? y2}) =>
      GridZones(x1: x1 ?? this.x1, x2: x2 ?? this.x2, y1: y1 ?? this.y1, y2: y2 ?? this.y2);

  Map<String, dynamic> toJson() => {'x1': x1, 'x2': x2, 'y1': y1, 'y2': y2};

  /// 예전 저장값의 `panel`(가운데 기기 상자)은 무시한다.
  static GridZones? fromJson(Map<String, dynamic> j) {
    int? n(String k) => (j[k] as num?)?.round();
    final x1 = n('x1'), x2 = n('x2'), y1 = n('y1'), y2 = n('y2');
    if (x1 == null || x2 == null || y1 == null || y2 == null) return null;
    final g = GridZones(x1: x1, x2: x2, y1: y1, y2: y2);
    return g.valid ? g : null;
  }

  @override
  bool operator ==(Object other) =>
      other is GridZones && other.x1 == x1 && other.x2 == x2 && other.y1 == y1 && other.y2 == y2;
  @override
  int get hashCode => Object.hash(x1, x2, y1, y2);
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
