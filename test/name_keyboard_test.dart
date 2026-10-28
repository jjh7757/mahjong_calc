import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/game_screen.dart';
import 'package:mahjong_calc/ui/name_keyboard.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 이름 칸의 앱 안 키보드: 두벌식 조합과, 칸을 누르면 패널이 떠서 터치만으로 이름이 바뀌는지.
void main() {
  String typed(String keys, [String initial = '']) {
    final c = NameComposer(initial);
    for (final k in keys.split('')) {
      c.type(k);
    }
    return c.text;
  }

  group('NameComposer', () {
    test('받침·모음 넘김', () {
      expect(typed('ㅎㅏㄴㄱㅡㄹ'), '한글');
      expect(typed('ㄱㅣㅁㅊㅓㄹㅅㅜ'), '김철수');
      expect(typed('ㅇㅏㄴㅏ'), '아나'); // ㄴ 받침이 다음 모음으로 넘어감
    });

    test('겹모음·겹받침', () {
      expect(typed('ㄱㅗㅏㅇ'), '광');
      expect(typed('ㄷㅏㄹㄱ'), '닭');
      expect(typed('ㄷㅏㄹㄱㅣ'), '달기'); // 겹받침 뒤 모음이면 뒤 자음만 넘어감
      expect(typed('ㄷㅏㄹㄱㅇㅣ'), '닭이');
      expect(typed('ㅇㅢ'), '의');
    });

    test('된소리는 받침이 안 되는 것, 홀자모, 영문·숫자 섞기', () {
      expect(typed('ㅇㅏㄸㅏ'), '아따');
      expect(typed('ㅋㅋ'), 'ㅋㅋ');
      expect(typed('ㅏㅏ'), 'ㅏㅏ');
      expect(typed('ㅁㅣㄴ2'), '민2');
      expect(typed('Kㅣ'), 'Kㅣ');
    });

    test('지우기는 키 하나씩, 원래 이름은 글자 하나씩', () {
      final c = NameComposer('철수');
      for (final k in 'ㅎㅏㄴ'.split('')) {
        c.type(k);
      }
      expect(c.text, '철수한');
      c.backspace();
      expect(c.text, '철수하');
      c.backspace();
      c.backspace();
      expect(c.text, '철수');
      c.backspace();
      expect(c.text, '철');
    });

    test('최대 길이', () {
      final c = NameComposer('a' * NameComposer.maxLength);
      expect(c.type('b'), isFalse);
      expect(c.text.length, NameComposer.maxLength);
    });
  });

  group('대국 시작 폼', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));
    tearDown(() {
      if (gameStore.current != null) gameStore.discardCurrent();
    });

    for (final size in const [Size(1280, 800), Size(480, 900)]) {
      testWidgets('이름 칸을 누르면 키보드 패널, 터치로 이름 변경 (${size.width.toInt()}×${size.height.toInt()})',
          (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(const MaterialApp(home: GameScreen()));
        await tester.pumpAndSettle();

        await tester.tap(find.byKey(const ValueKey('setup-name-0')));
        await tester.pumpAndSettle();
        expect(find.text('동가 이름'), findsOneWidget);

        // 기본 이름은 처음 누른 글자가 대신한다.
        for (final k in ['ㅁ', 'ㅣ', 'ㄴ', 'ㅅ', 'ㅜ']) {
          await tester.tap(find.text(k));
          await tester.pump();
        }
        expect(find.descendant(of: find.byKey(const ValueKey('name-kb-preview')), matching: find.text('민수')),
            findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('name-kb-done')));
        await tester.pumpAndSettle();

        final field = tester.widget<TextField>(find.byKey(const ValueKey('setup-name-0')));
        expect(field.controller!.text, '민수');
        expect(tester.testTextInput.isVisible, isFalse); // 기기 키보드는 안 뜬다
      });
    }

    testWidgets('취소하면 그대로', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: GameScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('setup-name-1')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('ㅋ'));
      await tester.tap(find.text('취소'));
      await tester.pumpAndSettle();
      final field = tester.widget<TextField>(find.byKey(const ValueKey('setup-name-1')));
      expect(field.controller!.text, '플레이어 2');
    });
  });
}
