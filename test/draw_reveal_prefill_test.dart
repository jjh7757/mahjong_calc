import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 유국 창: 헤드 사진에서 손패를 공개한 자리([revealed])가 늦게 와도 사람이 안 누른 자리만 텐파이로 켠다.
void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  // 유국 창 줄은 체크박스(텐파이 켜기·끄기) 또는 텐파이·노텐 칩 둘 다 받는다.
  bool selected(WidgetTester t, String key) {
    final w = t.widget(find.byKey(ValueKey(key)));
    return w is ChoiceChip ? w.selected : (w as CheckboxListTile).value == true;
  }

  Future<void> pressNoten(WidgetTester t, int s) async {
    final noten = find.byKey(ValueKey('draw-noten-$s'));
    if (noten.evaluate().isNotEmpty) {
      await t.tap(noten);
    } else {
      // 체크박스: 켰다가 끄면 노텐으로 누른 것.
      await t.tap(find.byKey(ValueKey('draw-tenpai-$s')));
      await t.pump();
      await t.tap(find.byKey(ValueKey('draw-tenpai-$s')));
    }
    await t.pump();
  }

  Future<void> open(WidgetTester tester, Future<Set<int>?> revealed, void Function(Set<int>?) done) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (c) => TextButton(onPressed: () async => done(await showDrawDialog(c, gameStore.current!, revealed: revealed)), child: const Text('유국')),
        ),
      ),
    ));
    await tester.tap(find.text('유국'));
    await tester.pumpAndSettle();
  }

  testWidgets('사진 답이 오면 공개 자리를 텐파이로, 먼저 누른 자리는 그대로', (tester) async {
    final photo = Completer<Set<int>?>();
    Set<int>? result = {-1};
    await open(tester, photo.future, (r) => result = r);
    expect(find.text('사진에서 공개한 손패를 확인하는 중…'), findsOneWidget);
    expect(selected(tester, 'draw-tenpai-1'), isFalse);

    // 답이 오기 전에 사람이 2번 자리를 노텐으로 눌러 둠.
    await pressNoten(tester, 2);
    photo.complete({1, 2});
    await tester.pumpAndSettle();
    expect(selected(tester, 'draw-tenpai-1'), isTrue);
    expect(selected(tester, 'draw-tenpai-2'), isFalse, reason: '사람이 누른 자리는 사진 답으로 바꾸지 않는다');
    expect(find.text('사진: B·C 손패 공개 → 텐파이로 켜 둠'), findsOneWidget);

    await tester.tap(find.text('확인'));
    await tester.pumpAndSettle();
    expect(result, {1});
    // 1명 텐파이: 노텐 셋이 1000점씩 → 텐파이 3000.
    expect(gameStore.current!.scores, [24000, 28000, 24000, 24000]);
  });

  testWidgets('사진 확인 실패면 안내만, 칩은 그대로', (tester) async {
    await open(tester, Future.value(null), (_) {});
    expect(find.text('사진을 확인하지 못했습니다 — 직접 골라 주세요'), findsOneWidget);
    for (var s = 0; s < 4; s++) {
      expect(selected(tester, 'draw-tenpai-$s'), isFalse);
    }
  });

  testWidgets('창을 닫은 뒤 온 답은 기록을 바꾸지 않는다', (tester) async {
    final photo = Completer<Set<int>?>();
    Set<int>? result = {-1};
    await open(tester, photo.future, (r) => result = r);
    await tester.tap(find.text('확인'));
    await tester.pumpAndSettle();
    photo.complete({0, 1, 2, 3});
    await tester.pumpAndSettle();
    expect(result, isEmpty);
    expect(gameStore.current!.scores, [25000, 25000, 25000, 25000]);
  });
}
