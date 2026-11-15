// 헤드 1:1 일 때 추적(2026-11-13): 표 12-9 의 11-07 14장을 4:3(1020 건너뛰기·2040 평균)과 1:1(997 건너뛰기·1496 평균, mk_sq_frames.py)로
// analyzeTableFrame 에 넣어 리치봉 홈 판정을 정답(stick_truth.json)과 대고, 강·모서리 흰 면(패 장수)을 4:3 ↔ 1:1 짝끼리 견준다.
//   flutter test experiments/speed/sq_track_test.dart   → experiments/speed/results/res_frames_1107_sq/compare.json
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/corner_change.dart' show tileFracsOf;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/table_layout.dart' show Side;

void main() {
  test('1:1 추적 통계', () {
    const a = 'experiments/speed/results/res_frames_1107', b = 'experiments/speed/results/res_frames_1107_sq';
    final ga = jsonDecode(File('$a/grids.json').readAsStringSync()) as Map<String, dynamic>;
    final gb = jsonDecode(File('$b/grids.json').readAsStringSync()) as Map<String, dynamic>;
    final truth = jsonDecode(File('$a/stick_truth.json').readAsStringSync()) as Map<String, dynamic>;
    const sets = {'1020': a, '2040': a, '997': b, '1496': b};
    final rows = <Map<String, dynamic>>[];
    final ok = {for (final r in sets.keys) r: 0}, hit = {for (final r in sets.keys) r: 0}, fp = {for (final r in sets.keys) r: 0};
    final times = {for (final r in sets.keys) r: <int>[]};
    var nStick = 0, nSlot = 0;
    for (final k in ga.keys) {
      final want = {for (final s in (truth[k] as List)) s as String};
      final st = <String, TableFrameStats>{};
      final grids = <String, GridZones>{};
      for (final r in sets.keys) {
        final grid = GridZones.fromJson((sets[r] == a ? ga : gb)[k] as Map<String, dynamic>)!;
        grids[r] = grid;
        final bytes = File('${sets[r]}/${k}_$r.jpg').readAsBytesSync();
        analyzeTableFrame((bytes, grid));
        final sw = Stopwatch()..start();
        st[r] = analyzeTableFrame((bytes, grid));
        times[r]!.add(sw.elapsedMilliseconds);
        for (final s in Side.values) {
          final seen = st[r]!.sticksSeen[s] == true, w = want.contains(s.name);
          if (seen == w) ok[r] = ok[r]! + 1;
          if (seen && w) hit[r] = hit[r]! + 1;
          if (seen && !w) fp[r] = fp[r]! + 1;
        }
      }
      nStick += want.length;
      nSlot += 4;
      Map<String, dynamic> cmp(String x, String y) {
        final ax = x == '1020' || x == '2040' ? 4 / 3 : 1.0, ay = y == '1020' || y == '2040' ? 4 / 3 : 1.0;
        final cx = tileFracsOf(grids[x]!, aspect: ax), cy = tileFracsOf(grids[y]!, aspect: ay);
        final rx = riverTileFracsOf(grids[x]!, aspect: ax), ry = riverTileFracsOf(grids[y]!, aspect: ay);
        return {
          for (final s in Side.values)
            s.name: {
              'river_tiles': [st[x]!.rivers[s]!.tiles(rx[s]!), st[y]!.rivers[s]!.tiles(ry[s]!)],
              'corner_tiles': [st[x]!.corners[s]!.white / cx[s]!, st[y]!.corners[s]!.white / cy[s]!],
            },
        };
      }
      rows.add({
        'key': k,
        'truth': want.toList(),
        'sticks': {for (final r in sets.keys) r: [for (final e in st[r]!.sticksSeen.entries) if (e.value) e.key.name]},
        '1020_vs_997': cmp('1020', '997'),
        '2040_vs_1496': cmp('2040', '1496'),
      });
    }
    final out = {'slots': nSlot, 'sticks': nStick, 'ok': ok, 'hit': hit, 'fp': fp, 'times_ms': times, 'rows': rows};
    File('$b/compare.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
    // ignore: avoid_print
    print('slots $nSlot sticks $nStick ok $ok hit $hit fp $fp');
  }, timeout: const Timeout(Duration(minutes: 20)));
}
