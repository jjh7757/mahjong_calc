import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:mahjong_calc/ui/game/settlement_screen.dart';
import 'package:mahjong_calc/ui/game/win_sheet.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/meld_sheet.dart';
import 'package:mahjong_calc/ui/quiz_screen.dart';
import 'package:mahjong_calc/ui/score_table_screen.dart';
import 'package:mahjong_calc/ui/settings_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 키오스크(가로 1280×800)에서 시트·창이 가운데 큰 패널(Dialog)로 뜨고, 폰에서는 바텀시트 그대로인지.
void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  void kioskSize(WidgetTester tester) {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  Future<void> pumpOpener(WidgetTester tester, void Function(BuildContext) open) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: Builder(builder: (c) => TextButton(onPressed: () => open(c), child: const Text('열기')))),
    ));
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
  }

  testWidgets('키오스크: 화료 시트는 가운데 Dialog', (tester) async {
    kioskSize(tester);
    await pumpOpener(tester, (c) => showWinSheet(c, gameStore.current!));
    expect(find.byType(Dialog), findsOneWidget);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text('화료 — 동1국'), findsOneWidget);
  });

  testWidgets('폰: 화료 시트는 바텀시트 그대로', (tester) async {
    tester.view.physicalSize = const Size(375, 812);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await pumpOpener(tester, (c) => showWinSheet(c, gameStore.current!));
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(find.byType(Dialog), findsNothing);
  });

  testWidgets('키오스크: 부르기 시트도 Dialog', (tester) async {
    kioskSize(tester);
    await pumpOpener(tester, (c) => showMeldSheet(c, HandEditor()));
    expect(find.byType(Dialog), findsOneWidget);
    expect(find.text('부르기'), findsOneWidget);
  });

  testWidgets('키오스크: 유국 창이 넓고 도중 유국 칩이 그대로 동작', (tester) async {
    kioskSize(tester);
    await pumpOpener(tester, (c) => showDrawDialog(c, gameStore.current!));
    final box = tester.getSize(find.byType(AlertDialog));
    expect(box.width, greaterThan(500));
    await tester.tap(find.byKey(const ValueKey('draw-abortive-구종구패')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('확인'));
    await tester.pumpAndSettle();
    expect(gameStore.current!.honba, 1);
  });

  testWidgets('키오스크: 대국 시작 폼·정산은 가운데 폭 제한 + 어두운 테마', (tester) async {
    kioskSize(tester);
    gameStore.discardCurrent();
    await tester.pumpWidget(const MaterialApp(home: GameScreen()));
    await tester.pumpAndSettle();
    expect(find.text('대국 시작'), findsWidgets);
    final body = tester.getSize(find.byType(ListView).first);
    expect(body.width, lessThanOrEqualTo(820));
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold).first);
    expect(Theme.of(tester.element(find.byWidget(scaffold))).brightness, Brightness.dark);

    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
    await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: gameStore.current!)));
    await tester.pumpAndSettle();
    // 정산은 작혼식 종료 화면: 왼쪽 1위 패널 + 오른쪽 순위 띠, 어두운 테마.
    expect(find.byKey(const ValueKey('settle-winner')), findsOneWidget);
    expect(find.byKey(const ValueKey('settle-rank-4')), findsOneWidget);
    expect(Theme.of(tester.element(find.byKey(const ValueKey('settle-title')))).brightness, Brightness.dark);
  });

  testWidgets('키오스크: 점수표·룰 설정·연습 화면은 어두운 테마', (tester) async {
    kioskSize(tester);
    Brightness brightnessOf(WidgetTester t) =>
        Theme.of(t.element(find.byType(Scaffold).first)).brightness;

    await tester.pumpWidget(const MaterialApp(home: ScoreTableScreen()));
    await tester.pumpAndSettle();
    expect(brightnessOf(tester), Brightness.dark);

    await tester.pumpWidget(MaterialApp(home: SettingsScreen(editor: HandEditor())));
    await tester.pumpAndSettle();
    expect(brightnessOf(tester), Brightness.dark);
    expect(tester.getSize(find.byType(ListView)).width, lessThanOrEqualTo(820));

    await tester.pumpWidget(const MaterialApp(home: QuizScreen()));
    await tester.pumpAndSettle();
    expect(brightnessOf(tester), Brightness.dark);
  });

  testWidgets('폰: 점수표는 밝은 테마 그대로', (tester) async {
    tester.view.physicalSize = const Size(375, 812);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: ScoreTableScreen()));
    await tester.pumpAndSettle();
    expect(Theme.of(tester.element(find.byType(Scaffold).first)).brightness, Brightness.light);
  });

  testWidgets('키오스크: 대국 버리기 확인 창도 어두운 테마', (tester) async {
    kioskSize(tester);
    await tester.pumpWidget(const MaterialApp(home: GameScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();
    final dialog = find.byType(AlertDialog);
    expect(dialog, findsOneWidget);
    expect(Theme.of(tester.element(dialog)).brightness, Brightness.dark);
    await tester.tap(find.text('아니오'));
    await tester.pumpAndSettle();
    expect(gameStore.current, isNotNull);
  });
}
