// ignore_for_file: avoid_print
// 리치 시퀀스 프레임(make_seq2.py: 버림 전 → 손 → 버림 → 안정 → 리치봉 → 안정 → 화료)을 3초 간격으로 강 추적기에 넣어
// 리치봉 확정·리치 시점 수·더블리치·일발 후보를 본다. 서버 리치봉 읽기는 "정답대로" 답한 것으로 친다(리치봉 프레임부터
// [side] 만 true) — 픽셀 쪽(띠 변화 감지·버림 감지·시점 기록)만 재는 것.
//
//   dart run experiments/tracking/replay_riichi.dart <프레임 폴더> <리치 자리 bottom|right> [hold 초, 기본 6] [리치봉 프레임, 기본 4] [sticks=ymin,xmin,ymax,xmax]
// sticks= 를 주면 격자에 리치봉 상자를 둔다(자동 맞추기처럼, 띠가 그 상자 안 30% 띠가 됨). 없으면 GridZones.initial 의 넓은 띠.
import 'dart:io';

import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main(List<String> argv) {
  final grid = gridFrom(argv);
  final args = [for (final a in argv) if (!a.startsWith('sticks=')) a];
  final dir = args[0];
  final side = Side.values.byName(args[1]);
  final hold = args.length > 2 ? int.parse(args[2]) : 6;
  final stickFrame = args.length > 3 ? int.parse(args[3]) : 4;
  final re = RegExp(r'f(\d+)\.jpg$');
  final files = Directory(dir).listSync().whereType<File>().where((f) => re.hasMatch(f.path)).toList()
    ..sort((a, b) => int.parse(re.firstMatch(a.path)!.group(1)!).compareTo(int.parse(re.firstMatch(b.path)!.group(1)!)));
  final stats = [for (final f in files) analyzeTableFrame((f.readAsBytesSync(), grid))];

  final rt = RiverTracker(tileFrac: riverTileFracsOf(grid));
  final gate = SceneShiftGate();
  final t0 = DateTime(2026, 10, 29, 20);
  // 마지막 프레임(화료)은 30초 더 둔다(fake_head --seq 와 같이 마지막은 계속).
  final total = hold * (files.length - 1) + 30;
  var reads = 0;
  for (var sec = 0; sec <= total; sec += 3) {
    final i = (sec ~/ hold).clamp(0, files.length - 1);
    final now = t0.add(Duration(seconds: sec));
    if (gate.check(stats[i])) rt.cameraMoved(now);
    for (final a in rt.onFrame(stats[i].rivers, stats[i].strips, now)) {
      reads++;
      rt.onSticksRead(a.frame, {for (final s in Side.values) s: s == side && i >= stickFrame},
          now.add(const Duration(seconds: 2)));
    }
  }
  print('${files.length}장 × $hold초, 리치봉 읽기 $reads회');
  print('사건: ${[for (final e in rt.events) '${e.at.difference(t0).inSeconds}s ${e.side.name} ${e.kind}${e.kind == 'discard' ? '(${e.detail})' : ''}']}');
  print('버림 수 ${rt.discardCounts.map((k, v) => MapEntry(k.name, v))}, 빈 강 본 자리 '
      '${[for (final e in rt.rivers.entries) if (e.value.seenEmpty) e.key.name]}');
  print('리치 ${rt.riichi.map((s) => s.name).toList()} · 리치 시점 ${rt.toJson()['riichi_at']}');
  print('더블리치 후보 ${rt.doubleRiichiCandidates.map((s) => s.name).toList()} · '
      '일발 후보 ${rt.ippatsuCandidates().map((s) => s.name).toList()}');
}

GridZones gridFrom(List<String> args) {
  final a = args.where((x) => x.startsWith('sticks=')).firstOrNull;
  if (a == null) return GridZones.initial;
  final v = a.substring(7).split(',').map(int.parse).toList();
  return GridZones.initial.copyWith(sticks: NormBox(v[0], v[1], v[2], v[3]));
}
