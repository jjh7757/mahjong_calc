// ignore_for_file: avoid_print
// 판 상태 추적 입력 해상도 확인(2026-11-12): make_seq_res.py 시퀀스(f<i>_<해상도>.jpg, 실제 11-07 원본에서 합성:
// 버림 전 → 버림 → 리치봉)를 앱 `_trackFrame` 과 같은 순서로 넣는다 — 입력 해상도가 바뀌면 SceneShiftGate.reset + cameraMoved
// (mount_screen `_trackSrc`), 그다음 SceneShiftGate → cameraMoved → MeldTracker.onFrame → RiverTracker.onFrame(sticksSeen).
// 서버 리치봉 읽기는 "정답대로"(리치봉 프레임부터 [stickSide] 만 true) 2초 뒤 답한 것으로 친다.
//
//   dart run experiments/tracking/replay_res.dart <시퀀스 폴더> <모드> [리치봉 자리=top] [버림 자리=bottom] [hold 초=6] [리치봉 프레임=4]
// 모드: 1020 · 2040 · 4080 · 1020-2040-<프레임> · 2040-1020-<프레임>(그 프레임부터 바뀜)
// 끊김: 환경변수 GAP=<시작초>-<끝초> 면 그 사이 차례는 받기가 끊긴 것으로 — HOLD=1 이면 앱처럼 추적을 쉬고(입력 그대로),
// HOLD=0 이면 고치기 전처럼 그 사이만 1020 으로 바꿔 넣는다.
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/table/corner_change.dart' show tileFracsOf;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/tracker.dart';

void main(List<String> a) {
  final dir = a[0];
  final mode = a[1];
  final stickSide = Side.values.byName(a.length > 2 ? a[2] : 'top');
  final hold = a.length > 4 ? int.parse(a[4]) : 6;
  final stickFrame = a.length > 5 ? int.parse(a[5]) : 4;
  final grid = GridZones.fromJson(jsonDecode(File('$dir/grid.json').readAsStringSync()) as Map<String, dynamic>)!;
  final n = Directory(dir).listSync().where((f) => RegExp(r'f\d+_1020\.jpg$').hasMatch(f.path)).length;

  String resAt(int i) {
    final m = RegExp(r'^(\d+)-(\d+)-(\d+)$').firstMatch(mode);
    if (m == null) return mode;
    return i < int.parse(m.group(3)!) ? m.group(1)! : m.group(2)!;
  }

  final cache = <String, TableFrameStats>{};
  TableFrameStats stats(int i, String r) =>
      cache.putIfAbsent('$i/$r', () => analyzeTableFrame((File('$dir/f${i}_$r.jpg').readAsBytesSync(), grid)));

  final rt = RiverTracker(tileFrac: riverTileFracsOf(grid));
  final mt = MeldTracker(tileFrac: tileFracsOf(grid), config: const TrackerConfig(pixelOnly: true));
  final gate = SceneShiftGate();
  final t0 = DateTime(2026, 11, 12, 14);
  String? src;
  var reads = 0, meldActions = 0, shifts = 0, rebases = 0;
  final total = hold * (n - 1) + 30;
  final gapEnv = Platform.environment['GAP'];
  final gap = gapEnv?.split('-').map(int.parse).toList();
  final holdOn = Platform.environment['HOLD'] != '0';
  var skipped = 0;
  for (var sec = 0; sec <= total; sec += 3) {
    final i = (sec ~/ hold).clamp(0, n - 1);
    var r = resAt(i);
    if (gap != null && sec >= gap[0] && sec < gap[1]) {
      if (holdOn) {
        skipped++;
        continue;
      }
      r = '1020';
    }
    final now = t0.add(Duration(seconds: sec));
    final s = stats(i, r);
    if (src != null && src != r) {
      gate.reset();
      mt.cameraMoved(now);
      rt.cameraMoved(now);
      rebases++;
    }
    src = r;
    if (gate.check(s)) {
      shifts++;
      mt.cameraMoved(now);
      rt.cameraMoved(now);
    }
    meldActions += mt.onFrame(s.corners, now).length;
    for (final act in rt.onFrame(s.rivers, s.strips, now, sticksSeen: s.sticksSeen)) {
      reads++;
      rt.onSticksRead(act.frame, {for (final side in Side.values) side: side == stickSide && i >= stickFrame},
          now.add(const Duration(seconds: 2)));
    }
  }
  print('');
  print('[$mode${gap == null ? '' : ' 끊김 ${gap[0]}~${gap[1]}초 ${holdOn ? '쉼($skipped차례)' : '1020 으로'}'}] $n장 × $hold초 · 해상도 바뀜 $rebases · 장면 이동 $shifts · 울기 읽기 요청 $meldActions · 리치봉 읽기 $reads');
  print('  사건: ${[for (final e in rt.events) '${e.at.difference(t0).inSeconds}s ${e.side.name} ${e.kind}']}');
  print('  버림 수 ${rt.discardCounts.map((k, v) => MapEntry(k.name, v))} · 리치 ${rt.riichi.map((s) => s.name).toList()} · '
      '리치 시점 ${rt.toJson()['riichi_at']}');
}
