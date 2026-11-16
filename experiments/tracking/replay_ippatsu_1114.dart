// ignore_for_file: avoid_print
// 11-14 2반장 동4국 1본장(13:39 화료, 플레이어 3 리치 → 일발 쯔모)에서 일발이 빠진 원인 확인(2026-11-16).
// 추적 폴더의 frames_*.zip 을 앱 흐름(mount_screen `_trackFrame`: SceneShiftGate → cameraMoved → 울기·강 추적기)대로 다시 넣고
// 화료 시각의 리치·리치 시점·일발 후보를 찍는다. 격자는 (가) 그날 저장돼 있던 것 (나) 기기에 맞게 옮긴 것 둘 다.
//   dart run experiments/tracking/replay_ippatsu_1114.dart <추적 폴더> <화료 시각 hh:mm:ss> [dx dy]
// dx dy = (나) 격자를 (가)에서 옮길 양(0~1000 좌표, 기본 -70 60 — 13:38 프레임에서 기기가 상자보다 왼쪽 아래).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/tracker.dart';

void main(List<String> a) {
  final dir = a[0], win = a[1];
  final dx = a.length > 3 ? int.parse(a[2]) : -70, dy = a.length > 3 ? int.parse(a[3]) : 60;
  final zips = Directory(dir).listSync().whereType<File>().where((f) => RegExp(r'frames_\d+\.zip$').hasMatch(f.path)).toList()
    ..sort((x, y) => x.path.compareTo(y.path));
  final frames = <(DateTime, Uint8List)>[];
  GridZones? saved;
  for (final z in zips) {
    final ar = ZipDecoder().decodeBytes(z.readAsBytesSync());
    final j = jsonDecode(utf8.decode(ar.findFile('frames.json')!.content as List<int>)) as Map<String, dynamic>;
    saved ??= GridZones.fromJson(j['grid'] as Map<String, dynamic>);
    for (final f in j['frames'] as List) {
      final file = ar.findFile(f['file'] as String);
      if (file == null) continue;
      frames.add((DateTime.parse(f['at'] as String), Uint8List.fromList(file.content as List<int>)));
    }
  }
  frames.sort((x, y) => x.$1.compareTo(y.$1));
  final g0 = saved!;
  final s = g0.sticks!;
  final g1 = GridZones(
    x1: g0.x1 + dx,
    x2: g0.x2 + dx,
    y1: g0.y1 + dy,
    y2: g0.y2 + dy,
    doraRel: g0.doraRel,
    sticks: NormBox(s.ymin + dy, s.xmin + dx, s.ymax + dy, s.xmax + dx),
  );
  for (final (name, g) in [('(가) 저장 격자', g0), ('(나) 기기에 맞춘 격자', g1)]) {
    // 헤드 1:1 프레임(정사각) → aspect 1.
    final rt = RiverTracker(tileFrac: riverTileFracsOf(g, aspect: 1));
    final mt = MeldTracker(tileFrac: tileFracsOf(g, aspect: 1), config: const TrackerConfig(pixelOnly: true));
    final gate = SceneShiftGate();
    final seenBy = <String>[];
    for (final (t, jpg) in frames) {
      final hms = t.toIso8601String().substring(11, 19);
      if (hms.compareTo(win) > 0) break;
      final stats = analyzeTableFrame((jpg, g));
      if (gate.check(stats)) {
        mt.cameraMoved(t);
        rt.cameraMoved(t);
      }
      mt.onFrame(stats.corners, t);
      rt.onFrame(stats.rivers, stats.strips, t, sticksSeen: stats.sticksSeen);
      final on = [for (final e in stats.sticksSeen.entries) if (e.value) e.key.name];
      if (on.isNotEmpty) seenBy.add('$hms ${on.join('+')}');
    }
    print('== $name: 선 ${g.x1} ${g.x2} ${g.y1} ${g.y2} · 리치봉 상자 ${g.sticks!.toList()}');
    print('   프레임별 봉 보임: ${seenBy.isEmpty ? '없음' : seenBy.join(' | ')}');
    print('   리치 ${rt.riichi.map((x) => x.name).toList()} · 시점 ${{
      for (final e in rt.riichiAt.entries) e.key.name: '자기 ${e.value.own}·전체 ${e.value.total}·가져감 ${e.value.taken} @${e.value.at.toIso8601String().substring(11, 19)}'
    }}');
    print('   버림 수 ${{for (final e in rt.discardCounts.entries) e.key.name: e.value}}');
    print('   일발 후보(강만) ${rt.ippatsuCandidates().map((x) => x.name).toList()} · '
        '(울기 추적 포함) ${rt.ippatsuCandidates(meldGrewSince: (t, s) => mt.grewSince(t)).map((x) => x.name).toList()}');
    final ev = [
      for (final e in rt.events)
        if (e.kind != 'rebase' && e.at.toIso8601String().substring(11, 19).compareTo('13:38:00') >= 0)
          '${e.at.toIso8601String().substring(11, 19)} ${e.side.name} ${e.kind} ${e.detail}',
    ];
    print('   13:38 뒤 강 사건: ${ev.join(' | ')}');
    final mev = [
      for (final e in mt.events)
        if (e.kind != 'rebase' && e.at.toIso8601String().substring(11, 19).compareTo('13:38:00') >= 0)
          '${e.at.toIso8601String().substring(11, 19)} ${e.side.name} ${e.kind} ${e.detail}',
    ];
    print('   13:38 뒤 울기 사건: ${mev.join(' | ')}');
    print('   울기 늘어난 시각(grewAt): ${{for (final e in mt.seats.entries) e.key.name: e.value.grewAt?.toIso8601String().substring(11, 19)}}');
  }
}
