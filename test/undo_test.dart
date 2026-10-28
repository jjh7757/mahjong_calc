import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/score.dart' show payment;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:mahjong_calc/ui/game/settlement_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 대국 기록 되돌리기(마지막 기록 취소·그 기록부터 되돌리기·다시 실행)와 점수 정정.
void main() {
  final ron8000 = payment(2000, const Situation(isTsumo: false, seatWind: Tiles.south)); // 자 론 8000
  final dealerTsumo = payment(1000, const Situation(isTsumo: true, seatWind: Tiles.east)); // 친 2000 올

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  group('되돌리기 지점', () {
    test('화료 하나 되돌리면 점수·친·국·기록이 그 전으로', () {
      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      final g = gameStore.current!;
      expect(g.scores, [25000, 17000, 33000, 25000]);
      expect(g.dealer, 1);
      expect(g.checkpoints, hasLength(1));

      final removed = gameStore.rewind();
      expect(removed.single.kind, 'win');
      expect(g.scores, [25000, 25000, 25000, 25000]);
      expect(g.dealer, 0);
      expect(g.roundLabel, '동1국');
      expect(g.events, isEmpty);
      expect(g.canUndo, isFalse);
    });

    test('리치 + 화료는 기록 둘: 마지막만 취소하면 리치는 남는다', () {
      gameStore.mutate((g) => g.declareRiichi(0));
      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      final g = gameStore.current!;
      expect(g.riichiSticks, 0); // 화료자가 가져감
      gameStore.rewind();
      expect(g.riichiSeats, {0});
      expect(g.riichiSticks, 1);
      expect(g.scores, [24000, 25000, 25000, 25000]);
      expect(g.events.single.kind, 'riichi');
    });

    test('중간 기록부터 되돌리면 뒤 기록도 지운다', () {
      for (var i = 0; i < 3; i++) {
        gameStore.mutate((g) => g.draw({0, 1}));
      }
      final g = gameStore.current!;
      expect(g.honba, 3);
      final c = g.checkpointBefore(1)!;
      expect(g.eventsAfter(c), hasLength(2));
      gameStore.rewind(c);
      expect(g.events, hasLength(1));
      expect(g.honba, 1);
      expect(g.checkpoints, hasLength(1));
    });

    test('아가리야메로 끝난 대국을 되돌리면 종료가 풀린다(남은 공탁 1위 몫도)', () {
      gameStore.resume(const ['A', 'B', 'C', 'D'], const GameSettings(),
          scores: const [26000, 24000, 20000, 30000], roundWind: 1, roundNumber: 4);
      gameStore.mutate((g) => g.declareRiichi(0));
      gameStore.mutate((g) => g.win(winner: 3, isTsumo: true, payment: dealerTsumo));
      final g = gameStore.current!;
      expect(g.endedBy, '아가리야메');
      expect(g.isOver, isTrue);

      gameStore.rewind();
      expect(g.endedBy, isNull);
      expect(g.isOver, isFalse);
      expect(g.scores, [25000, 24000, 20000, 30000]);
      expect(g.riichiSticks, 1);
      expect(g.roundLabel, '남4국');
    });

    test('중간부터 시작 기록은 되돌릴 수 없다', () {
      gameStore.resume(const ['A', 'B', 'C', 'D'], const GameSettings(),
          scores: const [30000, 20000, 25000, 25000], roundWind: 0, roundNumber: 2);
      final g = gameStore.current!;
      expect(g.events, hasLength(1));
      expect(g.checkpointBefore(0), isNull);
      expect(g.canUndo, isFalse);
      expect(gameStore.rewind(), isEmpty);
    });

    test('사건이 없는 변경(설정 등)은 지점을 남기지 않는다', () {
      gameStore.mutate((g) => g.settings = const GameSettings(bottomSeat: 2));
      expect(gameStore.current!.checkpoints, isEmpty);
    });

    test('다시 실행: 되돌린 기록을 되살린다, 새 기록을 넣으면 사라진다', () {
      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      final g = gameStore.current!;
      gameStore.rewind();
      expect(gameStore.canRedo, isTrue);
      gameStore.redo();
      expect(identical(gameStore.current, g), isTrue);
      expect(g.scores, [25000, 17000, 33000, 25000]);
      expect(g.dealer, 1);
      expect(g.checkpoints, hasLength(1));

      gameStore.rewind();
      gameStore.mutate((g) => g.draw(const {}));
      expect(gameStore.canRedo, isFalse);
    });

    test('저장·불러오기에 지점이 남고, 지점 없는 옛 기록도 읽는다', () {
      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      final back = Game.fromJson(gameStore.current!.toJson());
      expect(back.checkpoints.single.scores, [25000, 25000, 25000, 25000]);
      back.rewindTo(back.checkpoints.single);
      expect(back.scores, [25000, 25000, 25000, 25000]);

      final old = gameStore.current!.toJson()..remove('checkpoints');
      expect(Game.fromJson(old).canUndo, isFalse);
    });

    test('끝낸 대국은 지점을 버린다', () {
      gameStore.mutate((g) => g.draw(const {}));
      gameStore.finish();
      expect(gameStore.history.first.checkpoints, isEmpty);
    });
  });

  test('점수 정정: 점수·본장·공탁을 한 사건으로, 되돌릴 수 있다', () {
    gameStore.mutate((g) => g.correct(delta: [-1000, 1000, 0, 0], honba: 2, riichiSticks: 1, reason: '지불 실수'));
    final g = gameStore.current!;
    expect(g.scores, [24000, 26000, 25000, 25000]);
    expect(g.honba, 2);
    expect(g.riichiSticks, 1);
    expect(g.events.single.description, '지불 실수 (본장 0→2, 공탁 0→1)');
    gameStore.rewind();
    expect(g.scores, [25000, 25000, 25000, 25000]);
    expect(g.honba, 0);
    expect(g.riichiSticks, 0);
  });

  group('화면', () {
    void setSize(WidgetTester tester, Size size) {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
    }

    testWidgets('점수판: 마지막 취소 → 확인 창(점수 미리보기) → 되돌림 → 다시 실행', (tester) async {
      setSize(tester, const Size(412, 915));
      await tester.pumpWidget(const MaterialApp(home: GameScreen()));
      await tester.pumpAndSettle();
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('game-undo'))).onPressed, isNull);

      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('game-undo')));
      await tester.pumpAndSettle();
      expect(find.text('마지막 기록을 취소할까요?'), findsOneWidget);
      expect(find.text('B  17000 → 25000'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('rewind-confirm')));
      await tester.pumpAndSettle();
      expect(gameStore.current!.scores, [25000, 25000, 25000, 25000]);
      expect(find.text('기록 1건을 되돌렸습니다'), findsOneWidget);

      await tester.tap(find.text('다시 실행'));
      await tester.pumpAndSettle();
      expect(gameStore.current!.scores, [25000, 17000, 33000, 25000]);
    });

    testWidgets('되돌림 알림("다시 실행" 버튼 달림)은 8초 뒤 사라진다', (tester) async {
      // 액션이 있는 스낵바는 Flutter 3.29+ 에서 기본으로 남는다 → 아래 흰 바가 계속 있었음(2026-10-27 사용자).
      setSize(tester, const Size(412, 915));
      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      await tester.pumpWidget(const MaterialApp(home: GameScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('game-undo')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('rewind-confirm')));
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsOneWidget);
      await tester.pump(const Duration(seconds: 9));
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsNothing);
    });

    testWidgets('기록을 누르면 그 기록부터 되돌리기 / 점수 정정', (tester) async {
      setSize(tester, const Size(412, 915));
      gameStore.mutate((g) => g.draw({0}));
      gameStore.mutate((g) => g.draw({1}));
      await tester.pumpWidget(const MaterialApp(home: GameScreen()));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('game-event-0')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('event-rewind')));
      await tester.pumpAndSettle();
      expect(find.text('지울 기록 2건'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('rewind-confirm')));
      await tester.pumpAndSettle();
      expect(gameStore.current!.events, isEmpty);

      await tester.tap(find.byKey(const ValueKey('game-correct')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const ValueKey('correct-score-0')), '23000');
      await tester.enterText(find.byKey(const ValueKey('correct-score-3')), '27000');
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('correct-confirm')));
      await tester.pumpAndSettle();
      final g = gameStore.current!;
      expect(g.scores, [23000, 25000, 25000, 27000]);
      expect(g.events.single.description, '점수 정정');
      expect(g.canUndo, isTrue);
    });

    testWidgets('키오스크 테이블 화면: 기록 칸의 마지막 취소', (tester) async {
      tester.view.physicalSize = const Size(2560, 1600);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      gameStore.mutate((g) => g.win(winner: 2, loser: 1, isTsumo: false, payment: ron8000));
      await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
      await tester.pump();
      expect(find.byKey(const ValueKey('table-event-0')), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('table-undo')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('rewind-confirm')));
      await tester.pumpAndSettle();
      expect(gameStore.current!.scores, [25000, 25000, 25000, 25000]);
      expect(find.text('기록 없음'), findsOneWidget);
    });

    testWidgets('종료 화면의 마지막 기록 취소 → 종료가 풀리고 화면이 닫힌다', (tester) async {
      setSize(tester, const Size(1280, 800));
      gameStore.mutate((g) => g.adjust([0, -30000, 30000, 0], '시험'));
      final g = gameStore.current!;
      expect(g.isOver, isTrue);
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
      await tester.tap(find.byKey(const ValueKey('settle-undo')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('rewind-confirm')));
      await tester.pumpAndSettle();
      expect(g.isOver, isFalse);
      expect(find.byKey(const ValueKey('settle-title')), findsNothing);
      expect(find.text('열기'), findsOneWidget);
    });
  });
}
