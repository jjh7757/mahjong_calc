// ignore_for_file: avoid_print
// 11-07 하루 추적 프레임 전부를 픽셀 리치봉 판정 추적기에 넣어, 판(round_key)마다 확정한 리치 자리를 Gemini 읽기와 나란히 본다.
// 헛 리치(Gemini 가 한 번도 안 본 자리를 확정) 찾기용. 판이 바뀌면 추적기를 새로(앱의 reset 과 같음).
//
//   dart run experiments/tracking/scan_local_sticks.dart <풀어 둔 폴더> <captures 폴더>
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/scene_shift.dart';

void main(List<String> argv) {
  final base = Directory(argv[0]);
  final caps = argv[1];
  var rounds = 0, confirmed = 0, notByGemini = 0, frames = 0;
  final dirs = base.listSync().whereType<Directory>().toList()..sort((a, b) => a.path.compareTo(b.path));
  for (final d in dirs) {
    final name = d.path.split(RegExp(r'[\\/]')).last;
    // Gemini 가 이 폴더에서 한 번이라도 본 자리.
    final gem = <String>{};
    final cdir = Directory('$caps/$name');
    if (cdir.existsSync()) {
      for (final f in cdir.listSync().whereType<File>().where((f) => RegExp(r'sticks_\d+\.json$').hasMatch(f.path))) {
        final r = (jsonDecode(f.readAsStringSync())['read']['riichi_sticks'] as Map);
        gem.addAll([for (final e in r.entries) if (e.value == true) e.key as String]);
      }
    }
    final parts = d.listSync().whereType<Directory>().map((x) => x.path).toList()..sort();
    final byRound = <String, List<(DateTime, String, GridZones)>>{};
    for (final p in parts) {
      final j = jsonDecode(File('$p/frames.json').readAsStringSync()) as Map<String, dynamic>;
      final g = GridZones.fromJson(j['grid'] as Map<String, dynamic>)!;
      for (final f in j['frames'] as List) {
        byRound.putIfAbsent(j['round_key'] as String, () => []).add((DateTime.parse(f['at'] as String), '$p/${f['file']}', g));
      }
    }
    for (final e in byRound.entries) {
      final fs = e.value..sort((a, b) => a.$1.compareTo(b.$1));
      final g = fs.first.$3;
      if (g.sticks == null) {
        print('$name ${e.key}: 리치봉 상자 없음(픽셀 판정 안 함)');
        continue;
      }
      final rt = RiverTracker(tileFrac: riverTileFracsOf(g));
      final gate = SceneShiftGate();
      final seenOnce = <String>{};
      for (final (t, path, _) in fs) {
        final st = analyzeTableFrame((File(path).readAsBytesSync(), g));
        frames++;
        if (gate.check(st)) rt.cameraMoved(t);
        rt.onFrame(st.rivers, st.strips, t, sticksSeen: st.sticksSeen);
        seenOnce.addAll([for (final x in st.sticksSeen.entries) if (x.value) x.key.name]);
      }
      rounds++;
      final got = rt.riichi.map((s) => s.name).toSet();
      confirmed += got.length;
      final extra = got.difference(gem);
      notByGemini += extra.length;
      final conf = [
        for (final ev in rt.events)
          if (ev.kind == 'sticks_confirmed') '${ev.side.name}@${ev.at.toIso8601String().substring(11, 19)}',
      ];
      print('$name ${e.key} 프레임 ${fs.length}: 확정 $conf · 한 번이라도 본 $seenOnce · Gemini 본 자리 $gem${extra.isEmpty ? '' : ' ← Gemini 안 본 확정 $extra'}');
    }
  }
  print('판 $rounds · 프레임 $frames · 확정 $confirmed · 그중 Gemini 가 그 폴더에서 안 본 자리 $notByGemini');
}
