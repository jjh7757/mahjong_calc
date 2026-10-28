import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 키오스크(태블릿 가로): 대국 중 첫 화면은 테이블 화면, 점수 계산은 따로 열고 반영하면 테이블로 돌아온다.
void main() {
  testWidgets('테이블 화면 → 직접 계산 → 대국에 반영 → 테이블 화면(점수 변화 표시)', (tester) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.physicalSize = const Size(2560, 1600);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    addTearDown(gameStore.discardCurrent);

    gameStore.resume(
      const ['A', 'B', 'C', 'D'],
      const GameSettings(),
      scores: const [25000, 25000, 25000, 25000],
      roundWind: 1,
      roundNumber: 2,
      honba: 1,
    );

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    await tester.pump();
    // 테이블 화면: 가운데 점수판에 국과 네 사람 점수.
    expect(find.text('남 2국'), findsOneWidget);
    for (var s = 0; s < 4; s++) {
      expect(find.byKey(ValueKey('table-score-$s')), findsOneWidget);
    }

    await tester.tap(find.byKey(const ValueKey('table-calc')));
    await tester.pumpAndSettle();
    expect(find.text('점수 계산 · 남2국 1본장'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('game-seat-2')));
    await tester.pump();
    for (final code in parseTiles('123m456p789s23m55p4m').tiles) {
      await tester.tap(find.byKey(ValueKey('palette-$code')));
      await tester.pump();
    }
    expect(find.text('손패 14/14'), findsOneWidget);
    await tester.tap(find.text('점수 계산').last);
    await tester.pumpAndSettle();
    // 화료 연출 화면: 역 + 판 동그라미, 판·부 원, 큰 점수, 도라 칸.
    expect(find.text('1300점'), findsOneWidget);
    expect(find.text('핑후'), findsOneWidget);
    expect(find.text('1판'), findsNWidgets(2)); // 역 옆 동그라미 + 판·부 원
    expect(find.text('30부'), findsOneWidget);
    expect(find.text('도라'), findsOneWidget);

    await tester.tap(find.textContaining('대국에 반영'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ChoiceChip, 'A').last);
    await tester.pump();
    await tester.tap(find.text('기록').last);
    await tester.pumpAndSettle();

    // 계산 화면까지 닫히고 테이블 화면으로 돌아와 다음 국과 점수 변화를 보여 준다.
    expect(find.byKey(const ValueKey('table-calc')), findsOneWidget);
    expect(find.text('남 3국'), findsOneWidget);
    expect(find.text('+1300'), findsOneWidget);
    expect(find.text('-1300'), findsOneWidget);

    // 점수 변화는 몇 초 뒤 사라진다.
    await tester.pump(const Duration(seconds: 7));
    expect(find.text('+1300'), findsNothing);
  });
}
