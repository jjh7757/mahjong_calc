// 패보 재생 화면 리뷰 카드 아래의 mahjong-helper 참고값 묶음(lib/ui/paifu/review_view.dart EngineReviewBox).
// 엔진 계산은 화면에선 compute 로 뒤에서 돈다 — 위젯 시험에서는 PaifuScreen.engineReview 를 바꿔 끼워 결과를 손으로 넣는다.
// 문구 · 등급 칸은 test/paifu_review_ui_test.dart, 엔진 숫자 자체는 test/paifu_review_mh_test.dart 가 본다.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/paifu/review_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

Paifu _load(String name) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$name.json').readAsStringSync()) as Map<String, dynamic>);

const _card = ValueKey('paifu-review-card');
const _engine = ValueKey('paifu-review-engine');
const _pending = ValueKey('paifu-review-engine-pending');

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  // r19(손패 있음, hero 자리 1): 걸음 29 = 6번째 버림 4만(실수 · 위협 차례), 38 = 8번째 버림 3삭(리치 선언 · 텐파이),
  // 24 = 5번째 버림 2통(엔진 1위 5통과 값이 같음), 43 = 리치 뒤(forced).
  late Paifu r19;
  late PaifuReview r19Engine;
  setUpAll(() {
    r19 = _load('r19_142013');
    r19Engine = reviewPaifu(r19, withEngine: true);
  });

  TurnReview at(PaifuReview r, int step) => r.turns.firstWhere((t) => t.eventIndex + 1 == step);

  group('computeEngineReview (따로 도는 isolate)', () {
    test('r19: JSON 으로 넘겨 돌린 결과가 화면 스레드에서 바로 낸 것과 같음', () async {
      final got = await computeEngineReview(r19);
      expect(got.turns.length, r19Engine.turns.length);
      for (var i = 0; i < got.turns.length; i++) {
        final a = got.turns[i], b = r19Engine.turns[i];
        expect(a.status, b.status, reason: '${a.turn}번째 버림');
        expect(a.grade, b.grade);
        expect(a.mhBest, b.mhBest);
        expect(a.mhRankOfActual, b.mhRankOfActual);
        expect(a.mh?.length, b.mh?.length);
        expect(a.mhActualImprove, b.mhActualImprove);
        expect(a.riskSeats, b.riskSeats);
        expect(a.riskOfActual, b.riskOfActual);
        expect(a.minRiskTile, b.minRiskTile);
        expect(engineLines(a), engineLines(b));
      }
    });
  });

  group('참고값 문구', () {
    String seat(int s) => '자리$s';

    test('r19 걸음 29(실수 · 위협): 실제 버림 숫자 · 샹텐 지키는 추천 · 위험', () {
      final l = engineLines(at(r19Engine, 29), seatLabel: seat);
      expect(l, [
        '실제 버림 4만: 개량 뒤 유효패 평균 10.9장 · 속도 15.3 · 국수지 3132',
        '점수 · 화료까지 본 추천: 3만 (개량 뒤 유효패 평균 15.2장 · 속도 26.4)',
        '위협 자리: 자리0 · 이 패 방총 위험 약 1.7%',
        '가장 안전: 5통 (0.9%)',
      ]);
    });

    test('r19 걸음 38(텐파이): 화료율 · 리치 기준 기대 점수, 추천은 실제 버림과 같음', () {
      final l = engineLines(at(r19Engine, 38), seatLabel: seat);
      expect(l[0], '실제 버림 3삭: 개량 뒤 대기 평균 3.5장 · 화료율 33.3% · 기대 8276점(리치 기준) · 국수지 1755');
      expect(l[1], '점수 · 화료까지 본 추천: 실제 버림과 같음');
      expect(l[2], '위협 자리: 자리0 · 이 패 방총 위험 약 3.0%');
    });

    test('r19 걸음 24: 엔진 1위와 값이 모두 같으면 "값이 같음"', () {
      expect(engineRecommendLine(at(r19Engine, 24)), '점수 · 화료까지 본 추천: 5통 — 실제 버림과 값이 같음');
    });

    test('위협 없는 차례엔 위험 줄이 없음 · 엔진 없이 낸 평가엔 줄이 하나도 없음', () {
      expect(engineRiskLines(at(r19Engine, 4)), isEmpty);
      expect(engineLines(at(r19Engine, 4)), hasLength(2));
      for (final t in reviewPaifu(r19).turns) {
        expect(engineLines(t), isEmpty);
      }
    });

    test('후퇴 권장은 추천으로 보이지 않음: 추천 패는 늘 샹텐을 지키는 후보 1위', () {
      var backwardTurns = 0;
      for (final id in ['r11_130921', 'r12_131655', 'r17_140450', 'r19_142013']) {
        final r = id == 'r19_142013' ? r19Engine : reviewPaifu(_load(id), withEngine: true);
        for (final t in r.turns) {
          final line = engineRecommendLine(t);
          if (t.mh == null) {
            expect(line, isNull);
            continue;
          }
          final top = t.mh!.firstWhere((d) => !d.isBackward);
          if (t.mhRecommendBackward == true) {
            backwardTurns++;
            // 엔진 최선(후퇴 패)이 아니라 지키는 후보 1위를 말한다.
            expect(top.tile, isNot(t.mhBest), reason: '$id ${t.turn}번째 버림');
          }
          if (top.tile == t.discard.tile) {
            expect(line, '점수 · 화료까지 본 추천: 실제 버림과 같음');
          } else {
            expect(line, startsWith('점수 · 화료까지 본 추천: ${Tiles.name(top.tile)} '), reason: '$id ${t.turn}번째 버림');
            expect(line, isNot(contains('후퇴')));
          }
        }
      }
      expect(backwardTurns, greaterThan(0), reason: '후퇴 권장 차례가 하나는 있어야 이 시험이 뜻이 있다(r17)');
    });
  });

  group('재생 화면', () {
    late int calls;
    // 화면이 부를 때 만든다: setUp 에서 만든 Completer 는 가짜 시계 밖 구역이라 complete 해도 pump 로는 이어지지 않는다.
    Completer<PaifuReview>? done;

    Future<PaifuReview> runner(Paifu p) {
      calls++;
      return (done = Completer<PaifuReview>()).future;
    }

    setUp(() {
      calls = 0;
      done = null;
    });

    Future<void> pump(WidgetTester tester, Paifu p, {Size size = const Size(1280, 800), EngineReviewRunner? run}) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p, engineReview: run ?? runner)));
    }

    int step(WidgetTester tester) => tester.widget<Slider>(find.byType(Slider)).value.round();

    Future<void> goTo(WidgetTester tester, int target) async {
      while (step(tester) != target) {
        await tester.sendKeyEvent(step(tester) < target ? LogicalKeyboardKey.arrowRight : LogicalKeyboardKey.arrowLeft);
        await tester.pump();
      }
      await tester.pumpAndSettle();
    }

    Finder inEngine(String text) => find.descendant(of: find.byKey(_engine), matching: find.textContaining(text));

    testWidgets('r19: 첫 화면 뒤에 계산 시작 → "계산 중" → 결과가 오면 참고값 묶음', (tester) async {
      await pump(tester, r19);
      // 첫 프레임에서는 아직 부르지 않는다(웹에서 compute 가 같은 스레드라 첫 화면이 먼저 나와야 함).
      expect(calls, 0);
      await tester.pump(const Duration(milliseconds: 200));
      expect(calls, 1);

      await goTo(tester, 29);
      expect(find.byKey(_card), findsOneWidget);
      expect(find.byKey(_pending), findsOneWidget);
      expect(find.text(engineReviewPending), findsOneWidget);
      expect(find.byKey(_engine), findsNothing);

      done!.complete(r19Engine);
      await tester.pumpAndSettle();
      expect(find.byKey(_pending), findsNothing);
      expect(find.byKey(_engine), findsOneWidget);
      expect(inEngine(engineReviewTitle), findsOneWidget);
      expect(inEngine('통계표 어림'), findsOneWidget);
      expect(inEngine('실제 버림 4만: 개량 뒤 유효패 평균 10.9장 · 속도 15.3 · 국수지 3132'), findsOneWidget);
      expect(inEngine('점수 · 화료까지 본 추천: 3만'), findsOneWidget);
      // 위협 차례: 자리 표시는 재생 화면 그대로(바람 + 이름).
      expect(inEngine('위협 자리: 남 플레이어 1 · 이 패 방총 위험 약 1.7%'), findsOneWidget);
      expect(inEngine('가장 안전: 5통 (0.9%)'), findsOneWidget);
      // 등급 · 기존 카드 문구는 그대로.
      expect(find.descendant(of: find.byKey(_card), matching: find.textContaining('최선은 3만 → 15장 (5장 적음)')),
          findsOneWidget);
      expect(calls, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('r19: 텐파이 차례 · 리치 뒤(forced) 차례', (tester) async {
      await pump(tester, r19);
      await tester.pump(const Duration(milliseconds: 200));
      done!.complete(r19Engine);
      await tester.pumpAndSettle();

      await goTo(tester, 38);
      expect(inEngine('화료율 33.3%'), findsOneWidget);
      expect(inEngine('기대 8276점(리치 기준)'), findsOneWidget);
      expect(inEngine('점수 · 화료까지 본 추천: 실제 버림과 같음'), findsOneWidget);

      // 리치 뒤는 고를 수 없는 버림이라 참고값도 붙이지 않는다.
      await goTo(tester, 43);
      expect(find.byKey(_card), findsOneWidget);
      expect(find.byKey(_engine), findsNothing);
      expect(find.byKey(_pending), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('계산이 실패하면 "계산 중" 줄만 조용히 사라짐', (tester) async {
      await pump(tester, r19, run: (p) async {
        calls++;
        throw StateError('엔진 실패');
      });
      await tester.pump(const Duration(milliseconds: 200));
      await goTo(tester, 29);
      expect(calls, 1);
      expect(find.byKey(_card), findsOneWidget);
      expect(find.byKey(_pending), findsNothing);
      expect(find.byKey(_engine), findsNothing);
      expect(find.textContaining('엔진 실패'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('결과가 오기 전에 화면을 떠나면 결과를 버림', (tester) async {
      await pump(tester, r19);
      await tester.pump(const Duration(milliseconds: 200));
      expect(calls, 1);
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      done!.complete(r19Engine);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('첫 시작 전 화면을 떠나면 부르지도 않음', (tester) async {
      await pump(tester, r19);
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump(const Duration(seconds: 1));
      expect(calls, 0);
      expect(tester.takeException(), isNull);
    });

    testWidgets('손패 없는 판(r20): 계산하지 않고 묶음도 없음', (tester) async {
      final p = _load('r20_143236');
      await pump(tester, p);
      await tester.pump(const Duration(seconds: 1));
      expect(calls, 0);
      for (var i = 1; i < p.states.length; i++) {
        await goTo(tester, i);
        expect(find.byKey(_pending), findsNothing, reason: '걸음 $i');
        expect(find.byKey(_engine), findsNothing, reason: '걸음 $i');
      }
      expect(tester.takeException(), isNull);
    });

    testWidgets('폰 세로 400×800: 참고값이 들어와도 넘침 없음 · 스크롤하면 묶음이 다 보임', (tester) async {
      const size = Size(400, 800);
      await pump(tester, r19, size: size);
      await tester.pump(const Duration(milliseconds: 200));
      done!.complete(r19Engine);
      await tester.pumpAndSettle();
      var boxes = 0;
      for (var i = 1; i < r19.states.length; i++) {
        await goTo(tester, i);
        expect(tester.takeException(), isNull, reason: '걸음 $i');
        final box = find.byKey(_engine);
        if (box.evaluate().isEmpty) continue;
        boxes++;
        await tester.ensureVisible(box);
        await tester.pumpAndSettle();
        final scroll = tester.getRect(find.byKey(const ValueKey('paifu-panel-scroll')));
        final r = tester.getRect(box);
        expect(r.top, greaterThanOrEqualTo(scroll.top - 1), reason: '걸음 $i');
        expect(r.bottom, lessThanOrEqualTo(scroll.bottom + 1), reason: '걸음 $i');
        expect(r.right, lessThanOrEqualTo(size.width), reason: '걸음 $i');
        expect(tester.takeException(), isNull, reason: '걸음 $i');
      }
      expect(boxes, 8); // 숫자 있는 버림 10번 중 리치 뒤 2번을 뺀 것
    });
  });
}
