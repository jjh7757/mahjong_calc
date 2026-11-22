// 패보 복기 질문 창(설계서 docs/paifu_review_agent_app_design_1122.md 3절 · 6절 2단계): "질문" 단추 · 추천 질문 ·
// 차례 칩 · 기다리는 동안 잠금 · 실패와 "다시" · 대체 답 · "N순 보기" · 엔진 계산 기다렸다 보내기 · 이어 묻기 · 패보가 바뀌면 비움 ·
// 키 없는 빌드 · 단축키 · 배치. 서버는 부르지 않는다 — PaifuScreen.asker 에 가짜를 넣는다.
// 글(추천 질문 문구 · 차례 붙이기 · 답 조각)은 test/review_chat_test.dart, 서버 호출은 test/review_ask_client_test.dart.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

const _btn = ValueKey('paifu-ask-btn');
const _panel = ValueKey('paifu-ask-panel');
const _input = ValueKey('paifu-ask-input');
const _send = ValueKey('paifu-ask-send');
const _go = ValueKey('paifu-review-go');

/// 가짜 답 하나.
ReviewAnswer answer(String text, {bool verified = true, List<int> turns = const []}) => ReviewAnswer.fromJson({
  'answer': text,
  'outcome': verified ? 'verified' : 'fallback',
  'tool_calls': [
    for (final n in turns)
      {
        'name': 'turn_facts',
        'args': {'turn': n},
      },
  ],
})!;

/// 받은 부름 하나.
class AskCall {
  final Map<String, dynamic> facts;
  final String question;
  final List<ReviewExchange> history;
  AskCall(this.facts, this.question, this.history);
}

/// 가짜 asker. [reply] 가 없으면 바로 "답 N" 을 돌려준다. [hold] 면 부를 때 만든 Completer 에서 멈춘다
/// (setUp 에서 만든 Completer 는 가짜 시계 밖 구역이라 complete 해도 pump 로 이어지지 않는다).
class FakeAsker {
  final calls = <AskCall>[];
  Future<ReviewAnswer> Function(int index)? reply;
  bool hold = false;
  Completer<ReviewAnswer>? held;

  Future<ReviewAnswer> call({
    required Map<String, dynamic> facts,
    required String question,
    List<ReviewExchange> history = const [],
  }) {
    calls.add(AskCall(facts, question, history));
    final i = calls.length - 1;
    if (hold) return (held = Completer<ReviewAnswer>()).future;
    final r = reply;
    if (r != null) return r(i);
    return Future.value(answer('답 $i'));
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

  late FakeAsker fake;
  setUp(() => fake = FakeAsker());

  /// 엔진 참고값은 바로 끝나는 것으로(기본). 엔진을 기다리는 시험만 따로 넣는다.
  Future<PaifuReview> ready(Paifu p) async => identical(p, r19)
      ? r19Engine
      : identical(p, l16)
      ? l16Engine
      : reviewPaifu(p, withEngine: true);

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

  Future<void> startReview(WidgetTester tester) => tap(tester, const ValueKey('paifu-summary-start'));

  int step(WidgetTester tester) => tester.widget<ReviewBubble>(find.byType(ReviewBubble)).step;

  Future<void> goTo(WidgetTester tester, int target) async {
    // 방향키가 안 먹으면(입력 줄에 포커스) 끝없이 돌지 않게 걸음 수만큼만.
    for (var n = 0; step(tester) != target; n++) {
      expect(n, lessThan(100), reason: '방향키로 걸음 $target 에 못 감(지금 ${step(tester)})');
      await tester.sendKeyEvent(step(tester) < target ? LogicalKeyboardKey.arrowRight : LogicalKeyboardKey.arrowLeft);
      await tester.pump();
    }
    await tester.pumpAndSettle();
  }

  List<String> suggestions(WidgetTester tester) => [
    for (var i = 0; find.byKey(ValueKey('paifu-ask-suggest-$i')).evaluate().isNotEmpty; i++)
      (tester.widget<ActionChip>(find.byKey(ValueKey('paifu-ask-suggest-$i'))).label as Text).data!,
  ];

  String answerText(WidgetTester tester, int i) =>
      tester.widget<Text>(find.byKey(ValueKey('paifu-ask-answer-$i'))).textSpan!.toPlainText();

  Future<void> typeAndSend(WidgetTester tester, String text) async {
    await tester.enterText(find.byKey(_input), text);
    await tester.pump();
    await tap(tester, _send);
  }

  bool chipOn(WidgetTester tester, Key key) => tester.widget<FilterChip>(find.byKey(key)).selected;

  group('"질문" 단추 · 펼침', () {
    testWidgets('손패 있는 판의 복기 화면에 있고, 손패 없는 판(r20 재생 화면)에는 없음', (tester) async {
      await pump(tester, r19);
      await startReview(tester);
      expect(find.byKey(_btn), findsOneWidget);
      expect(find.byKey(_panel), findsNothing);

      // r20 재생 화면은 폰 세로에서 패널이 넘친다(질문 창과 무관한 기존 배치) — 기존 시험처럼 1280×800 에서 본다.
      await tester.pumpWidget(const SizedBox());
      await pump(tester, _load('r20_143236'), size: const Size(1280, 800));
      expect(find.byKey(const ValueKey('paifu-play')), findsOneWidget);
      expect(find.byKey(_btn), findsNothing);
      expect(find.byKey(_panel), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('켜면 질문 창 · 후보 참고값은 꺼짐, 후보를 켜면 질문 창이 닫힘, 닫기 단추', (tester) async {
      await pump(tester, r19);
      await startReview(tester);
      await goTo(tester, 29);
      await tap(tester, const ValueKey('paifu-fold-candidates-btn'));
      await tap(tester, const ValueKey('paifu-fold-engine-btn'));
      expect(find.byKey(const ValueKey('paifu-fold-candidates')), findsOneWidget);

      await tap(tester, _btn);
      expect(find.byKey(_panel), findsOneWidget);
      expect(chipOn(tester, _btn), isTrue);
      expect(chipOn(tester, const ValueKey('paifu-fold-candidates-btn')), isFalse);
      expect(chipOn(tester, const ValueKey('paifu-fold-engine-btn')), isFalse);
      expect(find.byKey(const ValueKey('paifu-fold-candidates')), findsNothing);
      expect(find.byKey(const ValueKey('paifu-fold-scroll')), findsNothing);

      await tap(tester, const ValueKey('paifu-fold-candidates-btn'));
      expect(find.byKey(_panel), findsNothing);
      expect(chipOn(tester, _btn), isFalse);
      expect(find.byKey(const ValueKey('paifu-fold-candidates')), findsOneWidget);

      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-close'));
      expect(find.byKey(_panel), findsNothing);
      expect(chipOn(tester, _btn), isFalse);
      expect(tester.takeException(), isNull);
    });
  });

  group('추천 질문 · 차례 칩', () {
    testWidgets('r19 6순(실수) → 등급 질문 둘, 내 버림 아닌 걸음 → 판 전체 질문, 누르면 그 글 그대로', (tester) async {
      await pump(tester, r19);
      await startReview(tester);
      await tap(tester, _btn);
      await goTo(tester, 29);
      expect(suggestions(tester), ['6순에 4만 버린 게 왜 실수야?', '6순에 3만을 버렸으면 어떻게 됐어?']);
      expect(tester.widget<FilterChip>(find.byKey(const ValueKey('paifu-ask-turn-chip'))).selected, isTrue);
      expect(find.text('6순에 대해'), findsOneWidget);

      await goTo(tester, 30);
      final game = suggestedQuestions(r19, r19Engine, null);
      expect(game.first, '이 판에서 제일 아까운 수는?');
      expect(suggestions(tester), game);
      expect(find.byKey(const ValueKey('paifu-ask-turn-chip')), findsNothing);

      await goTo(tester, 29);
      await tap(tester, const ValueKey('paifu-ask-suggest-1'));
      expect(fake.calls.map((c) => c.question), ['6순에 3만을 버렸으면 어떻게 됐어?']);
      expect(find.text('6순에 3만을 버렸으면 어떻게 됐어?'), findsWidgets); // 대화 목록 + 칩
      expect(answerText(tester, 0), '답 0');
      expect(tester.takeException(), isNull);
    });

    testWidgets('직접 쓴 글: 칩 켬 → "6순에 대해: " 붙임 · 끔 → 그대로 · "7순" 이 있으면 안 붙임 · 내 버림 아닌 걸음 → 그대로', (tester) async {
      await pump(tester, r19);
      await startReview(tester);
      await goTo(tester, 29);
      await tap(tester, _btn);

      await typeAndSend(tester, '이 수 어땠어?');
      expect(fake.calls.last.question, '6순에 대해: 이 수 어땠어?');
      expect(find.text('6순에 대해: 이 수 어땠어?'), findsOneWidget); // 붙인 글 그대로 보임
      expect(tester.widget<TextField>(find.byKey(_input)).controller!.text, isEmpty);

      await tap(tester, const ValueKey('paifu-ask-turn-chip'));
      expect(chipOn(tester, const ValueKey('paifu-ask-turn-chip')), isFalse);
      await typeAndSend(tester, '이 수 어땠어?');
      expect(fake.calls.last.question, '이 수 어땠어?');

      await tap(tester, const ValueKey('paifu-ask-turn-chip'));
      await typeAndSend(tester, '7순에 뭐가 나았어?');
      expect(fake.calls.last.question, '7순에 뭐가 나았어?');

      // 빈 글은 안 보낸다.
      await typeAndSend(tester, '   ');
      expect(fake.calls, hasLength(3));
      // 안 보냈으니 입력 줄에 포커스가 남아 방향키가 걸음을 안 옮긴다 — 빠져나온다.
      FocusManager.instance.primaryFocus!.unfocus();
      await tester.pumpAndSettle();

      // 칩 값은 걸음을 옮겨도 유지 — 끈 채로 다른 내 버림 걸음에 가도 꺼져 있음.
      await tap(tester, const ValueKey('paifu-ask-turn-chip'));
      await goTo(tester, 34);
      expect(chipOn(tester, const ValueKey('paifu-ask-turn-chip')), isFalse);
      expect(find.text('7순에 대해'), findsOneWidget);
      await tap(tester, const ValueKey('paifu-ask-turn-chip'));

      // 내 버림이 아닌 걸음: 칩 없음, 그대로. Enter(보내기 동작)로도 보낸다.
      await goTo(tester, 30);
      expect(find.byKey(const ValueKey('paifu-ask-turn-chip')), findsNothing);
      await tester.enterText(find.byKey(_input), '이 수 어땠어?');
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.pumpAndSettle();
      expect(fake.calls.last.question, '이 수 어땠어?');
      expect(fake.calls, hasLength(4));
      expect(tester.widget<TextField>(find.byKey(_input)).controller!.text, isEmpty);
      expect(tester.takeException(), isNull);
    });
  });

  group('상태', () {
    testWidgets('기다리는 동안: "답을 찾는 중… N초", 보내기 · 추천 질문 잠김, "다음" 은 됨, 답이 오면 굵은 패 이름', (tester) async {
      fake.hold = true;
      await pump(tester, r19);
      await startReview(tester);
      await goTo(tester, 29);
      await tap(tester, _btn);
      await tester.enterText(find.byKey(_input), '이 수 어땠어?');
      await tap(tester, _send);
      expect(fake.calls, hasLength(1));
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-ask-pending'))).data, '답을 찾는 중… 0초');
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-ask-pending'))).data, '답을 찾는 중… 2초');
      expect(tester.widget<TextField>(find.byKey(_input)).controller!.text, isEmpty);

      expect(tester.widget<IconButton>(find.byKey(_send)).onPressed, isNull);
      expect(tester.widget<ActionChip>(find.byKey(const ValueKey('paifu-ask-suggest-0'))).onPressed, isNull);
      await tester.tap(find.byKey(const ValueKey('paifu-ask-suggest-0')));
      await tester.enterText(find.byKey(_input), '또 물어');
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.tap(find.byKey(_send));
      await tester.pump();
      expect(fake.calls, hasLength(1));

      // 화면의 다른 단추는 그대로.
      await tester.tap(find.byKey(_go));
      await tester.pump();
      expect(step(tester), 34);
      expect(find.byKey(_panel), findsOneWidget);

      fake.held!.complete(answer("6순에 [3만]을 버렸다면 유효패가 15장이었다. 위험은 '낮음'이다."));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('paifu-ask-pending')), findsNothing);
      expect(answerText(tester, 0), '6순에 3만을 버렸다면 유효패가 15장이었다. 위험은 낮음이다.');
      final spans =
          (tester.widget<Text>(find.byKey(const ValueKey('paifu-ask-answer-0'))).textSpan! as TextSpan).children!;
      final bold = [
        for (final s in spans.cast<TextSpan>())
          if (s.style?.fontWeight == FontWeight.w700) s.text,
      ];
      expect(bold, ['3만', '낮음']);
      expect(find.byKey(const ValueKey('paifu-ask-fallback')), findsNothing);
      expect(find.byKey(const ValueKey('paifu-ask-norisk')), findsNothing);
      expect(tester.widget<IconButton>(find.byKey(_send)).onPressed, isNotNull);
      expect(tester.takeException(), isNull);
    });

    testWidgets('실패(요청이 많음) → 까닭 한 줄 + "다시", 다시 누르면 같은 글로 · 항목 하나인 채 답으로', (tester) async {
      fake.reply = (i) => i == 0
          ? Future.error(
              const ReviewAskException(
                ReviewAskError.rateLimited,
                '요청이 많습니다. 8초 뒤에 다시 시도하세요.',
                retryAfter: Duration(seconds: 8),
                statusCode: 429,
              ),
            )
          : Future.value(answer('다시 받은 답'));
      await pump(tester, r19);
      await startReview(tester);
      await goTo(tester, 29);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-ask-error'))).data, '요청이 많습니다. 8초 뒤에 다시 시도하세요.');
      expect(find.byKey(const ValueKey('paifu-ask-retry')), findsOneWidget);
      // 실패해도 보내기는 다시 열린다.
      expect(tester.widget<IconButton>(find.byKey(_send)).onPressed, isNotNull);

      await tap(tester, const ValueKey('paifu-ask-retry'));
      expect(fake.calls.map((c) => c.question), ['6순에 4만 버린 게 왜 실수야?', '6순에 4만 버린 게 왜 실수야?']);
      expect(find.byKey(const ValueKey('paifu-ask-error')), findsNothing);
      expect(answerText(tester, 0), '다시 받은 답');
      expect(find.byKey(const ValueKey('paifu-ask-q-0')), findsOneWidget);
      expect(find.byKey(const ValueKey('paifu-ask-q-1')), findsNothing);
      expect(find.byKey(const ValueKey('paifu-ask-answer-1')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('그 밖의 예외는 "질문에 실패했습니다."', (tester) async {
      fake.reply = (i) => Future.error(StateError('뭔가 깨짐'));
      await pump(tester, r19);
      await startReview(tester);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-ask-error'))).data, '질문에 실패했습니다.');
      expect(find.textContaining('뭔가 깨짐'), findsNothing);
    });

    testWidgets('대체 답 표시 · "N순 보기" 는 그 걸음으로(창은 연 채), 리뷰에 없는 차례는 칩 없음', (tester) async {
      fake.reply = (i) => Future.value(answer('[4만]은 실수였다.', verified: false, turns: [6, 99]));
      await pump(tester, r19);
      await startReview(tester);
      expect(step(tester), 0);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      expect(find.byKey(const ValueKey('paifu-ask-fallback')), findsOneWidget);
      expect(find.text('확인된 사실만 답했습니다'), findsOneWidget);
      expect(find.byKey(const ValueKey('paifu-ask-goto-6')), findsOneWidget);
      expect(find.text('6순 보기'), findsOneWidget);
      expect(find.byKey(const ValueKey('paifu-ask-goto-99')), findsNothing);

      await tap(tester, const ValueKey('paifu-ask-goto-6'));
      expect(step(tester), 29);
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-bubble-title'))).data, '4만 버림 · 실수');
      expect(tester.widget<ReviewStripItem>(find.byKey(const ValueKey('paifu-strip-29'))).current, isTrue);
      expect(find.byKey(_panel), findsOneWidget);
      // 대화 목록은 남고 추천 질문만 이 걸음 것으로.
      expect(answerText(tester, 0), '4만은 실수였다.');
      expect(suggestions(tester).first, '6순에 4만 버린 게 왜 실수야?');
      expect(tester.takeException(), isNull);
    });
  });

  group('엔진 참고값 기다리기', () {
    // L16 17순: 남이 리치한 차례 — 수비 칸(defense)은 엔진 리뷰에서만 채워진다.
    Map<String, dynamic> turnFacts(Map<String, dynamic> facts, int n) =>
        (facts['turns'] as List).cast<Map<String, dynamic>>().firstWhere((x) => x['turn'] == n);

    testWidgets('계산 중에 보내면 기다렸다가, 끝나면 엔진 리뷰의 사실표(수비 칸 있음)로 보냄', (tester) async {
      Completer<PaifuReview>? done;
      var engineCalls = 0;
      await pump(
        tester,
        l16,
        engine: (p) {
          engineCalls++;
          return (done = Completer<PaifuReview>()).future;
        },
      );
      expect(engineCalls, 1);
      await startReview(tester);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      expect(fake.calls, isEmpty);
      expect(find.byKey(const ValueKey('paifu-ask-wait-engine')), findsOneWidget);
      expect(find.text('참고값 계산이 끝나면 보냅니다'), findsOneWidget);
      // 기다리는 동안에도 잠금.
      expect(tester.widget<IconButton>(find.byKey(_send)).onPressed, isNull);
      await tester.pump(const Duration(seconds: 3));
      expect(fake.calls, isEmpty);

      done!.complete(l16Engine);
      await tester.pumpAndSettle();
      expect(fake.calls, hasLength(1));
      expect(turnFacts(fake.calls.single.facts, 17)['defense'], isNotNull);
      expect(turnFacts(fake.calls.single.facts, 17)['status'], 'defense');
      expect(find.byKey(const ValueKey('paifu-ask-wait-engine')), findsNothing);
      expect(answerText(tester, 0), '답 0');
      expect(find.byKey(const ValueKey('paifu-ask-norisk')), findsNothing);

      // 같은 리뷰면 사실표를 다시 만들지 않는다(같은 객체).
      await typeAndSend(tester, '이 판 어땠어?');
      expect(fake.calls, hasLength(2));
      expect(identical(fake.calls[0].facts, fake.calls[1].facts), isTrue);
      expect(tester.takeException(), isNull);
    });

    testWidgets('계산이 실패하면 지금 리뷰(수비 칸 없음)로 보내고 "방총 위험 정보 없이"', (tester) async {
      Completer<PaifuReview>? done;
      await pump(tester, l16, engine: (p) => (done = Completer<PaifuReview>()).future);
      await startReview(tester);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      expect(fake.calls, isEmpty);
      done!.completeError(StateError('엔진 실패'));
      await tester.pumpAndSettle();
      expect(fake.calls, hasLength(1));
      expect(turnFacts(fake.calls.single.facts, 17)['defense'], isNull);
      expect(find.byKey(const ValueKey('paifu-ask-norisk')), findsOneWidget);
      expect(find.text('방총 위험 정보 없이 답했습니다'), findsOneWidget);
      // 실패한 뒤에 보낸 질문도 같은 표시.
      await typeAndSend(tester, '이 판 어땠어?');
      expect(find.byKey(const ValueKey('paifu-ask-norisk')), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('이어 묻기: 성공한 질문 · 답만 순서대로(실패한 질문은 뺌)', (tester) async {
    fake.reply = (i) => i == 1
        ? Future.error(const ReviewAskException(ReviewAskError.upstream, '답을 만드는 모델 호출이 실패했습니다. 다시 시도하세요.'))
        : Future.value(answer('답 $i'));
    await pump(tester, r19);
    await startReview(tester); // 걸음 0: 차례 칩 없음 → 글 그대로
    await tap(tester, _btn);
    await typeAndSend(tester, '첫째');
    await typeAndSend(tester, '둘째');
    await typeAndSend(tester, '셋째');
    await typeAndSend(tester, '넷째');
    expect(fake.calls.map((c) => c.question), ['첫째', '둘째', '셋째', '넷째']);
    List<(String, String)> h(int i) => [for (final e in fake.calls[i].history) (e.q, e.a)];
    expect(h(0), isEmpty);
    expect(h(1), [('첫째', '답 0')]);
    expect(h(2), [('첫째', '답 0')]);
    expect(h(3), [('첫째', '답 0'), ('셋째', '답 2')]);
    expect(find.byKey(const ValueKey('paifu-ask-error')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  group('비우기', () {
    testWidgets('패보가 바뀌면 대화가 비고 창이 닫힘', (tester) async {
      await pump(tester, r19);
      await startReview(tester);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      expect(answerText(tester, 0), '답 0');

      await tester.pumpWidget(
        MaterialApp(
          home: PaifuScreen(paifu: l16, engineReview: ready, asker: fake.call),
        ),
      );
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      expect(find.byKey(_panel), findsNothing);
      expect(chipOn(tester, _btn), isFalse);
      await tap(tester, _btn);
      expect(find.byKey(const ValueKey('paifu-ask-answer-0')), findsNothing);
      expect(find.byKey(const ValueKey('paifu-ask-q-0')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('답을 기다리는 중에 패보가 바뀌면 늦게 온 답은 버림', (tester) async {
      fake.hold = true;
      await pump(tester, r19);
      await startReview(tester);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      final old = fake.held!;
      await tester.pumpWidget(
        MaterialApp(
          home: PaifuScreen(paifu: l16, engineReview: ready, asker: fake.call),
        ),
      );
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      old.complete(answer('옛 판의 답'));
      await tester.pumpAndSettle();
      await tap(tester, _btn);
      expect(find.text('옛 판의 답'), findsNothing);
      expect(find.byKey(const ValueKey('paifu-ask-pending')), findsNothing);
      // 잠금도 풀려 있다.
      expect(tester.widget<IconButton>(find.byKey(_send)).onPressed, isNotNull);
      expect(tester.takeException(), isNull);
    });

    testWidgets('답을 기다리는 중에 화면을 치워도 예외 · 남은 타이머 없음', (tester) async {
      fake.hold = true;
      await pump(tester, r19);
      await startReview(tester);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      fake.held!.complete(answer('늦은 답'));
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('키 없는 빌드(asker 없음 · dart-define 없음): 한 줄 알림, 추천 질문 · 입력 · 보내기 잠금', (tester) async {
    expect(ReviewConfig.isConfigured, isFalse, reason: '시험 환경엔 키가 없어야 이 시험이 뜻이 있다');
    await pump(tester, r19, withAsker: false);
    await startReview(tester);
    await goTo(tester, 29);
    await tap(tester, _btn);
    expect(find.byKey(const ValueKey('paifu-ask-nokey')), findsOneWidget);
    expect(find.text('이 빌드에는 서버 키가 없어 질문할 수 없습니다'), findsOneWidget);
    expect(tester.widget<TextField>(find.byKey(_input)).enabled, isFalse);
    expect(tester.widget<IconButton>(find.byKey(_send)).onPressed, isNull);
    expect(tester.widget<ActionChip>(find.byKey(const ValueKey('paifu-ask-suggest-0'))).onPressed, isNull);
    await tester.tap(find.byKey(const ValueKey('paifu-ask-suggest-0')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('paifu-ask-q-0')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('단축키: 입력 줄에 포커스가 있으면 ← → space 가 걸음 · 재생을 안 바꾸고 커서가 움직임, 빠져나오면 기존대로', (tester) async {
    await pump(tester, r19);
    await startReview(tester);
    await goTo(tester, 29);
    await tap(tester, _btn);
    await tester.tap(find.byKey(_input));
    await tester.enterText(find.byKey(_input), 'abc');
    await tester.pump();
    final ctl = tester.widget<TextField>(find.byKey(_input)).controller!;
    expect(ctl.selection, const TextSelection.collapsed(offset: 3));

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(step(tester), 29);
    expect(ctl.selection, const TextSelection.collapsed(offset: 2));
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(step(tester), 29);
    expect(ctl.selection, const TextSelection.collapsed(offset: 3));
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
    await tester.pump(const Duration(seconds: 3));
    expect(step(tester), 29);
    expect(find.byTooltip('멈춤'), findsNothing); // 재생이 켜지지 않음
    expect(ctl.text, 'abc');

    // 보내면 입력 줄에서 빠져나오고 방향키는 다시 걸음을 옮긴다.
    await tap(tester, _send);
    expect(fake.calls.single.question, '6순에 대해: abc');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(step(tester), 30);

    // 다시 입력 줄 → 닫기로 빠져나와도 같다.
    await tester.tap(find.byKey(_input));
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(step(tester), 30);
    await tap(tester, const ValueKey('paifu-ask-close'));
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(step(tester), 31);
    expect(tester.takeException(), isNull);
  });

  group('배치: 질문 창을 열고 답 하나가 있을 때 넘침 없음', () {
    const long =
        '6순에 [4만]을 버린 것은 실수였다. [3만]을 버렸다면 유효패가 15장으로 지금보다 5장 많았고, '
        "다음 순에 [2만] · [5만] · [3삭] · [4삭] · [8삭] 을 뽑아 1샹텐이 될 수 있었다. 위험은 '낮음'이었다.";
    for (final (name, size) in const [
      ('폰 세로 360×740', Size(360, 740)),
      ('폰 세로 400×800', Size(400, 800)),
      ('태블릿 가로 1280×800', Size(1280, 800)),
    ]) {
      testWidgets(name, (tester) async {
        fake.reply = (i) => Future.value(answer(long, verified: false, turns: [6, 7, 8]));
        await pump(tester, r19, size: size);
        await startReview(tester);
        await goTo(tester, 29);
        await tap(tester, _btn);
        await tap(tester, const ValueKey('paifu-ask-suggest-0'));
        await tap(tester, const ValueKey('paifu-ask-suggest-1'));
        expect(tester.takeException(), isNull);
        expect(answerText(tester, 1), isNot(contains('[')));

        final screen = Offset.zero & size;
        final panel = tester.getRect(find.byKey(_panel));
        final strip = tester.getRect(find.byKey(const ValueKey('paifu-strip')));
        final go = tester.getRect(find.byKey(_go));
        final btn = tester.getRect(find.byKey(_btn));
        final input = tester.getRect(find.byKey(_input));
        final send = tester.getRect(find.byKey(_send));
        // ignore: avoid_print
        print('$name: 다음 폭 ${go.width} · 질문 창 $panel');
        for (final r in [panel, strip, go, btn, input, send]) {
          expect(
            screen.contains(r.topLeft) && screen.contains(r.bottomRight - const Offset(0.01, 0.01)),
            isTrue,
            reason: '$r',
          );
        }
        expect(panel.bottom, lessThanOrEqualTo(strip.top + 1));
        expect(input.bottom, lessThanOrEqualTo(panel.bottom + 1));
        expect(strip.bottom, lessThanOrEqualTo(go.top + 1));
        expect(go.width, greaterThanOrEqualTo(100));
        if (size.width < size.height) {
          final sheet = tester.getRect(find.byKey(const ValueKey('paifu-ask-sheet')));
          expect(sheet.bottom, lessThanOrEqualTo(strip.top + 1));
          expect(sheet.overlaps(strip), isFalse);
          expect(sheet.overlaps(go), isFalse);
        }

        // 걸음을 옮겨도(내 버림 아닌 걸음 · 단계 걸음) 넘침 없음.
        for (final s in [30, 39, 53]) {
          await goTo(tester, s);
          expect(tester.takeException(), isNull, reason: '걸음 $s');
        }
      });
    }

    testWidgets('폰 세로 360×740 + 글자판(아래 300px): 입력 줄이 글자판 위에 보이고 넘침 없음', (tester) async {
      fake.reply = (i) => Future.value(answer(long));
      await pump(tester, r19, size: const Size(360, 740));
      await startReview(tester);
      await goTo(tester, 29);
      await tap(tester, _btn);
      await tap(tester, const ValueKey('paifu-ask-suggest-0'));
      await tester.tap(find.byKey(_input));
      tester.view.viewInsets = const FakeViewPadding(bottom: 300);
      addTearDown(tester.view.resetViewInsets);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      final input = tester.getRect(find.byKey(_input));
      final strip = tester.getRect(find.byKey(const ValueKey('paifu-strip')));
      expect(input.top, greaterThanOrEqualTo(0));
      expect(input.bottom, lessThanOrEqualTo(740 - 300));
      expect(tester.getRect(find.byKey(_panel)).bottom, lessThanOrEqualTo(strip.top + 1));
      // 글자판이 올라오면 추천 질문 줄은 숨긴다(높이가 모자람).
      expect(find.byKey(const ValueKey('paifu-ask-suggest')), findsNothing);
      expect(find.byKey(const ValueKey('paifu-ask-close')), findsOneWidget);
    });

    // 갤럭시탭 가로(논리 1280×800, 글자판 아래 약 375). PaifuScreen.build 가 kioskWrap 을 거치므로 이 크기에서는 기기처럼
    // 어두운 테마 + 글자 1.25배가 걸린다(아래에서 배율을 확인). 상태 표시줄이 있을 때(위 24)도 같은 단언.
    for (final (name, top) in const [('전체 화면', 0.0), ('상태 표시줄 위 24', 24.0)]) {
      testWidgets('태블릿 가로 1280×800 + 글자판(아래 375px, $name): 말풍선 · 수 띠를 숨겨 입력 줄 · 목록이 보이고 넘침 없음', (tester) async {
        fake.reply = (i) => Future.value(answer(long));
        const size = Size(1280, 800);
        const keyboard = 375.0;
        await pump(tester, r19, size: size);
        if (top > 0) tester.view.padding = FakeViewPadding(top: top);
        await tester.pumpAndSettle();
        await startReview(tester);
        await goTo(tester, 29);
        await tap(tester, _btn);
        await tap(tester, const ValueKey('paifu-ask-suggest-0'));
        await tester.tap(find.byKey(_input));
        await tester.pump();
        final editable = find.descendant(of: find.byKey(_input), matching: find.byType(EditableText));
        final before = tester.state<EditableTextState>(editable);
        tester.view.viewInsets = const FakeViewPadding(bottom: keyboard);
        addTearDown(tester.view.resetViewInsets);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(MediaQuery.textScalerOf(tester.element(find.byKey(_panel))).scale(10), closeTo(12.5, 1e-9));
        // 배치가 바뀌어도 입력 줄이 새로 만들어지지 않아 포커스를 잃지 않는다(기기에서는 포커스를 잃으면 글자판이 내려감).
        expect(identical(tester.state<EditableTextState>(editable), before), isTrue);
        expect(tester.widget<EditableText>(editable).focusNode.hasFocus, isTrue);

        final screen = Offset.zero & size;
        final panel = tester.getRect(find.byKey(_panel));
        final list = tester.getRect(find.byKey(const ValueKey('paifu-ask-list')));
        final input = tester.getRect(find.byKey(_input));
        final send = tester.getRect(find.byKey(_send));
        final go = tester.getRect(find.byKey(_go));
        final btn = tester.getRect(find.byKey(_btn));
        // ignore: avoid_print
        print('$name: 질문 창 $panel · 목록 $list · 입력 줄 $input · 보내기 $send · 다음 $go');
        for (final r in [panel, list, input, send, go, btn]) {
          expect(
            screen.contains(r.topLeft) && screen.contains(r.bottomRight - const Offset(0.01, 0.01)),
            isTrue,
            reason: '$r',
          );
        }
        expect(input.top, greaterThanOrEqualTo(top));
        expect(input.bottom, lessThanOrEqualTo(size.height - keyboard));
        for (final r in [input, send]) {
          expect(r.overlaps(go), isFalse, reason: '$r 가 다음 $go 와 겹침');
          expect(r.overlaps(btn), isFalse, reason: '$r 가 질문 단추 $btn 와 겹침');
        }
        expect(find.byKey(const ValueKey('paifu-strip')), findsNothing);
        expect(find.byKey(const ValueKey('paifu-ask-suggest')), findsNothing);
        expect(find.byKey(const ValueKey('paifu-ask-close')), findsOneWidget);
        expect(list.height, greaterThanOrEqualTo(80));

        // 글자판을 내리면 그대로 돌아온다.
        tester.view.resetViewInsets();
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.byKey(const ValueKey('paifu-strip')), findsOneWidget);
        expect(find.byType(ReviewBubble), findsOneWidget);
        expect(find.byKey(const ValueKey('paifu-ask-suggest')), findsOneWidget);
        expect(identical(tester.state<EditableTextState>(editable), before), isTrue);
      });
    }
  });
}
