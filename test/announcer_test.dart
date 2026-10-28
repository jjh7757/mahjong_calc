import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/services/announcer.dart';
import 'package:mahjong_calc/services/voice_lines.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:mahjong_calc/ui/settings_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 결과 화면이 읽는 순서 그대로(론·쯔모 제외): 역들, 끝에 등급.
String resultSpeech(ScoreResult r) =>
    [for (final y in r.yaku) yakuSpeech(y), gradeSpeech(r)].where((s) => s.isNotEmpty).join(', ');

void main() {
  group('결과 음성 문장', () {
    test('역을 순서대로, 도라는 장 수, 끝에 등급', () {
      // 리치·쯔모·핑후·탕야오·이페코·도라 2 = 7판 하네만
      final r = calculate(
        Hand.parse('223344m567p67s55s 8s'),
        Situation(isTsumo: true, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('1m')]),
      );
      expect(r.limit, Limit.haneman);
      expect(resultSpeech(r), '리치, 멘젠 쯔모, 탕야오, 핑후, 이페코, 도라 2, 하네만');
    });

    test('등급이 없으면 역만 읽고, 도라 1장은 숫자 없이', () {
      final r = calculate(
        Hand.parse('123m456p789s23m55p 4m'),
        Situation(isTsumo: false, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('3m')]),
      );
      expect(resultSpeech(r), '리치, 핑후, 도라');
    });

    test('역만은 이름 뒤에 역만', () {
      final r = calculate(
        Hand.parse('555z666z777z123m4p 4p'),
        Situation(isTsumo: false, seatWind: Tiles.south),
      );
      expect(resultSpeech(r), '대삼원, 역만');
    });

    test('화료 형태가 아니면 읽지 않음', () {
      final r = calculate(Hand.parse('123m456p789s1234m 5m'), Situation(isTsumo: false, seatWind: Tiles.south));
      expect(resultSpeech(r), '');
    });
  });

  group('결과 화면 음성 연출', () {
    // 리치·쯔모·탕야오·핑후·이페코·도라 2 = 하네만
    final haneman = calculate(
      Hand.parse('223344m567p67s55s 8s'),
      Situation(isTsumo: true, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('1m')]),
    );
    late _FakeTts tts;
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      tts = _FakeTts()..install();
    });

    testWidgets('쯔모를 외치고, 역을 하나씩 다 읽어야 다음 줄, 끝에 등급', (tester) async {
      await tester.pumpWidget(MaterialApp(home: ResultScreen(result: haneman, isTsumo: true)));
      await tester.pump();
      expect(tts.spoken, ['쯔모']);
      // 다 읽기 전에는 아무리 기다려도 다음 말로 넘어가지 않는다.
      await tester.pump(const Duration(seconds: 2));
      expect(tts.spoken, ['쯔모']);
      for (var i = 0; i < haneman.yaku.length + 1; i++) {
        await tts.finish(tester);
      }
      expect(tts.spoken, ['쯔모', '리치', '멘젠 쯔모', '탕야오', '핑후', '이페코', '도라 2', '하네만']);
      await tts.finish(tester);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('result-stamp')), findsOneWidget);
    });

    testWidgets('누르면 읽기를 멈추고 등급만 읽는다', (tester) async {
      await tester.pumpWidget(MaterialApp(home: ResultScreen(result: haneman, isTsumo: true)));
      await tester.pump();
      await tts.finish(tester); // 쯔모 → 리치
      expect(tts.spoken.last, '리치');
      await tester.tap(find.text('리치'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      expect(tts.spoken, ['쯔모', '리치', '하네만']);
      await tts.finish(tester);
      await tester.pumpAndSettle();
      expect(tts.spoken, ['쯔모', '리치', '하네만']);
    });

    testWidgets('결과 음성을 끄면 읽지 않고 원래 시간표대로', (tester) async {
      SharedPreferences.setMockInitialValues({'voice.result': false});
      await tester.pumpWidget(MaterialApp(home: ResultScreen(result: haneman, isTsumo: true)));
      await tester.pumpAndSettle();
      expect(tts.spoken, isEmpty);
      expect(find.byKey(const ValueKey('result-stamp')), findsOneWidget);
    });
  });

  group('미리 만든 음성 파일', () {
    test('목소리마다 읽을 말 전부의 mp3 가 있고 pubspec 에 폴더가 있다, lines.json 은 코드 목록과 같다', () {
      final pubspec = File('pubspec.yaml').readAsStringSync();
      for (final v in voiceChoices.keys) {
        expect(pubspec, contains('- assets/voice/$v/'), reason: v);
        for (final k in voiceLines.keys) {
          expect(File('assets/voice/$v/$k.mp3').existsSync(), isTrue, reason: '$v/$k');
        }
      }
      final json = jsonDecode(File('assets/voice/lines.json').readAsStringSync());
      expect(json, voiceLines, reason: 'dart run tool/voice_lines.dart 로 다시 뽑을 것');
    });

    testWidgets('파일이 있으면 TTS 대신 파일을 차례로 튼다', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final tts = _FakeTts()..install();
      final played = <String>[];
      Announcer.playClip = (k) async {
        played.add(k);
        return true;
      };
      final r = calculate(
        Hand.parse('223344m567p67s55s 8s'),
        Situation(isTsumo: true, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('1m')]),
      );
      await tester.pumpWidget(MaterialApp(home: ResultScreen(result: r, isTsumo: true)));
      await tester.pumpAndSettle();
      expect(played, [
        'call_tsumo', 'yaku_riichi', 'yaku_menzenTsumo', 'yaku_tanyao', 'yaku_pinfu', 'yaku_iipeikou', 'dora_2', //
        'grade_haneman',
      ].map((k) => 'Kore/$k'));
      expect(tts.spoken, isEmpty);
    });

    testWidgets('룰 설정에서 목소리를 고르면 저장하고 그 목소리로 미리 읽는다, 기기 음성은 TTS', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final tts = _FakeTts()..install();
      final played = <String>[];
      Announcer.playClip = (k) async {
        played.add(k);
        return true;
      };
      await tester.pumpWidget(MaterialApp(home: SettingsScreen(editor: HandEditor())));
      await tester.pumpAndSettle();
      expect(tester.widget<ChoiceChip>(find.byKey(const ValueKey('voice-Kore'))).selected, isTrue);

      await tester.tap(find.byKey(const ValueKey('voice-Puck')));
      await tester.pumpAndSettle();
      expect(await Announcer.voice(), 'Puck');
      expect(played, ['call_tsumo', 'yaku_riichi', 'yaku_iipeikou', 'dora_2', 'grade_haneman'].map((k) => 'Puck/$k'));

      await tester.ensureVisible(find.byKey(const ValueKey('voice-tts')));
      await tester.tap(find.byKey(const ValueKey('voice-tts')));
      await tester.pump();
      await tester.pump();
      expect(await Announcer.voice(), deviceVoice);
      expect(tts.spoken, ['쯔모']);
      expect(played.length, 5); // 기기 음성은 파일을 안 튼다
      for (var i = 0; i < 5; i++) {
        await tts.finish(tester);
      }
      expect(tts.spoken, ['쯔모', '리치', '이페코', '도라 2', '하네만']);
    });
  });
}

/// 기기 TTS 대신 읽은 말을 모으고, [finish] 를 불러야 다 읽은 것으로 친다(Android 처럼 stop 도 끝냄).
class _FakeTts {
  final spoken = <String>[];
  Completer<void>? _pending;

  void install() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('flutter_tts'), (call) async {
      if (call.method == 'speak') {
        spoken.add(call.arguments as String);
        _pending = Completer();
        await _pending!.future;
      } else if (call.method == 'stop') {
        _done();
      }
      return 1;
    });
  }

  void _done() {
    if (_pending?.isCompleted == false) _pending!.complete();
  }

  Future<void> finish(WidgetTester tester) async {
    _done();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
  }
}

