// 추적 입력 해상도 비교(2026-11-12): 같은 장면의 1020(건너뛰어 줄임, 헤드 /preview)·2040(2×2 평균, 헤드 녹화)·4080(원본)으로
// analyzeTableFrame 을 돌려 값 차이와 시간을 잰다. 입력은 `mk_res_frames.py` 가 만든 폴더(<키>_<해상도>.jpg + grids.json).
//
//   RES_DIR=experiments/speed/results/res_frames_1107 flutter test experiments/speed/res_compare_test.dart
//
// 결과는 RES_DIR/compare.json. 문턱값과 견준다: 모서리·강 diff 0.03(moveThreshold), 흰 면 변화 0.6장(discardTiles)·1장(changeTiles).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/corner_change.dart' show tileFracsOf;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/table_layout.dart' show Side;

void main() {
  test('해상도별 추적 통계 비교', () async {
    final dir = Platform.environment['RES_DIR'] ?? 'experiments/speed/results/res_frames_1107';
    final grids = (jsonDecode(File('$dir/grids.json').readAsStringSync()) as Map<String, dynamic>);
    const res = ['1020', '2040', '4080'];
    final rows = <Map<String, dynamic>>[];
    final times = {for (final r in res) r: <int>[]};
    for (final e in grids.entries) {
      final grid = GridZones.fromJson(e.value as Map<String, dynamic>)!;
      final stats = <String, TableFrameStats>{};
      for (final r in res) {
        final bytes = File('$dir/${e.key}_$r.jpg').readAsBytesSync();
        // 처음 한 번은 버리고 세 번 잰다.
        analyzeTableFrame((bytes, grid));
        for (var i = 0; i < 3; i++) {
          final sw = Stopwatch()..start();
          stats[r] = analyzeTableFrame((bytes, grid));
          times[r]!.add(sw.elapsedMilliseconds);
        }
      }
      final cf = tileFracsOf(grid);
      final rf = riverTileFracsOf(grid);
      Map<String, dynamic> cmp(String a, String b) {
        final x = stats[a]!, y = stats[b]!;
        return {
          for (final s in Side.values)
            s.name: {
              'corner_diff': x.corners[s]!.diff(y.corners[s]!),
              'corner_white_tiles': (x.corners[s]!.white - y.corners[s]!.white).abs() / cf[s]!,
              'river_shape_same': x.rivers[s]!.cols == y.rivers[s]!.cols && x.rivers[s]!.rows == y.rivers[s]!.rows,
              'river_diff': x.rivers[s]!.diff(y.rivers[s]!),
              'river_white_tiles': (x.rivers[s]!.whiteFrac - y.rivers[s]!.whiteFrac).abs() / rf[s]!,
              'river_tiles': [x.rivers[s]!.tiles(rf[s]!), y.rivers[s]!.tiles(rf[s]!)],
              'strip_diff': x.strips[s]!.diff(y.strips[s]!),
              'stick_same': x.sticksSeen[s] == y.sticksSeen[s],
            },
        };
      }
      rows.add({'key': e.key, 'sticks': {for (final r in res) r: {for (final kv in stats[r]!.sticksSeen.entries) kv.key.name: kv.value}}, '1020_vs_2040': cmp('1020', '2040'), '1020_vs_4080': cmp('1020', '4080'), '2040_vs_4080': cmp('2040', '4080')});
    }
    final out = {'times_ms': times, 'rows': rows};
    File('$dir/compare.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
