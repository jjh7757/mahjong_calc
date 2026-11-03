import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 리치 화료의 탁자 위 표시패 짝을 격자 구역으로 고르기(2026-11-03, metrics 표 1-54).
/// 격자: 선 265/706, 198/790, 리치봉 상자 y 430~621 · x 432~586(10-31 오후 저장 격자). 사진 1000×1000 으로 쳐서 box = 1000 분율.
void main() {
  const grid = GridZones(x1: 265, x2: 706, y1: 198, y2: 790, sticks: NormBox(430, 432, 621, 586));
  Map<String, dynamic> resp(List<List<(String, double, int, int)>> pairs) => {
        'size': [1000, 1000],
        'pairs': [
          for (final p in pairs)
            [
              for (final (code, conf, u, v) in p) {'tile': code, 'conf': conf, 'box': [u - 12, v - 16, 24, 32]},
            ],
        ],
      };
  List<String> codes(List<ReadTile> ts) => [for (final t in ts) t.code];

  test('구역 판정: 자리 띠(선에서 가운데 쪽 40 안까지)·리치봉 상자·강(상자에서 130)·밖', () {
    expect(pairZoneOf(grid, Side.left, (360, 673)), PairZone.outside, reason: '170105 짝: 아래 왼쪽 빈 곳');
    expect(pairZoneOf(grid, Side.top, (675, 460)), PairZone.otherSeat, reason: '165614 짝: 오른쪽 패산 끝 = 오른쪽 자리 띠 안');
    expect(pairZoneOf(grid, Side.right, (675, 460)), PairZone.winnerSeat);
    expect(pairZoneOf(grid, Side.left, (500, 700)), PairZone.river, reason: '아래 강 3줄 안');
    expect(pairZoneOf(grid, Side.left, (500, 500)), PairZone.sticks);
    expect(pairZoneOf(grid, Side.left, (330, 300)), PairZone.outside, reason: '왼쪽 위 패산 자리(가운데 칸 모서리)');
  });

  test('구역 밖 짝이 하나면 그것(확신도 조건 그대로)', () {
    final j = resp([
      [('5p', 0.98, 355, 667), ('5s', 0.98, 368, 687)],
    ]);
    expect(codes(localPairIndicators(j, grid: grid, winner: Side.left)), ['5p', '5s']);
    expect(localPairIndicators(resp([
      [('5p', 0.5, 355, 667), ('5s', 0.98, 368, 687)],
    ]), grid: grid, winner: Side.left), isEmpty);
  });

  test('다른 자리 띠·강의 짝은 쓰지 않는다(181209: 다른 자리 쪽 5s 짝)', () {
    final j = resp([
      [('5s', 0.94, 747, 714), ('5s', 0.93, 760, 714)],
    ]);
    expect(localPairIndicators(j, grid: grid, winner: Side.left), isEmpty);
    expect(localPairIndicators(resp([
      [('2m', 0.9, 500, 700), ('3m', 0.9, 520, 700)],
    ]), grid: grid, winner: Side.left), isEmpty, reason: '강 안');
  });

  test('밖에 없으면 화료자 자리 띠의 짝이 하나일 때만 그것', () {
    final j = resp([
      [('1z', 0.9, 675, 460), ('5z', 0.9, 675, 490)],
    ]);
    expect(codes(localPairIndicators(j, grid: grid, winner: Side.right)), ['1z', '5z']);
    expect(localPairIndicators(j, grid: grid, winner: Side.top), isEmpty);
  });

  test('밖에 여럿이면 판 중 확정한 도라가 든 하나, 없으면 고르지 않는다', () {
    final j = resp([
      [('5p', 0.98, 355, 667), ('5s', 0.98, 368, 687)],
      [('7s', 0.9, 330, 300), ('2m', 0.9, 350, 300)],
    ]);
    expect(localPairIndicators(j, grid: grid, winner: Side.left), isEmpty);
    expect(codes(localPairIndicators(j, grid: grid, winner: Side.left, trackedDora: ReadTile.fromCode('5p', 0.9))), ['5p', '5s']);
    expect(localPairIndicators(j, grid: grid, winner: Side.left, trackedDora: ReadTile.fromCode('9m', 0.9)), isEmpty);
  });

  test('격자나 위치가 없으면 예전 규칙(짝이 하나일 때만)', () {
    final old = {
      'pairs': [
        [
          {'tile': '3p', 'conf': 0.9},
          {'tile': '6z', 'conf': 0.9},
        ],
      ],
    };
    expect(codes(localPairIndicators(old, grid: grid, winner: Side.left)), ['3p', '6z']);
    expect(codes(localPairIndicators(old)), ['3p', '6z']);
  });
}
