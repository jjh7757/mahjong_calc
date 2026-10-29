// 판 상태 추적 흐름을 노트북에서 끝까지 본다(docs/state_tracking_design.md 9절 6).
// 먼저 띄울 것: 가짜 헤드(시퀀스 재생) + 로컬 인식 서버(launch.json "recognizer", 8030).
//   python -I <scratchpad>/fake_head.py <seq 폴더> 8777 --seq --hold 15,6
//   flutter test integration_test/tracking_flow_test.dart -d windows \
//     --dart-define=RECOGNIZER_URL=http://127.0.0.1:8030 --dart-define=RECOGNIZER_API_KEY=local
// 기록은 TRACK_OUT(기본 %TEMP%/mahjong_track_itest) 아래 mahjong_calc/ 에 남긴다.
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

  testWidgets('헤드 미리보기로 울기를 미리 읽어 확정하고, 화료 때 손패 전용 + 그림자 기록까지', (tester) async {
    const headUrl = String.fromEnvironment('HEAD_URL', defaultValue: 'http://127.0.0.1:8777');
    final out = const String.fromEnvironment('TRACK_OUT', defaultValue: '') != ''
        ? const String.fromEnvironment('TRACK_OUT')
        : '${Directory.systemTemp.path}/mahjong_track_itest';
    CaptureLog.desktopRootOverride = out;
    SharedPreferences.setMockInitialValues({
      'mount.remoteUrl': headUrl,
      'mount.remoteToken': 'local',
      'mount.tracking': true,
      'mount.autoSetupOnStart': false, // 대국 시작 자동 맞추기는 이 흐름에 안 섞는다(격자 고정)
      'mount.shadow': true,
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
    Future<void> waitFor(Finder f, String what, {int seconds = 90}) async {
      final until = sw.elapsed + Duration(seconds: seconds);
      while (sw.elapsed < until) {
        await tester.pump(const Duration(milliseconds: 500));
        await Future<void>.delayed(const Duration(milliseconds: 500));
        if (f.evaluate().isNotEmpty) return;
      }
      fail('$what 을(를) $seconds초 안에 못 봄 (${sw.elapsed.inSeconds}초)');
    }

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await waitFor(find.byKey(const ValueKey('table-calc')), '테이블 화면', seconds: 20);
    // 가짜 헤드: 15초 울기 전 → 6초 손 → 치 [6m 7m 8m]. 두 읽기 일치로 확정되기까지 기다린다.
    await waitFor(find.textContaining('미리 읽음'), '울기 확정 칩');
    // ignore: avoid_print
    print('[tracking] 확정까지 ${sw.elapsed.inSeconds}초');

    await tester.tap(find.byKey(const ValueKey('mount-shoot')));
    await waitFor(find.textContaining('대국에 반영'), '결과 화면', seconds: 150);
    // ignore: avoid_print
    print('[tracking] 화료 결과까지 ${sw.elapsed.inSeconds}초');
    expect(find.textContaining('미리 읽어 둔'), findsOneWidget, reason: '추적 울기를 썼다는 플래그');

    // 기록: 화료 폴더(meta.tracked_mode=handonly, shadow.json)와 추적 폴더(corner_*.json 에 자리·이름).
    final root = Directory('$out/mahjong_calc');
    final dirs = root.listSync().whereType<Directory>().toList()..sort((a, b) => a.path.compareTo(b.path));
    final capture = dirs.lastWhere((d) => !d.path.endsWith('_track'));
    final track = dirs.lastWhere((d) => d.path.endsWith('_track'));
    final meta = jsonDecode(File('${capture.path}/meta.json').readAsStringSync()) as Map<String, dynamic>;
    expect(meta['tracked_mode'], {'bottom': 'handonly'});
    expect((meta['setup'] as Map)['shadow'], isTrue);
    final shadow = jsonDecode(File('${capture.path}/shadow.json').readAsStringSync()) as Map<String, dynamic>;
    final b = shadow['bottom'] as Map<String, dynamic>;
    // ignore: avoid_print
    print('[shadow] handonly ${b['handonly_ms']}ms (${(b['handonly'] as Map)['agreement']}) / '
        'seat ${b['seat_ms']}ms (${(b['seat'] as Map)['agreement']})');
    final corners = track.listSync().where((f) => f.path.endsWith('.json') && f.path.contains('corner_')).toList();
    expect(corners, isNotEmpty);
    final c = jsonDecode(File(corners.first.path).readAsStringSync()) as Map<String, dynamic>;
    expect(c['side'], 'bottom');
    expect(c['seat'], 0);
    expect(c['name'], 'A');
    // ignore: avoid_print
    print('[track] ${track.path} 읽기 ${corners.length}번, 결과 ${capture.path}');
    // 거치 화면을 내려 배경 폴링 타이머를 멈춘다(남은 타이머가 있으면 테스트가 실패로 끝난다).
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
  });
}
