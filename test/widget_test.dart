import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/main.dart';

void main() {
  testWidgets('팔레트로 손패를 넣고 계산하면 결과 화면이 뜬다', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));

    expect(find.text('점수 계산'), findsOneWidget);
    expect(find.text('손패 0/14'), findsOneWidget);

    // 핑후 손패: 123m 456p 789s 23m 55p + 4m (론, 자)
    for (final code in parseTiles('123m456p789s23m55p4m').tiles) {
      final key = find.byKey(ValueKey('palette-$code'));
      await tester.ensureVisible(key);
      await tester.tap(key);
      await tester.pump();
    }
    expect(find.text('손패 14/14'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, '남풍').first); // 자풍 남
    await tester.pump();

    await tester.tap(find.text('점수 계산'));
    await tester.pumpAndSettle();

    expect(find.text('핑후'), findsOneWidget);
    expect(find.text('1000점'), findsOneWidget);
  });
}
