// ignore_for_file: avoid_print
// 추적 폴더(frames_*.zip)의 프레임마다 모서리 칸 통계·장면 변화·펠트 위치를 뽑아 JSON 으로 남긴다(2026-11-16).
// 울기 픽셀 추적(`MeldTracker` pixelOnly)의 "울기 늘어남" 헛잡음과 카메라 이동 뒤 격자 어긋남을 프레임을 다시 풀지 않고 따져 보려는 것.
//   dart run experiments/tracking/corner_series.dart <out.json> <dx> <dy> <felt 0|1> <추적 폴더>...
// dx dy = 저장 격자를 옮길 양(0~1000). 11-14 2반장은 -70 60(카메라가 옮겨진 뒤 옛 격자), 그 밖은 0 0.
// felt 1 이면 프레임마다 펠트 네 모서리와 그것으로 만든 격자도 적는다.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main(List<String> a) {
  final out = a[0];
  final dx = int.parse(a[1]), dy = int.parse(a[2]);
  final withFelt = a[3] == '1';
  final result = <String, Object?>{};
  for (final dir in a.skip(4)) {
    final zips = Directory(dir).listSync().whereType<File>().where((f) => RegExp(r'frames_\d+\.zip$').hasMatch(f.path)).toList()
      ..sort((x, y) => x.path.compareTo(y.path));
    GridZones? g;
    Map<String, dynamic>? savedGrid;
    final gate = SceneShiftGate();
    final rows = <Map<String, Object?>>[];
    for (final z in zips) {
      final ar = ZipDecoder().decodeBytes(z.readAsBytesSync());
      final j = jsonDecode(utf8.decode(ar.findFile('frames.json')!.content as List<int>)) as Map<String, dynamic>;
      if (g == null) {
        savedGrid = j['grid'] as Map<String, dynamic>;
        final g0 = GridZones.fromJson(savedGrid)!;
        final s = g0.sticks;
        g = GridZones(
          x1: g0.x1 + dx,
          x2: g0.x2 + dx,
          y1: g0.y1 + dy,
          y2: g0.y2 + dy,
          doraRel: g0.doraRel,
          sticks: s == null ? null : NormBox(s.ymin + dy, s.xmin + dx, s.ymax + dy, s.xmax + dx),
        );
      }
      for (final f in j['frames'] as List) {
        final file = ar.findFile(f['file'] as String);
        if (file == null) continue;
        final jpg = Uint8List.fromList(file.content as List<int>);
        final stats = analyzeTableFrame((jpg, g));
        final row = <String, Object?>{
          't': f['at'],
          'i': f['index'],
          'shift': gate.check(stats),
          'c': {
            for (final e in stats.corners.entries)
              e.key.name: [e.value.white, e.value.pattern, e.value.cx, e.value.cy],
          },
          'sticks': [for (final e in stats.sticksSeen.entries) if (e.value) e.key.name],
        };
        if (withFelt) {
          final q = feltQuadOfJpeg(jpg);
          row['felt'] = q?.toJson();
          row['felt_grid'] = q == null ? null : gridFromFelt(q)?.toJson();
        }
        rows.add(row);
      }
    }
    if (g == null) continue;
    final name = Directory(dir).uri.pathSegments.where((s) => s.isNotEmpty).last;
    result[name] = {
      'saved_grid': savedGrid,
      'grid': g.toJson(),
      'tile_frac': {for (final e in tileFracsOf(g, aspect: 1).entries) e.key.name: e.value},
      'frames': rows,
    };
    stderr.writeln('$name ${rows.length}');
    File(out).writeAsStringSync(jsonEncode(result));
  }
}
