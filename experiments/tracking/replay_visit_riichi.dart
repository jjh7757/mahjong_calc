// ignore_for_file: avoid_print
// 11-07 매장 실제 대국 2차(카메라 180° 돌려 다시 거치)의 배경 프레임을 강 추적기에 실제 시각대로 다시 넣어 리치 추적을 잰다.
// 앱 흐름(mount_screen `_trackFrame`)과 같은 순서: SceneShiftGate → cameraMoved → onFrame → 읽기 요청.
// 서버 `/v2/sticks` 는 부르지 않고 "정답대로" 답한 것으로 친다: 그 판의 리치 자리는 실제 첫 양성 읽기 요청 시각(T) 부터
// true, 그 전엔 전부 false(실측 11-07 읽기 30회가 모두 이 정답과 같았음). 답은 요청 [latency]초 뒤 첫 프레임에 도착한다
// (실측 `/v2/sticks` 6.7~10초). 화료 사진 시각까지 [RiverTracker.riichi] 에 그 자리가 들어갔는지를 본다.
//
//   dart run experiments/tracking/replay_visit_riichi.dart <풀어 둔 폴더> [latency 초=8] [confirm 읽기 수=2]
// <풀어 둔 폴더>/<판 폴더>/frames_##/{frames.json,f####_hhmmss.jpg} — captures/*_track/frames_##.zip 을 그대로 푼 것.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 판 폴더, 리치 자리(아래 = bottom_seat 3 기준), 첫 양성 읽기 요청 시각, 화료 사진 시각.
const rounds = [
  ('20261107_153128_track', '동2국 153311', Side.right, '15:32:33', '15:33:11'),
  ('20261107_153423_track', '동3국 153939', Side.bottom, '15:38:52', '15:39:39'),
  ('20261107_154029_track', '동4국 154417', Side.top, '15:44:01', '15:44:17'),
  ('20261107_155125_track', '남1국 155553', Side.left, '15:55:34', '15:55:53'),
];

DateTime at(String hms) {
  final p = hms.split(':').map(int.parse).toList();
  return DateTime(2026, 11, 7, p[0], p[1], p[2]);
}

void main(List<String> argv) {
  final base = argv[0];
  final latency = Duration(seconds: argv.length > 1 ? int.parse(argv[1]) : 8);
  final confirm = argv.length > 2 ? int.parse(argv[2]) : 2;
  // 4번째 인자 local = 픽셀 판정(서버 읽기 없음), 그 밖은 Gemini 읽기 흉내.
  final local = argv.length > 3 && argv[3] == 'local';
  var ok = 0;
  for (final (dir, name, side, firstTrue, winAt) in rounds) {
    final parts = Directory('$base/$dir').listSync().whereType<Directory>().map((d) => d.path).toList()..sort();
    final frames = <(DateTime, String)>[];
    GridZones? grid;
    for (final p in parts) {
      final j = jsonDecode(File('$p/frames.json').readAsStringSync()) as Map<String, dynamic>;
      grid ??= GridZones.fromJson(j['grid'] as Map<String, dynamic>);
      for (final f in j['frames'] as List) {
        frames.add((DateTime.parse(f['at'] as String), '$p/${f['file']}'));
      }
    }
    frames.sort((a, b) => a.$1.compareTo(b.$1));
    final g = grid!;
    final rt = RiverTracker(tileFrac: riverTileFracsOf(g), config: RiverTrackerConfig(stickConfirmReads: confirm));
    final gate = SceneShiftGate();
    final t1 = at(firstTrue), win = at(winAt);
    final pending = <(int, DateTime, DateTime)>[]; // (frame, 요청 시각, 도착 시각)
    var reads = 0, shifts = 0;
    DateTime? confirmedAt;
    for (final (t, path) in frames) {
      if (t.isAfter(win)) break;
      // 이 프레임 전에 도착한 답을 먼저 넣는다.
      for (final r in [...pending]) {
        if (!r.$3.isAfter(t)) {
          pending.remove(r);
          rt.onSticksRead(r.$1, {for (final s in Side.values) s: s == side && !r.$2.isBefore(t1)}, r.$3);
        }
      }
      final stats = analyzeTableFrame((File(path).readAsBytesSync(), g));
      if (gate.check(stats)) {
        shifts++;
        rt.cameraMoved(t);
      }
      for (final a in rt.onFrame(stats.rivers, stats.strips, t, sticksSeen: local ? stats.sticksSeen : null)) {
        reads++;
        pending.add((a.frame, t, t.add(latency)));
      }
      if (confirmedAt == null && rt.riichi.contains(side)) confirmedAt = t;
    }
    // 화료 사진 직전에 도착하는 답까지.
    for (final r in pending) {
      if (!r.$3.isAfter(win)) rt.onSticksRead(r.$1, {for (final s in Side.values) s: s == side && !r.$2.isBefore(t1)}, r.$3);
    }
    confirmedAt ??= rt.riichi.contains(side) ? win : null;
    final hit = rt.riichi.contains(side) && rt.riichi.length == 1;
    if (hit) ok++;
    final ra = rt.riichiAt[side];
    print('$name ${side.name}: 프레임 ${frames.length}·장면 변화 $shifts·읽기 $reads → 리치 ${rt.riichi.map((s) => s.name).toList()} '
        '${hit ? '✓' : '✗'}${confirmedAt != null ? ' (확정 +${confirmedAt.difference(t1).inSeconds}초)' : ''}'
        '${ra != null ? ' 시점 자기 ${ra.own}·전체 ${ra.total}' : ''}');
    final ev = [
      for (final e in rt.events)
        if (e.kind.startsWith('sticks') || e.kind == 'rebase') '${e.at.toIso8601String().substring(11, 19)} ${e.side.name} ${e.kind}${e.detail.isEmpty || e.kind == 'rebase' ? '' : '(${e.detail})'}',
    ];
    print('   ${ev.where((e) => !e.endsWith('rebase')).join(' | ')}');
  }
  print('리치 추적 $ok/${rounds.length} (${local ? '픽셀 판정' : 'latency ${latency.inSeconds}s, 확정 읽기 $confirm'})');
}
