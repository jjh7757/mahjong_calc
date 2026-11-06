import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:mahjong_calc/ui/seat_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 카메라 쪽 자리 맞추기 그림: 사람은 앉은 그대로, 앱에서 네 자리를 통째로 돌린다.
void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  String sideText(WidgetTester tester, String side) =>
      tester.widget<Text>(find.descendant(of: find.byKey(ValueKey('seat-side-$side')), matching: find.byType(Text))).data!;

  test('돌리기: 시계 = 오른쪽 사람이 아래로, 반시계 = 왼쪽 사람이 아래로', () {
    expect(SeatSidePicker.rotatedClockwise(0), 1);
    expect(SeatSidePicker.rotatedClockwise(3), 0);
    expect(SeatSidePicker.rotatedCounterClockwise(0), 3);
    expect(SeatSidePicker.rotatedCounterClockwise(2), 1);
  });

  testWidgets('그림은 반시계(아래→오른쪽→위→왼쪽)로 자리를 놓고 버튼으로 돈다', (tester) async {
    var bottom = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StatefulBuilder(
          builder: (_, set) => SeatSidePicker(
            labels: const ['동 A', '남 B', '서 C', '북 D'],
            bottomSeat: bottom,
            onChanged: (v) => set(() => bottom = v),
          ),
        ),
      ),
    ));
    expect(sideText(tester, 'bottom'), '동 A');
    expect(sideText(tester, 'right'), '남 B');
    expect(sideText(tester, 'top'), '서 C');
    expect(sideText(tester, 'left'), '북 D');

    await tester.tap(find.byKey(const ValueKey('seat-rotate-cw')));
    await tester.pump();
    expect(bottom, 1);
    expect(sideText(tester, 'bottom'), '남 B');
    expect(sideText(tester, 'left'), '동 A');

    for (var i = 0; i < 2; i++) {
      await tester.tap(find.byKey(const ValueKey('seat-rotate-ccw')));
      await tester.pump();
    }
    expect(bottom, 3);
    expect(sideText(tester, 'bottom'), '북 D');
    expect(sideText(tester, 'right'), '동 A');
  });

  testWidgets('대국 시작 폼에서 맞춘 자리가 대국 설정(bottomSeat)으로 들어간다', (tester) async {
    tester.view.physicalSize = const Size(1280, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: GameScreen()));
    await tester.pumpAndSettle();
    expect(sideText(tester, 'bottom'), '동 플레이어 1');

    await tester.tap(find.byKey(const ValueKey('seat-rotate-ccw')));
    await tester.pump();
    expect(sideText(tester, 'bottom'), '북 플레이어 4');

    final start = find.widgetWithText(FilledButton, '대국 시작');
    await tester.ensureVisible(start);
    await tester.tap(start);
    await tester.pumpAndSettle();
    expect(gameStore.current!.settings.bottomSeat, 3);
  });
}
