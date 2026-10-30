// 판독 중 "취소하고 직접 입력" → 입력 화면, 판독 결과가 뒤늦게 끼어들지 않는지 끝까지 본다.
// 먼저 띄울 것: 가짜 헤드
//   python -I experiments/tracking/fake_head.py experiments/tracking/seq 8777 --seq --hold 15,6
//   flutter test integration_test/read_cancel_test.dart -d emulator-5554 \
//     --dart-define=HEAD_URL=http://10.0.2.2:8777 --dart-define=RECOGNIZER_API_KEY=<키>
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/ui/input_screen.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('화료 촬영 → 판독 중 취소 → 입력 화면, 판독 결과 화면은 뜨지 않는다', (tester) async {
    const headUrl = String.fromEnvironment('HEAD_URL', defaultValue: 'http://127.0.0.1:8777');
    SharedPreferences.setMockInitialValues({
      'mount.remoteUrl': headUrl,
      'mount.remoteToken': 'local',
      'mount.tracking': false,
      'mount.autoSetupOnStart': false,
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
    final eventsBefore = gameStore.current!.events.length; // resumed 가 시작 사건을 하나 넣는다

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    Future<void> waitFor(Finder f, String what, {int seconds = 30}) async {
      final sw = Stopwatch()..start();
      while (f.evaluate().isEmpty) {
        if (sw.elapsed.inSeconds > seconds) fail('$what 을(를) $seconds초 안에 못 봄');
        await tester.pump(const Duration(milliseconds: 200));
      }
    }

    final shoot = find.byKey(const ValueKey('mount-shoot'));
    await waitFor(shoot, '화료 촬영 버튼');
    // 미리보기가 한 번 돌아 버튼이 켜지기를 기다린다.
    for (var i = 0; i < 15; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    await tester.tap(shoot);

    final cancel = find.byKey(const ValueKey('read-cancel'));
    await waitFor(cancel, '취소 버튼');
    final sw = Stopwatch()..start();
    await tester.tap(cancel);
    await waitFor(find.byType(InputScreen), '입력 화면', seconds: 5);
    // ignore: avoid_print
    print('[cancel] 취소 → 입력 화면 ${sw.elapsedMilliseconds}ms');

    // 판독이 살아 있었다면 끝났을 만큼 기다려도 결과 화면이 끼어들지 않는다.
    for (var i = 0; i < 100; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    expect(find.byType(ResultScreen), findsNothing);
    expect(find.byType(InputScreen), findsOneWidget);
    expect(gameStore.current!.events.length, eventsBefore, reason: '취소한 판독이 기록을 남기면 안 된다');
  });
}
