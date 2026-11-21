import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/hand_restore/rebuild.dart';
import 'package:mahjong_calc/paifu/hand_restore/restore_ui.dart';
import 'package:mahjong_calc/paifu/hand_restore/restorer.dart';
import 'package:mahjong_calc/paifu/hand_restore/turns.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_store.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'hand_restore_fixtures.dart';

/// 가짜 실행기: 진행을 한 번 알리고 [gate] 가 풀리면 정답으로 복원한 결과를 낸다.
class _FakeRunner implements HandRestoreRunner {
  final Paifu orig;
  final gate = Completer<void>();
  var runs = 0;
  bool sawCancel = false;
  _FakeRunner(this.orig);

  @override
  Future<RestoreOutcome> run(Paifu p, {void Function(RestoreProgress)? onProgress, bool Function()? cancelled}) async {
    runs++;
    onProgress?.call(const RestoreProgress(done: 1, total: 9, usd: 0.42, turn: 12, message: '12번째 버림 읽는 중'));
    await gate.future;
    sawCancel = cancelled?.call() ?? false;
    final turns = planTurns(p);
    final rb = rebuildHands(p, turns, {for (final t in apiTurns(p)) t: truthReadings(orig)[t]!});
    return RestoreOutcome(
      paifu: rb.paifu,
      rebuild: rb,
      usd: 2.5,
      apiTurns: 9,
      ruleTurns: 2,
      guessTurns: 0,
      unsureTurns: const [3, 7],
    );
  }
}

void main() {
  final orig = withEndHand(assetJson('r18_141259'));
  final stripped = stripHands(orig);

  Future<void> pump(WidgetTester tester, Paifu p, {String? gameId, bool dir = true, _FakeRunner? runner}) async {
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
      home: PaifuScreen(
        key: UniqueKey(),
        paifu: p,
        gameId: gameId,
        restoreSetup: HandRestoreSetup(dirExists: (_) => dir, runnerFor: (_) => runner ?? _FakeRunner(orig)),
      ),
    ));
    await tester.pumpAndSettle();
  }

  const btn = ValueKey('paifu-restore');
  const why = ValueKey('paifu-restore-why');

  testWidgets('버튼 조건: 예시(대국 없음) · 손패 있음이면 없음, 녹화 · 폴더 · 끝 손패가 없으면 까닭 한 줄', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await pump(tester, stripped);
    expect(find.byKey(btn), findsNothing);
    expect(find.byKey(why), findsNothing);

    await pump(tester, orig, gameId: 'g');
    expect(find.byKey(btn), findsNothing);

    await pump(tester, stripped, gameId: 'g');
    expect(find.byKey(btn), findsOneWidget);
    expect(find.text('손패 복원 (Claude API)'), findsOneWidget);
    expect(find.byKey(const ValueKey('paifu-restore-nokey')), findsOneWidget);

    await pump(tester, stripped, gameId: 'g', dir: false);
    expect(find.byKey(btn), findsNothing);
    expect(find.textContaining('녹화 폴더가 이 기기에 없어'), findsOneWidget);

    final noFrames = Paifu.fromJson(stripped.toJson()..remove('frames'));
    await pump(tester, noFrames, gameId: 'g');
    expect(find.textContaining('헤드 녹화를 받아 저장하던 판이 아니라'), findsOneWidget);

    final noEnd = stripHands(Paifu.fromJson(assetJson('r20_143236')));
    await pump(tester, noEnd, gameId: 'g');
    expect(find.textContaining('끝 손패가 없는 판'), findsOneWidget);
  });

  testWidgets('키 없으면 입력 창(가림) → 저장 → 확인 창의 어림 비용 글 → 취소하면 부르지 않음', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final runner = _FakeRunner(orig);
    await pump(tester, stripped, gameId: 'g', runner: runner);
    await tester.tap(find.byKey(btn));
    await tester.pumpAndSettle();
    final field = find.byKey(const ValueKey('restore-key-field'));
    expect(field, findsOneWidget);
    expect(tester.widget<TextField>(field).obscureText, isTrue);
    await tester.enterText(field, 'sk-ant-test');
    await tester.tap(find.byKey(const ValueKey('restore-key-save')));
    await tester.pumpAndSettle();
    expect((await SharedPreferences.getInstance()).getString('claude.apiKey'), 'sk-ant-test');
    final plan = tester.widget<Text>(find.byKey(const ValueKey('restore-plan'))).data!;
    expect(plan, contains('차례당 0.1 ~ 1.7달러, 판당 약 3달러(11-14 실험)'));
    expect(plan, contains('규칙 차례'));
    expect(plan, contains('판 10달러'));
    expect(find.text('sk-ant-test'), findsNothing);
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();
    expect(runner.runs, 0);
    expect(find.byKey(const ValueKey('paifu-restore-nokey')), findsNothing);
  });

  testWidgets('진행(차례 i/N · 누적 달러 · 취소) → 결과 → 다시 그림 → 되돌리기', (tester) async {
    SharedPreferences.setMockInitialValues({'claude.apiKey': 'sk-x'});
    await PaifuStore.put('g', stripped);
    final runner = _FakeRunner(orig);
    await pump(tester, stripped, gameId: 'g', runner: runner);
    await tester.tap(find.byKey(btn));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('restore-start')));
    await tester.pump();
    await tester.pump();
    expect(runner.runs, 1);
    final prog = tester.widget<Text>(find.byKey(const ValueKey('restore-progress'))).data!;
    expect(prog, contains('차례 1/9'));
    expect(prog, contains('0.42달러'));
    await tester.tap(find.byKey(const ValueKey('restore-cancel')));
    await tester.pump();
    expect(find.textContaining('취소하는 중'), findsOneWidget);
    runner.gate.complete();
    await tester.pumpAndSettle();
    expect(runner.sawCancel, isTrue);
    final res = tester.widget<Text>(find.byKey(const ValueKey('restore-result'))).data!;
    expect(res, contains('복원한 차례'));
    expect(res, contains('확신 낮은 차례: 3번째 · 7번째'));
    expect(res, contains('2.50달러'));
    await tester.tap(find.text('확인'));
    await tester.pumpAndSettle();

    // 다시 그림: 손패가 생겨 복원 단추 대신 되돌리기, 저장소도 바뀜.
    expect(find.byKey(btn), findsNothing);
    expect(find.byKey(const ValueKey('paifu-start-hand')), findsNothing);
    expect(find.byKey(const ValueKey('paifu-restore-revert')), findsOneWidget);
    expect((await PaifuStore.list('g')).single.handSource, 'claude_api');

    await tester.tap(find.byKey(const ValueKey('paifu-restore-revert')));
    await tester.pumpAndSettle();
    expect(find.byKey(btn), findsOneWidget);
    expect((await PaifuStore.list('g')).single.hasHeroHands, isFalse);
  });

  testWidgets('대국 패보 목록이 gameId 를 넘겨 재생 화면에 복원 단추가 나옴', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await PaifuStore.put('g', stripped);
    tester.view.physicalSize = const Size(1600, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MaterialApp(home: PaifuListScreen(gameId: 'g')));
    await tester.pumpAndSettle();
    expect(find.textContaining('버림만'), findsOneWidget);
    await tester.tap(find.byType(ListTile));
    await tester.pumpAndSettle();
    // 테스트 기기에는 녹화 폴더가 없어 까닭 한 줄이 나온다(기본 폴더 확인).
    expect(find.textContaining('녹화 폴더가 이 기기에 없어'), findsOneWidget);
  });
}
