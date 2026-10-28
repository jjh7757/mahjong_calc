// ignore_for_file: avoid_print
// 저장한 헤드 프레임(f00.jpg…, 3초 간격)을 두 추적기에 그대로 넣어, 장면 전체 변화 검사가 있을 때와 없을 때를 같은 프레임으로 비교한다.
// 서버 읽기는 부르지 않고 "패 없음" 으로 답한 것으로 친다(패 없는 장면 측정용 — 실측에서 서버가 전부 그렇게 답함).
//
//   dart run experiments/tracking/replay_track.dart <프레임 폴더>
import 'dart:io';

import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/tracker.dart';

const grid = GridZones.initial;

List<String> frames(String dir) {
  final re = RegExp(r'f(\d+)\.jpg$');
  final fs = Directory(dir).listSync().whereType<File>().map((f) => f.path).where(re.hasMatch).toList()
    ..sort((a, b) => int.parse(re.firstMatch(a)!.group(1)!).compareTo(int.parse(re.firstMatch(b)!.group(1)!)));
  return fs;
}

void main(List<String> args) {
  final paths = frames(args.first);
  final stats = [for (final p in paths) analyzeTableFrame((File(p).readAsBytesSync(), grid))];
  final t0 = DateTime(2026, 10, 28, 13);

  // 프레임마다 바뀐 칸 수(움직였는지 눈으로 보기).
  final g = SceneShiftGate();
  final marks = <String>[];
  for (var i = 0; i < stats.length; i++) {
    final hit = g.check(stats[i]);
    marks.add(hit ? '[${g.lastChanged}/${g.lastCorners}/${g.lastBright}]' : '${g.lastChanged}');
  }
  print('${paths.length}장, 프레임별 바뀐 칸 수([ ] = 장면 변화 판정, 칸/모서리/밝기 강):');
  print(marks.join(' '));

  for (final useGate in [false, true]) {
    final mt = MeldTracker(tileFrac: tileFracsOf(grid));
    final rt = RiverTracker(tileFrac: riverTileFracsOf(grid));
    final gate = SceneShiftGate();
    var corner = 0, sticks = 0, rebases = 0;
    for (var i = 0; i < stats.length; i++) {
      final now = t0.add(Duration(seconds: i * 3));
      if (useGate && gate.check(stats[i])) {
        mt.cameraMoved(now);
        rt.cameraMoved(now);
        rebases++;
      }
      for (final a in mt.onFrame(stats[i].corners, now)) {
        corner++;
        mt.onRead(a.side, a.frame, const [], now.add(const Duration(seconds: 2)));
      }
      for (final a in rt.onFrame(stats[i].rivers, stats[i].strips, now)) {
        sticks++;
        rt.onSticksRead(a.frame, {for (final s in Side.values) s: false}, now.add(const Duration(seconds: 2)));
      }
    }
    final discards = rt.discardCounts;
    print('${useGate ? '검사 있음' : '검사 없음'}: 모서리 읽기 $corner회 · 리치봉 읽기 $sticks회 · 헛 강 버림 '
        '${discards.values.fold(0, (a, b) => a + b)}개 ${discards.map((k, v) => MapEntry(k.name, v))}'
        '${useGate ? ' · 기준 다시 잡기 $rebases번' : ''}');
  }
}
