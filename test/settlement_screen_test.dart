import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:mahjong_calc/ui/game/settlement_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 작혼식 대국 종료 화면: 순위 띠·최종 점수·득점, 대국이 끝나면 자동으로 뜨는지.
void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  void setSize(WidgetTester tester, Size size) {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  /// A 45000 · B 31000 · C 29000 · D −5000(토비). A 는 12000 화료 한 번.
  void bustGame() {
    gameStore.mutate((g) {
      g.events.add(GameEvent('win', 'A 론 12000', const [12000, 0, 0, -12000], g.roundLabel));
      g.adjust([20000, 6000, 4000, -30000], '시험');
    });
  }

  testWidgets('키오스크: 1위 패널 + 순위 띠, 최종 점수·득점·토비', (tester) async {
    setSize(tester, const Size(1280, 800));
    bustGame();
    await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: gameStore.current!)));
    await tester.pumpAndSettle();

    expect(find.text('토비 — 종료'), findsOneWidget);
    final winner = find.byKey(const ValueKey('settle-winner'));
    expect(find.descendant(of: winner, matching: find.text('A')), findsOneWidget);
    expect(find.descendant(of: winner, matching: find.text('화료 1 · 최고 +12000')), findsOneWidget);

    String scoreOf(int rank) => tester.widget<Text>(find.byKey(ValueKey('settle-score-$rank'))).data!;
    // 우마 20-10, 오카 20: A (45−30)+20+20, B (31−30)+10, C (29−30)−10, D (−5−30)−20.
    expect([for (var r = 1; r <= 4; r++) scoreOf(r)], ['+55', '+11', '-11', '-55']);
    final fourth = find.byKey(const ValueKey('settle-rank-4'));
    expect(find.descendant(of: fourth, matching: find.text('D')), findsOneWidget);
    expect(find.descendant(of: fourth, matching: find.text('-5000')), findsOneWidget);
    expect(find.descendant(of: fourth, matching: find.text('토비')), findsOneWidget);
    // 띠는 아래로 갈수록 오른쪽으로 들어간다.
    expect(tester.getTopLeft(fourth).dx, greaterThan(tester.getTopLeft(find.byKey(const ValueKey('settle-rank-1'))).dx));
  });

  testWidgets('폰 세로: 1위 패널 없이 띠만, 넘침 없음', (tester) async {
    setSize(tester, const Size(400, 800));
    bustGame();
    await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: gameStore.current!)));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('settle-winner')), findsNothing);
    expect(find.byKey(const ValueKey('settle-rank-1')), findsOneWidget);
    expect(find.text('저장하고 종료'), findsOneWidget);
  });

  testWidgets('저장하고 종료 → 지난 대국으로, 지난 대국은 확인 버튼만', (tester) async {
    setSize(tester, const Size(1280, 800));
    bustGame();
    final g = gameStore.current!;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (c) => TextButton(
          onPressed: () => Navigator.of(c).push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
          child: const Text('열기'),
        ),
      ),
    ));
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settle-finish')));
    await tester.pumpAndSettle();
    expect(gameStore.current, isNull);
    expect(gameStore.history.first.id, g.id);

    await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: g)));
    await tester.pumpAndSettle();
    expect(find.text('확인'), findsOneWidget);
    expect(find.text('저장하고 종료'), findsNothing);
  });

  testWidgets('점수판에서 대국이 끝나면 종료 화면이 자동으로 뜬다(창이 닫힌 뒤, 한 번만)', (tester) async {
    setSize(tester, const Size(1280, 800));
    await tester.pumpWidget(MaterialApp(navigatorObservers: [gameRouteObserver], home: const GameScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-title')), findsNothing);

    // 기록 창이 떠 있는 동안 끝나면 창이 닫힐 때까지 기다린다.
    final ctx = tester.element(find.byType(Scaffold).first);
    showDialog<void>(context: ctx, builder: (_) => const AlertDialog(title: Text('기록 중')));
    await tester.pumpAndSettle();
    bustGame();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-title')), findsNothing);

    Navigator.of(tester.element(find.text('기록 중'))).pop();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-title')), findsOneWidget);

    // 돌아가면 다시 뜨지 않는다.
    await tester.tap(find.text('돌아가기'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-title')), findsNothing);
    expect(find.byKey(const ValueKey('game-over-banner')), findsOneWidget);
  });
}
