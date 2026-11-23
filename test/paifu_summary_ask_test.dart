// 패보 복기 질문 창 다듬기(설계서 docs/paifu_review_agent_app_design_1122.md 3절):
// ① 판 요약 화면의 판 전체 질문 줄 — 칩을 누르면 복기 화면 첫 걸음으로 가서 질문 창을 열고 그 글 그대로 보냄.
// ② 단추 줄 칩 높이 — 좁은 폭(< 440)에서 가로 여백만 줄이고 높이는 넓은 폭과 같게.
// 서버는 부르지 않는다 — PaifuScreen.asker 에 가짜를 넣는다(test/paifu_ask_ui_test.dart 와 같은 방식).
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/paifu/review_chat.dart';
import 'package:mahjong_calc/services/review_ask_client.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/paifu/review_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

Paifu _load(String name) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$name.json').readAsStringSync()) as Map<String, dynamic>);

const _summary = ValueKey('paifu-summary');
const _askRow = ValueKey('paifu-summary-ask');
const _panel = ValueKey('paifu-ask-panel');
const _btn = ValueKey('paifu-ask-btn');
const _go = ValueKey('paifu-review-go');

/// 받은 질문 글만 모으는 가짜 asker. [hold] 면 답을 주지 않고 멈춘다.
class _FakeAsker {
  final questions = <String>[];
  bool hold = false;

  Future<ReviewAnswer> call({
    required Map<String, dynamic> facts,
    required String question,
    List<ReviewExchange> history = const [],
  }) {
    questions.add(question);
    if (hold) return Completer<ReviewAnswer>().future;
    return Future.value(ReviewAnswer.fromJson({'answer': '답 ${questions.length - 1}', 'outcome': 'verified'})!);
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  late Paifu r19;
  late PaifuReview r19Engine;
  late Paifu l16;
  late PaifuReview l16Engine;
  setUpAll(() {
    r19 = _load('r19_142013');
    r19Engine = reviewPaifu(r19, withEngine: true);
    l16 = _load('L16_135321');
    l16Engine = reviewPaifu(l16, withEngine: true);
  });

  late _FakeAsker fake;
  setUp(() => fake = _FakeAsker());

  Future<PaifuReview> ready(Paifu p) async => identical(p, r19) ? r19Engine : l16Engine;

  Future<void> pump(
    WidgetTester tester,
    Paifu p, {
    Size size = const Size(400, 800),
    EngineReviewRunner? engine,
    bool withAsker = true,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: PaifuScreen(paifu: p, engineReview: engine ?? ready, asker: withAsker ? fake.call : null),
      ),
    );
    await tester.pump();
    // 엔진 계산은 첫 화면 뒤 100ms 에 시작한다.
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pumpAndSettle();
  }

  Future<void> tap(WidgetTester tester, Key key) async {
    await tester.ensureVisible(find.byKey(key));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(key));
    await tester.pumpAndSettle();
  }

  List<String> summaryQuestions(WidgetTester tester) => [
    for (var i = 0; find.byKey(ValueKey('paifu-summary-ask-$i')).evaluate().isNotEmpty; i++)
      (tester.widget<ActionChip>(find.byKey(ValueKey('paifu-summary-ask-$i'))).label as Text).data!,
  ];

  String answerText(WidgetTester tester, int i) =>
      tester.widget<Text>(find.byKey(ValueKey('paifu-ask-answer-$i'))).textSpan!.toPlainText();

  int step(WidgetTester tester) => tester.widget<ReviewBubble>(find.byType(ReviewBubble)).step;

  group('요약 화면의 판 전체 질문', () {
    testWidgets('asker 가 있으면 판 전체 질문 칩(r19 · L16), 글은 suggestedQuestions(p, r, null) 그대로, 배울 장면 아래 · 복기 시작 위',
        (tester) async {
      for (final (p, r) in [(r19, r19Engine), (l16, l16Engine)]) {
        await tester.pumpWidget(const SizedBox());
        await pump(tester, p);
        expect(find.byKey(_summary), findsOneWidget);
        expect(find.byKey(_askRow), findsOneWidget);
        final game = suggestedQuestions(p, r, null);
        expect(game, isNotEmpty);
        expect(summaryQuestions(tester), game);
        expect(game.first, '이 판에서 제일 아까운 수는?');
        expect(find.text('누르면 복기 화면의 질문 창에서 답합니다.'), findsOneWidget);

        final row = tester.getRect(find.byKey(_askRow));
        final start = tester.getRect(find.byKey(const ValueKey('paifu-summary-start')));
        final lessonTitle = tester.getRect(find.text('배울 장면'));
        expect(row.top, greaterThan(lessonTitle.bottom));
        expect(row.bottom, lessThanOrEqualTo(start.top));
        expect(tester.takeException(), isNull);
      }
      // L16 은 남 리치가 있어 세 번째 질문이 붙는다.
      expect(summaryQuestions(tester), hasLength(3));
      expect(summaryQuestions(tester).last, endsWith(' 리치 뒤에 나는 어떻게 했어?'));
    });

    testWidgets('칩을 누르면 복기 화면 첫 걸음 + 질문 창이 열리고 그 글 그대로 보냄(차례 안 붙임), 답이 창에, 글자판 안 뜸',
        (tester) async {
      await pump(tester, r19);
      final q = summaryQuestions(tester)[1];
      await tap(tester, const ValueKey('paifu-summary-ask-1'));

      expect(find.byKey(_summary), findsNothing);
      expect(find.byKey(_go), findsOneWidget);
      expect(step(tester), 0);
      expect(find.byKey(_panel), findsOneWidget);
      expect(tester.widget<FilterChip>(find.byKey(_btn)).selected, isTrue);
      expect(fake.questions, [q]);
      expect(fake.questions.single, isNot(contains('순에 대해')));
      expect(answerText(tester, 0), '답 0');
      expect(tester.testTextInput.isVisible, isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('엔진 계산 중에 누르면 창은 열리고, 계산이 끝난 뒤 그 글로 보냄', (tester) async {
      Completer<PaifuReview>? done;
      await pump(tester, l16, engine: (p) => (done = Completer<PaifuReview>()).future);
      final q = summaryQuestions(tester)[0];
      await tap(tester, const ValueKey('paifu-summary-ask-0'));
      expect(find.byKey(_panel), findsOneWidget);
      expect(fake.questions, isEmpty);
      expect(find.byKey(const ValueKey('paifu-ask-wait-engine')), findsOneWidget);

      done!.complete(l16Engine);
      await tester.pumpAndSettle();
      expect(fake.questions, [q]);
      expect(answerText(tester, 0), '답 0');
      expect(tester.takeException(), isNull);
    });

    testWidgets('앞 답을 기다리는 중(busy)이면 요약에서 누른 질문은 안 보내고 창만 열림', (tester) async {
      fake.hold = true;
      await pump(tester, r19);
      await tap(tester, const ValueKey('paifu-summary-ask-0'));
      expect(fake.questions, hasLength(1));
      // 요약으로 돌아가 다른 질문을 누름.
      await tap(tester, const ValueKey('paifu-open-summary'));
      expect(find.byKey(_summary), findsOneWidget);
      await tap(tester, const ValueKey('paifu-summary-ask-1'));
      expect(find.byKey(_panel), findsOneWidget);
      expect(fake.questions, hasLength(1));
      expect(tester.takeException(), isNull);
      // 멈춘 답의 타이머를 치운다.
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
    });

    testWidgets('asker 도 서버 설정도 없으면(키 없는 빌드) 요약 화면에 질문 줄 없음', (tester) async {
      expect(ReviewConfig.isConfigured, isFalse, reason: '시험 환경엔 키가 없어야 이 시험이 뜻이 있다');
      await pump(tester, r19, withAsker: false);
      expect(find.byKey(_summary), findsOneWidget);
      expect(find.byKey(_askRow), findsNothing);
      expect(find.byKey(const ValueKey('paifu-summary-ask-0')), findsNothing);
      expect(find.byKey(const ValueKey('paifu-summary-start')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    for (final size in const [Size(400, 800), Size(360, 740)]) {
      testWidgets('${size.width.toInt()}×${size.height.toInt()}: 질문 줄이 있어도 요약 화면 넘침 없음, 칩 · 복기 시작이 화면 폭 안',
          (tester) async {
        await pump(tester, l16, size: size);
        expect(tester.takeException(), isNull);
        final screen = Offset.zero & size;
        for (final key in [
          _askRow,
          const ValueKey('paifu-summary-ask-0'),
          const ValueKey('paifu-summary-ask-1'),
          const ValueKey('paifu-summary-ask-2'),
          const ValueKey('paifu-summary-start'),
          const ValueKey('paifu-summary-play'),
        ]) {
          await tester.ensureVisible(find.byKey(key));
          await tester.pumpAndSettle();
          final r = tester.getRect(find.byKey(key));
          expect(r.left, greaterThanOrEqualTo(0), reason: '$key $r');
          expect(r.right, lessThanOrEqualTo(screen.right), reason: '$key $r');
          expect(screen.contains(r.topLeft) && screen.contains(r.bottomRight - const Offset(0.01, 0.01)), isTrue,
              reason: '$key $r');
        }
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('단추 줄 칩 높이', () {
    const chips = [
      ValueKey('paifu-best-view'),
      ValueKey('paifu-fold-candidates-btn'),
      ValueKey('paifu-fold-engine-btn'),
      ValueKey('paifu-ask-btn'),
    ];

    /// 복기 화면 단추 줄의 칩 높이들 · 좁은 여백인가 · "다음" 폭.
    Future<(List<double>, bool, double)> measure(WidgetTester tester, Size size) async {
      await tester.pumpWidget(const SizedBox());
      await pump(tester, r19, size: size);
      await tap(tester, const ValueKey('paifu-summary-start'));
      expect(tester.takeException(), isNull);
      final heights = [for (final k in chips) tester.getSize(find.byKey(k)).height];
      final tight = tester.widget<FilterChip>(find.byKey(chips.first)).padding != null;
      final go = tester.getSize(find.byKey(_go)).width;
      return (heights, tight, go);
    }

    // 기준은 같은 글자 배율끼리: 폰 세로(배율 1)는 800×1280 세로, 가로 1280×800 은 키오스크 배치(kioskWrap 글자 1.25 배)라
    // 같은 키오스크 배치에서 단추 줄이 440 이상 되는 1600×900 가로.
    for (final (name, wideSize, narrow) in const [
      ('폰 세로 400×800 · 360×740 (기준 800×1280 세로)', Size(800, 1280), [Size(400, 800), Size(360, 740)]),
      ('가로 1280×800 오른쪽 패널 (기준 키오스크 1600×900 가로)', Size(1600, 900), [Size(1280, 800)]),
    ]) {
      testWidgets('$name: 좁은 여백 칩 높이가 넓은 폭과 같고 "다음" ≥ 100', (tester) async {
        final (wide, wideTight, _) = await measure(tester, wideSize);
        expect(wideTight, isFalse, reason: '$wideSize 는 단추 줄이 440 이상이어야 기준이 된다');
        expect(wide.toSet(), hasLength(1));
        for (final size in narrow) {
          final (h, tight, go) = await measure(tester, size);
          // ignore: avoid_print
          print('$size: 칩 높이 $h (넓은 폭 $wideSize ${wide.first}) · 좁은 여백 $tight · 다음 폭 $go');
          expect(tight, isTrue, reason: '$size 는 단추 줄이 440 보다 좁아야 한다');
          expect(h, wide, reason: '$size');
          expect(go, greaterThanOrEqualTo(100), reason: '$size');
        }
      });
    }
  });
}
