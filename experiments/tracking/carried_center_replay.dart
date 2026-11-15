// ignore_for_file: avoid_print
// 유국 공탁을 가운데로 모은 뒤 다음 판 새 리치를 앱 추적기가 잡나 — 실제 프레임 재생(2026-11-13, 사용자 "니가 직접 테스트 해볼래?").
// 10-31 `20261031_170310_track` frames_01: 17:04~17:07 위 홈에 봉 → 17:07:31 부터 그 봉이 주사위 창 위(가운데)로 →
// 17:09:31 부터 왼쪽 홈에 새 봉 → 17:11 왼쪽 화료 촬영(171025). 앱처럼 판이 바뀐 때(가운데로 옮긴 직후) 추적기를 새로 만들고
// analyzeTableFrame(프레임, 격자) → RiverTracker.onFrame(sticksSeen:) 을 그대로 돌린다.
//   dart run experiments/tracking/carried_center_replay.dart [시작 프레임 번호=37]
// 결과(11-13): 37 → 리치 {left}·넘김 {left} / 30(봉 옮기기 전 유국 기록) → 리치 {top, left}·넘김 {left}(riichiExcept 덕)
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main(List<String> args) {
  final start = args.isNotEmpty ? int.parse(args[0]) : 37;
  const zip = 'experiments/visit_20261031/captures/20261031_170310_track/frames_01.zip';
  final a = ZipDecoder().decodeBytes(File(zip).readAsBytesSync());
  final j = jsonDecode(utf8.decode(a.findFile('frames.json')!.content as List<int>)) as Map<String, dynamic>;
  final grid = GridZones.fromJson(j['grid'] as Map<String, dynamic>)!;
  final tr = RiverTracker(tileFrac: riverTileFracsOf(grid));
  var n = 0;
  Set<String>? last;
  for (final f in j['frames'] as List) {
    final name = f['file'] as String;
    if (int.parse(name.substring(1, 5)) < start) continue;
    final jpeg = Uint8List.fromList(a.findFile(name)!.content as List<int>);
    final st = analyzeTableFrame((jpeg, grid));
    final now = DateTime.parse(f['at'] as String);
    tr.onFrame(st.rivers, st.strips, now, sticksSeen: st.sticksSeen);
    n++;
    final r = {for (final s in tr.riichi) s.name};
    if (last == null || r.length != last.length || !r.containsAll(last)) {
      print('${name.substring(0, 5)} ${f['at'].toString().substring(11, 19)} 홈 판정 ${[for (final e in st.sticksSeen.entries) if (e.value) e.key.name]} → 추적 리치 $r');
      last = r;
    }
  }
  print('프레임 $n장, 최종 리치 ${[for (final s in tr.riichi) s.name]}, 리치 시점 ${[for (final s in tr.riichiAt.keys) s.name]}');
  // 앱이 화료 판독·유국 창에 넘기는 값: 전판 봉 주인(위)을 시점 없으면 뺀다(mount_screen _trackedRiichi).
  print('앱이 넘기는 추적 리치(전판 봉 주인 = 위) ${[for (final s in tr.riichiExcept({Side.top})) s.name]}');
}
