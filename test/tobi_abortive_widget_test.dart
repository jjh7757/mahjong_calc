import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  testWidgets('유국 창에서 구종구패를 고르면 점수 그대로 본장 +1', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (c) => TextButton(onPressed: () => showDrawDialog(c, gameStore.current!), child: const Text('유국')),
        ),
      ),
    ));
    await tester.tap(find.text('유국'));
    await tester.pumpAndSettle();
    expect(find.text('유국 — 텐파이한 사람'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('draw-abortive-구종구패')));
    await tester.pumpAndSettle();
    expect(find.text('도중 유국 — 구종구패'), findsOneWidget);
    // 텐파이 체크박스는 숨는다.
    expect(find.byKey(const ValueKey('draw-tenpai-0')), findsNothing);

    await tester.tap(find.text('확인'));
    await tester.pumpAndSettle();
    final g = gameStore.current!;
    expect(g.scores, [25000, 25000, 25000, 25000]);
    expect(g.honba, 1);
    expect(g.dealer, 0);
    expect(g.events.last.description, '도중 유국 (구종구패)');
  });

  testWidgets('토비면 점수판에 배너와 정산만 남는다', (tester) async {
    gameStore.mutate((g) => g.adjust([0, -30000, 30000, 0], '시험'));
    await tester.pumpWidget(const MaterialApp(home: GameScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('game-over-banner')), findsOneWidget);
    expect(find.text('토비 — 종료'), findsOneWidget);
    expect(find.text('화료'), findsNothing);
    expect(find.text('유국'), findsNothing);
    expect(find.text('정산'), findsOneWidget);
  });
}
