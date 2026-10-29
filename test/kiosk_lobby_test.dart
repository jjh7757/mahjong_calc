import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/ui/kiosk.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 키오스크(태블릿 가로)에서 대국이 없으면 첫 화면은 로비: 큰 "대국 시작" + 최근 대국 + 메뉴 타일.
void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    if (gameStore.current != null) gameStore.discardCurrent();
    gameStore.history.clear();
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
    gameStore.history.clear();
    kioskLobbyFor.value = null;
  });

  void setSize(WidgetTester tester, Size size) {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  testWidgets('대국이 없으면 로비, 대국 시작을 누르면 설정 폼', (tester) async {
    setSize(tester, const Size(1280, 800));
    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lobby-start')), findsOneWidget);
    expect(find.text('아직 기록한 대국이 없습니다'), findsOneWidget);
    for (final k in ['calc', 'history', 'table', 'quiz', 'settings', 'head']) {
      expect(find.byKey(ValueKey('lobby-$k')), findsOneWidget);
    }

    await tester.tap(find.byKey(const ValueKey('lobby-start')));
    await tester.pumpAndSettle();
    expect(find.text('자리 순서 (동 → 남 → 서 → 북)'), findsOneWidget);
  });

  testWidgets('설문 참여 → 설문 QR 창, 닫으면 로비', (tester) async {
    setSize(tester, const Size(1280, 800));
    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lobby-survey')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('survey-qr')), findsOneWidget);
    await tester.tap(find.text('닫기'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('survey-qr')), findsNothing);
    expect(find.byKey(const ValueKey('lobby-start')), findsOneWidget);
  });

  testWidgets('점수 계산 타일 → 계산기(뒤로 가면 로비)', (tester) async {
    setSize(tester, const Size(1280, 800));
    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lobby-calc')));
    await tester.pumpAndSettle();
    expect(find.text('마작 점수 계산기'), findsOneWidget);
    expect(find.text('점수 계산'), findsWidgets);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lobby-start')), findsOneWidget);
  });

  testWidgets('최근 대국 카드: 1위 이름, 누르면 종료 화면', (tester) async {
    setSize(tester, const Size(1280, 800));
    gameStore.start(const ['민수', '지현', '태호', '서연'], const GameSettings());
    gameStore.mutate((g) => g.adjust([-5000, 0, -3000, 8000], '시험'));
    gameStore.finish();

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pumpAndSettle();
    final recent = find.byKey(const ValueKey('lobby-recent'));
    expect(find.descendant(of: recent, matching: find.text('최근 대국')), findsOneWidget);
    expect(find.descendant(of: recent, matching: find.text('서연')), findsOneWidget);
    expect(find.descendant(of: recent, matching: find.text('33000 (+43)')), findsOneWidget);

    await tester.tap(find.descendant(of: recent, matching: find.text('서연')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-title')), findsOneWidget);
    expect(find.text('확인'), findsOneWidget);
  });

  // 폰도 태블릿과 같은 흐름(로비 → 대국 시작 → 테이블), 배치만 폰용(2026-10-29, 전엔 폰 = 계산기).
  for (final size in const [Size(412, 915), Size(360, 640), Size(915, 412)]) {
    testWidgets('폰 ${size.width.toInt()}×${size.height.toInt()}: 로비 → 계산기, 대국 시작 폼', (tester) async {
      setSize(tester, size);
      await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('lobby-start')), findsOneWidget);
      expect(find.text('아직 기록한 대국이 없습니다'), findsOneWidget);
      for (final k in ['calc', 'history', 'table', 'quiz', 'settings', 'head']) {
        await tester.ensureVisible(find.byKey(ValueKey('lobby-$k')));
        expect(find.byKey(ValueKey('lobby-$k')), findsOneWidget);
      }

      await tester.tap(find.byKey(const ValueKey('lobby-calc')));
      await tester.pumpAndSettle();
      expect(find.text('손패 0/14'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const ValueKey('lobby-start')));
      await tester.tap(find.byKey(const ValueKey('lobby-start')));
      await tester.pumpAndSettle();
      expect(find.text('자리 순서 (동 → 남 → 서 → 북)'), findsOneWidget);
    });

    testWidgets('폰 ${size.width.toInt()}×${size.height.toInt()}: 대국 중 테이블 화면 버튼, 홈 → 로비 이어 하기 → 테이블', (tester) async {
      setSize(tester, size);
      gameStore.start(const ['민수', '지현', '태호', '서연'], const GameSettings());
      gameStore.mutate((g) => g.declareRiichi(0));
      await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
      await tester.pump();
      for (final k in ['mount-shoot', 'table-calc', 'mount-gallery', 'table-end', 'table-home', 'table-undo', 'table-event-0']) {
        expect(find.byKey(ValueKey(k)), findsOneWidget, reason: k);
      }
      expect(find.text('리치'), findsOneWidget);
      expect(find.text('유국'), findsOneWidget);
      for (var s = 0; s < 4; s++) {
        expect(find.byKey(ValueKey('table-score-$s')), findsOneWidget);
      }

      await tester.ensureVisible(find.byKey(const ValueKey('table-calc')));
      await tester.tap(find.byKey(const ValueKey('table-calc')));
      await tester.pumpAndSettle();
      expect(find.text('손패 0/14'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const ValueKey('table-home')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('lobby-continue')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('lobby-continue')));
      await tester.pump();
      expect(find.byKey(const ValueKey('table-calc')), findsOneWidget);
    });
  }

  testWidgets('대국 중: 테이블의 홈 → 로비(이어 하기) → 다시 테이블, 홈에서 대국 종료 → 저장하고 종료 → 로비', (tester) async {
    setSize(tester, const Size(1280, 800));
    gameStore.start(const ['민수', '지현', '태호', '서연'], const GameSettings());
    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('table-home')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('table-home')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('lobby-continue')), findsOneWidget);
    expect(find.byKey(const ValueKey('lobby-start')), findsNothing);
    expect(gameStore.current, isNotNull); // 대국은 그대로

    await tester.tap(find.text('대국 이어 하기'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('table-home')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('table-home')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('lobby-end-game')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('settle-finish')));
    await tester.pumpAndSettle();
    expect(gameStore.current, isNull);
    expect(gameStore.history, hasLength(1));
    expect(find.byKey(const ValueKey('lobby-start')), findsOneWidget);
  });

  testWidgets('대국 중: 테이블의 대국 종료 → 중간 정산 → 저장하고 종료 → 로비', (tester) async {
    setSize(tester, const Size(1280, 800));
    gameStore.start(const ['민수', '지현', '태호', '서연'], const GameSettings());
    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('table-end')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('settle-finish')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('settle-finish')));
    await tester.pumpAndSettle();
    expect(gameStore.current, isNull);
    expect(find.byKey(const ValueKey('lobby-start')), findsOneWidget);
  });
}
