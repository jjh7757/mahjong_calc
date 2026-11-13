import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 기기 판독 `localsetup` 응답 → 격자([gridFromLocalSetup], 서버 없는 자동 맞추기).
void main() {
  const keep = GridZones(x1: 280, x2: 745, y1: 173, y2: 713, sticks: NormBox(400, 450, 600, 550));

  test('격자·리치봉 상자를 받는다, 도라 구역 모양은 지금 것', () {
    final g = gridFromLocalSetup({
      'grid': {'x1': 300, 'x2': 720, 'y1': 190, 'y2': 700, 'sticks': [410, 460, 590, 540]},
    }, keep: keep)!;
    expect([g.x1, g.x2, g.y1, g.y2], [300, 720, 190, 700]);
    expect(g.sticks, const NormBox(410, 460, 590, 540));
    expect(g.doraRel, keep.doraRel);
  });

  test('리치봉 상자가 없으면 지금 것', () {
    final g = gridFromLocalSetup({'grid': {'x1': 300, 'x2': 720, 'y1': 190, 'y2': 700}}, keep: keep)!;
    expect(g.sticks, keep.sticks);
  });

  test('기준점을 못 잡았거나 선이 엇갈리면 null', () {
    expect(gridFromLocalSetup({'grid': null, 'frame_error': '기기·패산 못 찾음'}, keep: keep), isNull);
    expect(gridFromLocalSetup({'grid': {'x1': 700, 'x2': 300, 'y1': 190, 'y2': 700}}, keep: keep), isNull);
  });
}
