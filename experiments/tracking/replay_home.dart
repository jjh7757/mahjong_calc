// ignore_for_file: avoid_print
// 앱이 남긴 추적 프레임 묶음(frames_##.zip 을 푼 폴더: f####_HHMMSS.jpg + frames.json)을 실제 시각·격자 그대로
// 울기 추적기에 넣어, 헛 변화 미루기(TrackerConfig.idleBackoffMax)가 없을 때와 있을 때 모서리 읽기 수를 비교한다.
// 서버 읽기는 "울기 없음" 으로 답한 것으로 친다(패 없는 장면 — 실측에서 서버가 전부 그렇게 답함).
// 묶음은 변화 주변과 10장마다 한 장만 남아 있어 앱이 본 프레임 전부는 아니다(수는 어림).
//
//   dart run experiments/tracking/replay_home.dart <푼 폴더>
import 'dart:convert';
import 'dart:io';

import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/scene_shift.dart';
import 'package:mahjong_calc/table/tracker.dart';

void main(List<String> args) {
  final dir = args.first;
  final meta = jsonDecode(File('$dir/frames.json').readAsStringSync()) as Map<String, dynamic>;
  final grid = GridZones.fromJson(meta['grid'] as Map<String, dynamic>) ?? GridZones.initial;
  final frames = [
    for (final f in meta['frames'] as List)
      (at: DateTime.parse(f['at'] as String), path: '$dir/${f['file']}'),
  ]..sort((a, b) => a.at.compareTo(b.at));
  final stats = [for (final f in frames) analyzeTableFrame((File(f.path).readAsBytesSync(), grid))];
  print('${frames.length}장 ${frames.first.at.toIso8601String().substring(11, 19)}~'
      '${frames.last.at.toIso8601String().substring(11, 19)}');

  for (final backoff in [Duration.zero, const TrackerConfig().idleBackoffMax]) {
    final mt = MeldTracker(tileFrac: tileFracsOf(grid), config: TrackerConfig(idleBackoffMax: backoff));
    final gate = SceneShiftGate();
    final reads = <String>[];
    for (var i = 0; i < stats.length; i++) {
      final now = frames[i].at;
      if (gate.check(stats[i])) mt.cameraMoved(now);
      for (final a in mt.onFrame(stats[i].corners, now)) {
        reads.add('${now.toIso8601String().substring(11, 19)} ${a.side.name}');
        mt.onRead(a.side, a.frame, const [], now.add(const Duration(seconds: 4)));
      }
    }
    print('${backoff == Duration.zero ? '미루기 없음(전)' : '미루기 최대 ${backoff.inSeconds}초(후)'}: 모서리 읽기 ${reads.length}회');
    print('  ${reads.join(', ')}');
  }
}
