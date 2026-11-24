import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/game/member_store.dart';
import 'package:mahjong_calc/ui/game/member_screens.dart';
import 'package:mahjong_calc/ui/game/result_entry_screen.dart';
import 'package:mahjong_calc/ui/game/settlement_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 대국 결과 직접 입력: 등록 멤버에서만 고르기, 합계 검사, 저장 → 지난 대국 + 정산 화면.
void main() {
  const members = ['민수', '지현', '태호', '서연'];

  setUp(() async {
    SharedPreferences.setMockInitialValues({'members.list': members});
    await memberStore.load();
    if (gameStore.current != null) gameStore.discardCurrent();
    gameStore.history.clear();
  });
  tearDown(() {
    gameStore.history.clear();
  });

  Future<void> pick(WidgetTester tester, int seat, String name) async {
    await tester.ensureVisible(find.byKey(ValueKey('entry-name-$seat')));
    await tester.tap(find.byKey(ValueKey('entry-name-$seat')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ValueKey('entry-pick-$name')));
    await tester.pumpAndSettle();
  }

  Future<void> score(WidgetTester tester, int seat, String v) async {
    await tester.ensureVisible(find.byKey(ValueKey('entry-score-$seat')));
    await tester.enterText(find.byKey(ValueKey('entry-score-$seat')), v);
    await tester.pump();
  }

  bool saveEnabled(WidgetTester tester) =>
      tester.widget<FilledButton>(find.byKey(const ValueKey('entry-save'))).onPressed != null;

  testWidgets('멤버 고르기 · 점수 → 합계가 틀리면 오류와 저장 막힘, 맞추면 저장하고 정산 화면', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ResultEntryScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('entry-error')), findsOneWidget);
    expect(saveEnabled(tester), isFalse);

    await pick(tester, 0, '민수');
    // 이미 고른 멤버는 다른 자리 목록에 안 나온다.
    await tester.tap(find.byKey(const ValueKey('entry-name-1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('entry-pick-민수')), findsNothing);
    expect(find.byKey(const ValueKey('entry-pick-지현')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('entry-pick-지현')));
    await tester.pumpAndSettle();
    await pick(tester, 2, '태호');
    // 셋을 고르면 넷째 자리에는 남은 한 명만.
    await tester.tap(find.byKey(const ValueKey('entry-name-3')));
    await tester.pumpAndSettle();
    for (final n in ['민수', '지현', '태호']) {
      expect(find.byKey(ValueKey('entry-pick-$n')), findsNothing, reason: n);
    }
    await tester.tap(find.byKey(const ValueKey('entry-pick-서연')));
    await tester.pumpAndSettle();

    // 합계 99000(공탁 1000 을 1위에 안 더함) → 오류, 저장 막힘.
    await score(tester, 0, '45,000');
    await score(tester, 1, '30000');
    await score(tester, 2, '20000');
    await score(tester, 3, '4000');
    final error = find.byKey(const ValueKey('entry-error'));
    expect(error, findsOneWidget);
    expect((tester.widget<Text>(error).data ?? ''), contains('합계 99000'));
    expect((tester.widget<Text>(error).data ?? ''), contains('100000'));
    expect(saveEnabled(tester), isFalse);
    expect(find.byKey(const ValueKey('entry-preview')), findsNothing);

    // 100점 단위가 아니면 오류.
    await score(tester, 3, '5050');
    expect(find.byKey(const ValueKey('entry-error')), findsOneWidget);
    expect(saveEnabled(tester), isFalse);

    // 합계 100000 → 통과, 미리보기(1위 민수 +55).
    await score(tester, 3, '5000');
    expect(find.byKey(const ValueKey('entry-error')), findsNothing);
    expect(saveEnabled(tester), isTrue);
    expect(find.byKey(const ValueKey('entry-preview')), findsOneWidget);
    expect(find.text('+55'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('entry-save')));
    await tester.pumpAndSettle();

    expect(gameStore.history, hasLength(1));
    final g = gameStore.history.first;
    expect(g.isManual, isTrue);
    expect(g.finished, isTrue);
    expect(g.names, members);
    expect(g.scores, [45000, 30000, 20000, 5000]);
    expect(g.settle().map((r) => r.score).toList(), [55.0, 10.0, -20.0, -45.0]);
    expect(find.byType(SettlementScreen), findsOneWidget);
    expect(find.byType(ResultEntryScreen), findsNothing);
    expect(find.text('직접 입력한 대국'), findsOneWidget);
    expect(find.text('확인'), findsOneWidget);

    // 마지막으로 쓴 규칙을 기억한다.
    final p = await SharedPreferences.getInstance();
    final saved = GameSettings.fromJson(jsonDecode(p.getString('manual.settings')!) as Map<String, dynamic>);
    expect((saved.startPoints, saved.returnPoints, saved.umaBig, saved.umaSmall, saved.roundingMode),
        (25000, 30000, 20, 10, 1));
  });

  testWidgets('별 입력 → 미리보기 · 저장된 대국 starsOf · 정산 화면 ★ · 멤버 순위 별 열', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ResultEntryScreen()));
    await tester.pumpAndSettle();
    for (var i = 0; i < 4; i++) {
      await pick(tester, i, members[i]);
    }
    await score(tester, 0, '45000');
    await score(tester, 1, '30000');
    await score(tester, 2, '20000');
    await score(tester, 3, '5000');

    Future<void> tapKey(String k) async {
      await tester.ensureVisible(find.byKey(ValueKey(k)));
      await tester.tap(find.byKey(ValueKey(k)));
      await tester.pump();
    }

    String starsText(int i) => tester.widget<Text>(find.byKey(ValueKey('entry-stars-$i'))).data!;
    bool enabled(String k) => tester.widget<IconButton>(find.byKey(ValueKey(k))).onPressed != null;

    // 기본 0, 0 에서는 − 가 막힘.
    for (var i = 0; i < 4; i++) {
      expect(starsText(i), '0');
    }
    expect(enabled('entry-stars-1-minus'), isFalse);
    // 민수 +4 −1 = 3, 태호 +1.
    for (var n = 0; n < 4; n++) {
      await tapKey('entry-stars-0-plus');
    }
    await tapKey('entry-stars-0-minus');
    await tapKey('entry-stars-2-plus');
    expect(starsText(0), '3');
    expect(starsText(2), '1');
    expect(enabled('entry-stars-0-minus'), isTrue);
    expect(find.text('민수 ★3'), findsOneWidget);
    expect(find.text('태호 ★1'), findsOneWidget);

    await tester.ensureVisible(find.byKey(const ValueKey('entry-save')));
    await tester.tap(find.byKey(const ValueKey('entry-save')));
    await tester.pumpAndSettle();

    final g = gameStore.history.single;
    expect([for (var s = 0; s < 4; s++) g.starsOf(s)], [3, 0, 1, 0]);
    expect(find.byType(SettlementScreen), findsOneWidget);
    expect(tester.widget<Text>(find.byKey(const ValueKey('settle-stars-1'))).data, '★3');
    expect(tester.widget<Text>(find.byKey(const ValueKey('settle-stars-3'))).data, '★1');
    expect(find.byKey(const ValueKey('settle-stars-2')), findsNothing);
    expect(find.byKey(const ValueKey('settle-stars-4')), findsNothing);

    // 멤버 순위: 별 · 평별 · 최고점 · 1,2위율(새 앱으로 — 같은 MaterialApp 이면 정산 화면 경로가 남는다).
    await tester.pumpWidget(MaterialApp(key: UniqueKey(), home: const MemberRankingScreen()));
    await tester.pumpAndSettle();
    String cell(String k) => tester.widget<Text>(find.byKey(ValueKey(k))).data!;
    expect(cell('members-stars-민수'), '3');
    expect(cell('members-avgstars-민수'), '3.00');
    expect(cell('members-best-민수'), '45000');
    expect(cell('members-top2-민수'), '100%');
    expect(cell('members-stars-태호'), '1');
    expect(cell('members-top2-태호'), '0%');
  });

  testWidgets('명단이 비었으면 고르기 창에 멤버 관리 안내', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await memberStore.load();
    await tester.pumpWidget(const MaterialApp(home: ResultEntryScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('entry-name-0')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('entry-pick-empty')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('entry-pick-manage')));
    await tester.pumpAndSettle();
    expect(find.byType(MemberManageScreen), findsOneWidget);
  });

  testWidgets('멤버 순위: 결과 입력한 대국이 표에 잡히고, 대국 없는 멤버는 아래에', (tester) async {
    gameStore.addFinished(Game.manual(
      id: 'm1',
      playedAt: DateTime(2026, 11, 20, 20),
      settings: const GameSettings(),
      names: const ['민수', '지현', '태호', '남'],
      scores: const [45000, 30000, 20000, 5000],
    ));
    await tester.pumpWidget(const MaterialApp(home: MemberRankingScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('members-table')), findsOneWidget);
    expect(find.text('+55'), findsOneWidget);
    // 명단에 없는 '남' 은 표에 안 나오고, 대국 없는 서연은 나온다.
    expect(find.byKey(const ValueKey('members-row-남')), findsNothing);
    expect(find.byKey(const ValueKey('members-row-서연')), findsOneWidget);
    expect(find.byKey(const ValueKey('members-entry')), findsOneWidget);
    expect(find.byKey(const ValueKey('members-manage')), findsOneWidget);
  });
}
