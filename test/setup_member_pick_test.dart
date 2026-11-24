import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/game/member_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:mahjong_calc/ui/game/member_screens.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 앱으로 치는 대국의 이름을 등록 멤버 명단에서 고른다: 이미 고른 사람은 빠지고, 손님은 직접 입력,
/// 마지막 대국의 네 이름이 모두 명단에 있으면 다음 설정 폼 기본값.
void main() {
  const members = ['민수', '지현', '태호', '서연'];

  Future<void> init(Map<String, Object> prefs) async {
    SharedPreferences.setMockInitialValues(prefs);
    await memberStore.load();
  }

  setUp(() => init({'members.list': members}));
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  String nameOf(WidgetTester tester, int i) =>
      tester.widget<TextField>(find.byKey(ValueKey('setup-name-$i'))).controller!.text;

  Future<void> open(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: GameScreen()));
    await tester.pumpAndSettle();
  }

  Future<void> tapName(WidgetTester tester, int i) async {
    await tester.tap(find.byKey(ValueKey('setup-name-$i')));
    await tester.pumpAndSettle();
  }

  testWidgets('명단에서 고르기: 다른 자리에서 고른 사람은 목록에서 빠진다', (tester) async {
    await open(tester);
    // 지난 대국 기록이 없으면 기본 이름 그대로.
    expect([for (var i = 0; i < 4; i++) nameOf(tester, i)], ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4']);

    await tapName(tester, 0);
    for (final n in members) {
      expect(find.byKey(ValueKey('setup-pick-$n')), findsOneWidget, reason: n);
    }
    expect(find.byKey(const ValueKey('setup-pick-type')), findsOneWidget);
    expect(find.textContaining('멤버 순위에 잡히지 않습니다'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('setup-pick-지현')));
    await tester.pumpAndSettle();
    expect(nameOf(tester, 0), '지현');

    await tapName(tester, 1);
    expect(find.byKey(const ValueKey('setup-pick-지현')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('setup-pick-민수')));
    await tester.pumpAndSettle();
    expect(nameOf(tester, 1), '민수');

    // 셋째 자리: 지현 · 민수 빠지고 태호 · 서연만.
    await tapName(tester, 2);
    expect(find.byKey(const ValueKey('setup-pick-지현')), findsNothing);
    expect(find.byKey(const ValueKey('setup-pick-민수')), findsNothing);
    expect(find.byKey(const ValueKey('setup-pick-태호')), findsOneWidget);
    expect(find.byKey(const ValueKey('setup-pick-서연')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('setup-pick-서연')));
    await tester.pumpAndSettle();

    // 첫 자리를 다시 열면 자기 이름(지현)은 목록에 있다.
    await tapName(tester, 0);
    expect(find.byKey(const ValueKey('setup-pick-지현')), findsOneWidget);
    expect(find.byKey(const ValueKey('setup-pick-민수')), findsNothing);
    expect(find.byKey(const ValueKey('setup-pick-서연')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('setup-pick-태호')));
    await tester.pumpAndSettle();
    expect([for (var i = 0; i < 4; i++) nameOf(tester, i)], ['태호', '민수', '서연', '플레이어 4']);
  });

  testWidgets('이름 직접 입력(손님) → 앱 안 키보드', (tester) async {
    await open(tester);
    await tapName(tester, 2);
    await tester.tap(find.byKey(const ValueKey('setup-pick-type')));
    await tester.pumpAndSettle();
    expect(find.text('서가 이름'), findsOneWidget);
    for (final k in ['ㄱ', 'ㅣ', 'ㅁ']) {
      await tester.tap(find.text(k));
      await tester.pump();
    }
    await tester.tap(find.byKey(const ValueKey('name-kb-done')));
    await tester.pumpAndSettle();
    expect(nameOf(tester, 2), '김');
  });

  testWidgets('멤버 관리로 갈 수 있다', (tester) async {
    await open(tester);
    await tapName(tester, 0);
    await tester.tap(find.byKey(const ValueKey('setup-pick-manage')));
    await tester.pumpAndSettle();
    expect(find.byType(MemberManageScreen), findsOneWidget);
  });

  testWidgets('명단이 비면 바로 키보드(고르기 창 없음)', (tester) async {
    await init({});
    await open(tester);
    await tapName(tester, 0);
    expect(find.byKey(const ValueKey('setup-pick-type')), findsNothing);
    expect(find.text('동가 이름'), findsOneWidget);
  });

  testWidgets('대국을 시작하면 네 이름을 기억하고, 모두 명단에 있으면 다음 폼 기본값', (tester) async {
    await open(tester);
    for (final (i, n) in [(0, '서연'), (1, '태호'), (2, '지현'), (3, '민수')]) {
      await tapName(tester, i);
      await tester.tap(find.byKey(ValueKey('setup-pick-$n')));
      await tester.pumpAndSettle();
    }
    final start = find.widgetWithText(FilledButton, '대국 시작');
    await tester.ensureVisible(start);
    await tester.tap(start);
    await tester.pumpAndSettle();
    expect(gameStore.current!.names, ['서연', '태호', '지현', '민수']);
    final p = await SharedPreferences.getInstance();
    expect(p.getStringList('setup.lastMembers'), ['서연', '태호', '지현', '민수']);

    // 대국을 버리고 새 설정 폼 → 지난 네 이름.
    gameStore.discardCurrent();
    await tester.pumpWidget(MaterialApp(key: UniqueKey(), home: const GameScreen()));
    await tester.pumpAndSettle();
    expect([for (var i = 0; i < 4; i++) nameOf(tester, i)], ['서연', '태호', '지현', '민수']);
  });

  testWidgets('지난 이름 중 명단에 없는 사람(손님)이 있으면 기본 이름', (tester) async {
    await init({
      'members.list': members,
      'setup.lastMembers': ['민수', '지현', '손님', '서연'],
    });
    await open(tester);
    expect([for (var i = 0; i < 4; i++) nameOf(tester, i)], ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4']);
  });

  testWidgets('지난 이름이 모두 멤버여도 명단이 비었으면 채우지 않는다', (tester) async {
    await init({
      'setup.lastMembers': ['민수', '지현', '태호', '서연'],
    });
    await open(tester);
    expect(nameOf(tester, 0), '플레이어 1');
  });
}
