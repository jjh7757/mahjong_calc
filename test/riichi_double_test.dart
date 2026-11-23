// 점수판 리치 중복 막기 — 이미 이 국에 리치한 자리를 다시 리치하면 1000점이 또 빠져 국 시작 점수(handStart)가 1000 틀렸다(11-23).
// 모델(Game.declareRiichi)은 같은 자리 두 번째를 무시하고, 리치 고르기 창(showRiichiPicker)은 그 자리를 못 누르게 한다.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

Game _game() => Game(
      id: 'g',
      startedAt: DateTime(2026, 11, 23),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
    );

Future<void> _openPicker(WidgetTester tester) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (c) => TextButton(onPressed: () => showRiichiPicker(c, gameStore.current!), child: const Text('리치 열기')),
      ),
    ),
  ));
  await tester.tap(find.text('리치 열기'));
  await tester.pumpAndSettle();
  expect(find.text('누가 리치?'), findsOneWidget);
}

SimpleDialogOption _option(WidgetTester tester, int seat) =>
    tester.widget<SimpleDialogOption>(find.byKey(ValueKey('pick-seat-$seat')));

void main() {
  group('모델: 같은 자리 두 번째 리치는 무시', () {
    test('점수 −1000 한 번 · 봉 1 · 사건 1 · 국 시작 점수 그대로', () {
      final g = _game()
        ..declareRiichi(1)
        ..declareRiichi(1);
      expect(g.scores, [25000, 24000, 25000, 25000]);
      expect(g.riichiSticks, 1);
      expect(g.riichiSeats, {1});
      expect(g.events.where((e) => e.kind == 'riichi').length, 1);
      final st = g.handStart!;
      expect(st.scores, [25000, 25000, 25000, 25000]);
      expect(st.kyotaku, 0);
    });

    test('사진 자동 리치로 같은 자리를 다시 불러도 무시, 다른 자리는 들어간다', () {
      final g = _game()..declareRiichi(2);
      g.declareRiichi(2, fromPhoto: true);
      g.declareRiichi(0, fromPhoto: true);
      expect(g.scores, [24000, 25000, 24000, 25000]);
      expect(g.riichiSticks, 2);
      expect(g.events.map((e) => e.description), ['C 리치', 'A 리치 (자동)']);
      expect(g.handStart!.scores, [25000, 25000, 25000, 25000]);
      expect(g.handStart!.kyotaku, 0);
    });

    test('국이 넘어가면 같은 자리가 다시 리치할 수 있다', () {
      final g = _game()..declareRiichi(1);
      g.draw({1});
      g.declareRiichi(1);
      expect(g.riichiSticks, 2);
      expect(g.riichiSeats, {1});
      expect(g.events.where((e) => e.kind == 'riichi').length, 2);
    });
  });

  group('리치 고르기 창', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
    });
    tearDown(() {
      if (gameStore.current != null) gameStore.discardCurrent();
    });

    testWidgets('리치한 자리는 비활성 "리치함", 눌러도 그대로 · 안 한 자리는 눌린다', (tester) async {
      gameStore.mutate((g) => g.declareRiichi(1));
      await _openPicker(tester);

      expect(_option(tester, 1).onPressed, isNull);
      expect(find.textContaining('리치함'), findsOneWidget);
      for (final s in [0, 2, 3]) {
        expect(_option(tester, s).onPressed, isNotNull, reason: '자리 $s');
      }

      // 리치한 자리를 눌러도 창은 그대로, 점수 · 봉 · 사건 그대로.
      await tester.tap(find.byKey(const ValueKey('pick-seat-1')), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(find.text('누가 리치?'), findsOneWidget);
      final g = gameStore.current!;
      expect(g.scores, [25000, 24000, 25000, 25000]);
      expect(g.riichiSticks, 1);
      expect(g.events.where((e) => e.kind == 'riichi').length, 1);

      // 안 한 자리(C)는 눌리고 창이 닫힌다.
      await tester.tap(find.byKey(const ValueKey('pick-seat-2')));
      await tester.pumpAndSettle();
      expect(find.text('누가 리치?'), findsNothing);
      expect(g.scores, [25000, 24000, 24000, 25000]);
      expect(g.riichiSticks, 2);
      expect(g.riichiSeats, {1, 2});
      expect(g.handStart!.scores, [25000, 25000, 25000, 25000]);
    });

    testWidgets('네 자리 모두 리치했으면 창은 열리고 모두 비활성 + 안내 한 줄', (tester) async {
      for (var s = 0; s < 4; s++) {
        gameStore.mutate((g) => g.declareRiichi(s));
      }
      await _openPicker(tester);
      for (var s = 0; s < 4; s++) {
        expect(_option(tester, s).onPressed, isNull, reason: '자리 $s');
      }
      expect(find.textContaining('리치함'), findsNWidgets(4));
      expect(find.text('네 자리 모두 리치했습니다.'), findsOneWidget);
    });

    testWidgets('아무도 리치 안 했으면 네 자리 모두 눌리고 안내는 없다', (tester) async {
      await _openPicker(tester);
      for (var s = 0; s < 4; s++) {
        expect(_option(tester, s).onPressed, isNotNull, reason: '자리 $s');
      }
      expect(find.textContaining('리치함'), findsNothing);
      expect(find.text('네 자리 모두 리치했습니다.'), findsNothing);
    });
  });
}
