import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/table_reader.dart';
import 'package:mahjong_calc/ui/mount/read_progress_dialog.dart';

/// 판독 진행 창: 언제든 취소할 수 있고, 20초가 지나면 안내가 바뀌고 버튼이 강조된다.
void main() {
  Future<Completer<void>> open(WidgetTester tester, VoidCallback onCancel) async {
    final done = Completer<void>();
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (ctx) => TextButton(
          onPressed: () => showDialog<void>(
            context: ctx,
            barrierDismissible: false,
            builder: (_) => ReadProgressDialog(
              stage: ValueNotifier(ReadStage.reading),
              done: done.future,
              onCancel: onCancel,
            ),
          ),
          child: const Text('열기'),
        ),
      ),
    ));
    await tester.tap(find.text('열기'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    return done;
  }

  testWidgets('처음부터 취소 버튼이 있고, 누르면 알린다', (tester) async {
    var canceled = 0;
    final done = await open(tester, () => canceled++);
    expect(find.textContaining('보통 10~15초'), findsOneWidget);
    expect(find.widgetWithText(TextButton, '취소하고 직접 입력'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('read-cancel')));
    expect(canceled, 1);
    done.complete();
    await tester.pumpAndSettle();
    expect(find.byType(ReadProgressDialog), findsNothing);
  });

  testWidgets('20초가 지나면 안내가 바뀌고 버튼을 강조하지만, 저절로 닫히지는 않는다', (tester) async {
    var canceled = 0;
    final done = await open(tester, () => canceled++);
    for (var i = 0; i < 21; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(find.textContaining('평소보다 오래 걸립니다'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, '취소하고 직접 입력'), findsOneWidget);
    expect(find.byType(ReadProgressDialog), findsOneWidget);
    expect(canceled, 0);
    done.complete();
    await tester.pumpAndSettle();
  });
}
