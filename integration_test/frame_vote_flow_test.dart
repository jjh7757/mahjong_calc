// 프레임 투표(개선 계획 6단계) 흐름을 노트북에서 끝까지 본다: 화료 촬영 → 결과 화면(첫 판독으로 바로) → 자동 반영 직전에
// 헤드 프레임 1장을 /v2/localroles 로 한 번 더 읽어 같으면 자동 반영, 다르면 '프레임 불일치' 로 멈춤.
// 가짜 헤드는 `--after-capture`: 첫 사진만 보여 주다가 /capture 뒤엔 둘째 사진(같은 판의 다른 프레임 흉내).
// 먼저 띄울 것: 가짜 헤드 8777(`python -I experiments/tracking/fake_head.py <짝 폴더> 8777 --after-capture`) + 로컬 인식 서버
// (launch.json "recognizer-sig-prodlike" 8056 = feat/cls-alt, 또는 "recognizer-prodlike" 8036).
//   flutter test integration_test/frame_vote_flow_test.dart -d windows --dart-define=RECOGNIZER_URL=http://127.0.0.1:8056 \
//     --dart-define=RECOGNIZER_API_KEY=local --dart-define=FRAME_VOTE=true --dart-define=SCENE=D
// FRAME_VOTE=false 면 토글 끔(지금 동작 그대로 자동 반영). 결과는 "[vote-flow]" 줄과 촬영 기록 `<시각>/frame_vote.json`
// (`python -I -X utf8 experiments/speed/frame_vote.py logs <폴더>` 가 Python 규칙으로 다시 판정).
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:shared_preferences/shared_preferences.dart';

// 장면별 격자(read_grid_timing_test.dart `_bcd` 와 같음). 매장 사진은 GRID="x1,x2,y1,y2" 로.
const _grids = {
  'B': (272, 735, 137, 727),
  'C': (320, 760, 142, 717),
  'D': (280, 745, 173, 713),
};

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('자동 반영 직전 프레임 투표', (tester) async {
    const headUrl = String.fromEnvironment('HEAD_URL', defaultValue: 'http://127.0.0.1:8777');
    const vote = bool.fromEnvironment('FRAME_VOTE', defaultValue: true);
    const scene = String.fromEnvironment('SCENE', defaultValue: 'D');
    const gridArg = String.fromEnvironment('GRID');
    final out = const String.fromEnvironment('VOTE_OUT', defaultValue: '') != ''
        ? const String.fromEnvironment('VOTE_OUT')
        : '${Directory.systemTemp.path}/mahjong_vote_itest';
    CaptureLog.desktopRootOverride = out;
    final g = gridArg.isNotEmpty ? gridArg.split(',').map(int.parse).toList() : null;
    final (x1, x2, y1, y2) = g != null ? (g[0], g[1], g[2], g[3]) : _grids[scene]!;
    SharedPreferences.setMockInitialValues({
      'mount.remoteUrl': headUrl,
      'mount.gridSource': headUrl,
      'mount.remoteToken': 'local',
      'mount.tracking': false, // 투표만 본다(추적 호출이 서버를 같이 쓰지 않게)
      'mount.autoSetupOnStart': false,
      'mount.useGrid': true,
      'mount.autoRecord': true,
      'mount.frameVote': vote,
      'mount.grid': jsonEncode(GridZones.initial.copyWith(x1: x1, x2: x2, y1: y1, y2: y2).toJson()),
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
        await tester.pump(const Duration(milliseconds: 200));
        await Future<void>.delayed(const Duration(milliseconds: 200));
        if (f.evaluate().isNotEmpty) return true;
      }
      if (must) fail('$what 을(를) $seconds초 안에 못 봄 (${sw.elapsed.inSeconds}초)');
      return false;
    }

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await waitFor(find.byKey(const ValueKey('table-calc')), '테이블 화면', seconds: 20);
    // 배경 미리보기 한 장(프레임 긴 변을 알아야 투표가 고해상 미리보기로 받는다).
    await waitFor(find.byKey(const ValueKey('mount-shoot')), '촬영 버튼', seconds: 10);
    await Future<void>.delayed(const Duration(seconds: 4));
    await tester.pump();

    final roundsBefore = gameStore.current!.events.length;
    final shotAt = sw.elapsedMilliseconds;
    await tester.tap(find.byKey(const ValueKey('mount-shoot')));
    // 결과 화면(자동 반영 카운트다운)이 뜰 때까지. 눕힌 손패가 여럿이면 아래 자리를 고른다.
    final resultShown = find.byKey(const ValueKey('result-auto-bar'));
    final until = sw.elapsed + const Duration(seconds: 120);
    while (sw.elapsed < until && resultShown.evaluate().isEmpty) {
      await tester.pump(const Duration(milliseconds: 200));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      final pick = find.textContaining('아래:');
      if (find.textContaining('누가 났나요').evaluate().isNotEmpty && pick.evaluate().isNotEmpty) await tester.tap(pick.first);
    }
    expect(resultShown, findsOneWidget, reason: '자동 반영 대상 판독이어야 투표를 본다');
    final resultAt = sw.elapsedMilliseconds;
    // ignore: avoid_print
    print('[vote-flow] 결과 화면까지 ${(resultAt - shotAt) / 1000}초 (촬영 → 첫 판독)');

    // 자동 반영(점수판 기록이 늘고 테이블로 돌아옴) 또는 '프레임 불일치' 경고.
    final blocked = find.byKey(const ValueKey('result-gate-block'));
    final waiting = find.textContaining('프레임 확인 중');
    int? waitSeenAt;
    final end = sw.elapsed + const Duration(seconds: 90);
    while (sw.elapsed < end) {
      await tester.pump(const Duration(milliseconds: 200));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      if (waiting.evaluate().isNotEmpty) waitSeenAt ??= sw.elapsedMilliseconds;
      if (blocked.evaluate().isNotEmpty || gameStore.current!.events.length > roundsBefore) break;
    }
    final doneAt = sw.elapsedMilliseconds;
    final recorded = gameStore.current!.events.length > roundsBefore;
    final isBlocked = blocked.evaluate().isNotEmpty;
    // ignore: avoid_print
    print('[vote-flow] 토글 ${vote ? '켬' : '끔'} 장면 $scene → ${recorded ? '자동 반영' : isBlocked ? '프레임 불일치로 멈춤' : '둘 다 아님'}, '
        '결과 화면 뒤 ${(doneAt - resultAt) / 1000}초, "프레임 확인 중" 기다림 ${waitSeenAt == null ? 0 : (doneAt - waitSeenAt) / 1000}초');

    await Future<void>.delayed(const Duration(seconds: 2)); // frame_vote.json 은 백그라운드로 저장된다
    final root = Directory('$out/mahjong_calc');
    final dirs = root.listSync().whereType<Directory>().where((d) => !d.path.endsWith('_track')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    final capture = dirs.last;
    final fv = File('${capture.path}/frame_vote.json');
    // ignore: avoid_print
    print('[vote-flow] 촬영 기록 ${capture.path} frame_vote.json ${fv.existsSync() ? fv.readAsStringSync() : '없음'}');
    if (vote) {
      expect(fv.existsSync(), isTrue, reason: '토글을 켜면 촬영 기록에 두 판독이 남아야 한다');
      final j = jsonDecode(fv.readAsStringSync()) as Map<String, dynamic>;
      expect(isBlocked, j['result'] == 'mismatch');
      expect(recorded, j['result'] != 'mismatch');
    } else {
      expect(fv.existsSync(), isFalse);
      expect(recorded, isTrue);
      expect(waitSeenAt, isNull);
    }
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
  });
}
