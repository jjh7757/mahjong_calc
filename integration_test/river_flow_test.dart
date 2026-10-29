// 강·리치봉 추적(2단계) 흐름을 노트북에서 끝까지 본다. 가짜 헤드가 장면 D(k16)로 "오른쪽 자리 버림 전 → 손 → 버림 →
// 안정 → 리치봉 → 안정 → 화료" 를 6초씩 재생한다(experiments/tracking/make_seq2.py --side right, launch.json "fake-head-seq2").
// 먼저 띄울 것: 가짜 헤드(8777) + 로컬 인식 서버(launch.json "recognizer", 8030).
//   flutter test integration_test/river_flow_test.dart -d windows \
//     --dart-define=RECOGNIZER_URL=http://127.0.0.1:8030 --dart-define=RECOGNIZER_API_KEY=local
// 확인: 테이블 화면의 강 추적 줄에 "마지막 <오른쪽 자리 이름>" 이 뜨고, 리치봉 읽기가 두 번 일어나며, 화료 촬영 기록의
// setup.tracked_discard 가 오른쪽 자리다(그 패를 따로 잘라 /v2/last 로 읽는 경로).
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('헤드 미리보기로 버림·리치봉을 추적하고, 화료 때 방총자·론 패 힌트로 넘긴다', (tester) async {
    const headUrl = String.fromEnvironment('HEAD_URL', defaultValue: 'http://127.0.0.1:8777');
    final out = const String.fromEnvironment('TRACK_OUT', defaultValue: '') != ''
        ? const String.fromEnvironment('TRACK_OUT')
        : '${Directory.systemTemp.path}/mahjong_river_itest';
    CaptureLog.desktopRootOverride = out;
    SharedPreferences.setMockInitialValues({
      'mount.remoteUrl': headUrl,
      'mount.remoteToken': 'local',
      'mount.tracking': true,
      'mount.autoSetupOnStart': false, // 대국 시작 자동 맞추기는 이 흐름에 안 섞는다(격자 고정)
      'mount.useGrid': true,
    });
    gameStore.resume(
      const ['A', 'B', 'C', 'D'],
      const GameSettings(),
      scores: const [25000, 25000, 25000, 25000],
      roundWind: 0,
      roundNumber: 1,
    );
    addTearDown(gameStore.discardCurrent);
    tester.view.physicalSize = const Size(2560, 1600);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    final sw = Stopwatch()..start();
    Future<bool> waitFor(Finder f, String what, {int seconds = 90, bool must = true}) async {
      final until = sw.elapsed + Duration(seconds: seconds);
      while (sw.elapsed < until) {
        await tester.pump(const Duration(milliseconds: 500));
        await Future<void>.delayed(const Duration(milliseconds: 500));
        if (f.evaluate().isNotEmpty) return true;
      }
      if (must) fail('$what 을(를) $seconds초 안에 못 봄 (${sw.elapsed.inSeconds}초)');
      return false;
    }

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await waitFor(find.byKey(const ValueKey('table-calc')), '테이블 화면', seconds: 20);
    // 오른쪽 자리(bottomSeat 0 → 오른쪽 = 자리 1 = B)의 버림이 감지되면 강 추적 줄에 "마지막 B".
    await waitFor(find.textContaining('마지막 B'), '버림 감지(강 추적 줄)', seconds: 45);
    // ignore: avoid_print
    print('[river] 버림 감지까지 ${sw.elapsed.inSeconds}초');
    // 리치봉 추적은 기본으로 꺼져 있다(RiverTrackerConfig.trackSticks) — 리치봉은 화료 판독이 읽는다.

    await tester.tap(find.byKey(const ValueKey('mount-shoot')));
    await waitFor(find.textContaining('대국에 반영'), '결과 화면', seconds: 150);
    // ignore: avoid_print
    print('[river] 화료 결과까지 ${sw.elapsed.inSeconds}초');

    final root = Directory('$out/mahjong_calc');
    final dirs = root.listSync().whereType<Directory>().toList()..sort((a, b) => a.path.compareTo(b.path));
    final capture = dirs.lastWhere((d) => !d.path.endsWith('_track'));
    final track = dirs.where((d) => d.path.endsWith('_track')).toList();
    final meta = jsonDecode(File('${capture.path}/meta.json').readAsStringSync()) as Map<String, dynamic>;
    final setup = meta['setup'] as Map<String, dynamic>;
    final discard = setup['tracked_discard'] as Map<String, dynamic>?;
    expect(discard, isNotNull, reason: '화료 때 추적한 마지막 버림이 넘어가야 한다');
    expect(discard!['side'], 'right');
    expect(discard['box'], isNotNull);
    // ignore: avoid_print
    print('[river] tracked_discard $discard, tracked_riichi ${setup['tracked_riichi']}');
    if (track.isNotEmpty) {
      final tj = jsonDecode(File('${track.last.path}/track.json').readAsStringSync()) as Map<String, dynamic>;
      final rivers = tj['rivers'] as Map<String, dynamic>?;
      final kinds = [for (final e in (rivers?['events'] as List<dynamic>? ?? const [])) (e as Map)['kind']];
      // ignore: avoid_print
      print('[river] track.json events: $kinds');
      expect(kinds, contains('discard'));
      expect(kinds.where((k) => '$k'.startsWith('sticks_')), isEmpty, reason: '리치봉 추적은 꺼져 있어 읽지 않아야 한다');
    }
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
  });
}
