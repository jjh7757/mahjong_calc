// 패보 복기 화면의 mahjong-helper 참고값(lib/ui/paifu/review_view.dart EngineReviewFold — 11-21 부터 "참고값" 단추로 펼침,
// 세 줄 + "자세히" 후보 표, 설계서 docs/paifu_review_ui_design_1121.md 3-9).
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

const _engine = ValueKey('paifu-review-engine');
const _pending = ValueKey('paifu-review-engine-pending');

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  // r19(손패 있음, hero 자리 1): 걸음 29 = 6번째 버림 4만(실수 · 위협 차례), 39 = 8번째 버림 3삭(리치 선언 · 텐파이),
  // 23 = 5번째 버림 2통(엔진 1위 5통과 값이 같음), 44 = 리치 뒤(forced).
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
        '실제 버림 4만: 개량 뒤 유효패 평균 10.8장 · 속도 15.5 · 국수지 3132',
        '점수 · 화료까지 본 추천: 3만 (개량 뒤 유효패 평균 15.2장 · 속도 26.8)',
        // 위험 % 는 화면 보정값(울기 위협만 C 표, lib/engine/risk_calibration.dart — 11-23): 엔진 1.85 → 2.1, 5통 0.95 → 0.9.
        '위협 자리: 자리0 · 이 패 방총 위험 약 2.1%',
        '가장 안전: 5통 (0.9%)',
      ]);
    });

    test('r19 걸음 39(텐파이): 화료율 · 리치 기준 기대 점수, 추천은 실제 버림과 같음', () {
      final l = engineLines(at(r19Engine, 39), seatLabel: seat);
      expect(l[0], '실제 버림 3삭: 개량 뒤 대기 평균 3.4장 · 화료율 33.3% · 기대 8276점(리치 기준) · 국수지 1755');
      expect(l[1], '점수 · 화료까지 본 추천: 실제 버림과 같음');
      expect(l[2], '위협 자리: 자리0 · 이 패 방총 위험 약 3.3%'); // 엔진 3.47 → C 표 보정 3.3(11-23)
    });

    test('r19 걸음 23: 엔진 1위와 값이 모두 같으면 "값이 같음"', () {
      expect(engineRecommendLine(at(r19Engine, 23)), '점수 · 화료까지 본 추천: 5통 — 실제 버림과 값이 같음');
    });

    test('위협 없는 차례엔 위험 줄이 없음 · 엔진 없이 낸 평가엔 줄이 하나도 없음', () {
      // 걸음 4(1순)는 짐작 손패(guessed)라 엔진 칸이 없다 — 숫자 있는 첫 차례인 걸음 9(2순, 위협 없음)로 본다.
      expect(at(r19Engine, 9).status, ReviewStatus.graded);
      expect(engineRiskLines(at(r19Engine, 9)), isEmpty);
      expect(engineLines(at(r19Engine, 9)), hasLength(2));
      for (final t in reviewPaifu(r19).turns) {
        expect(engineLines(t), isEmpty);
      }
    });

    test('참고값 세 줄(engineFoldLines): 추천은 말풍선의 최선(동률 포함)과 같으면 그렇게 적고, 위협 없으면 추천 한 줄', () {
      // 걸음 29: 최선 3만(또는 3삭), 엔진 추천 3만 · 위협 자리 0 · 방총 2.1%(보정값) · 가장 안전 5통(위 engineLines 시험과 같은 값).
      expect(engineFoldLines(at(r19Engine, 29), seatLabel: seat), [
        '점수 · 화료까지 본 추천: 3만 — 말풍선의 최선과 같음',
        '이 패 방총 위험: 약 2.1% (위협: 자리0)',
        '가장 안전한 패: 5통',
      ]);
      // 걸음 23: 최선 2통(또는 5통), 엔진 추천 5통.
      expect(engineFoldLines(at(r19Engine, 23)).first, '점수 · 화료까지 본 추천: 5통 — 말풍선의 최선과 같음');
      // 걸음 9(2번째 버림 동): 위협 없음 → 추천 한 줄.
      expect(engineFoldLines(at(r19Engine, 9)), hasLength(1));
      // 짐작 손패 차례(걸음 4)는 엔진 순위가 없다.
      expect(at(r19Engine, 4).mh, isNull);
      expect(engineFoldLines(at(r19Engine, 4)), isEmpty);
    });

    test('"자세히" 표 머리: 텐파이 후보가 있으면 화료율, 위협이 있으면 방총 위험', () {
      expect(EngineCandidateTable.headOf(at(r19Engine, 29)), ['버릴 패', '샹텐', '유효패', '개량 뒤 평균', '방총 위험', '국수지']);
      expect(EngineCandidateTable.headOf(at(r19Engine, 39)),
          ['버릴 패', '샹텐', '유효패', '개량 뒤 평균', '화료율', '방총 위험', '국수지']);
      expect(EngineCandidateTable.headOf(at(r19Engine, 9)), ['버릴 패', '샹텐', '유효패', '개량 뒤 평균', '국수지']);
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

  group('복기 화면 "참고값" 펼침', () {
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

    /// 요약 → 복기 시작 → 참고값 펼침.
    Future<void> openFold(WidgetTester tester) async {
      await tester.pump();
      await tester.ensureVisible(find.byKey(const ValueKey('paifu-summary-start')));
      await tester.tap(find.byKey(const ValueKey('paifu-summary-start')));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('paifu-fold-engine-btn')));
      await tester.pump();
    }

    int step(WidgetTester tester) => tester.widget<ReviewBubble>(find.byType(ReviewBubble)).step;

    Future<void> goTo(WidgetTester tester, int target) async {
      while (step(tester) != target) {
        await tester.sendKeyEvent(step(tester) < target ? LogicalKeyboardKey.arrowRight : LogicalKeyboardKey.arrowLeft);
        await tester.pump();
      }
      await tester.pumpAndSettle();
    }

    Finder inEngine(String text) => find.descendant(of: find.byKey(_engine), matching: find.textContaining(text));

    testWidgets('r19: 첫 화면 뒤에 계산 시작 → "계산 중" → 결과가 오면 세 줄(추천 · 방총 위험 · 가장 안전)', (tester) async {
      await pump(tester, r19);
      // 첫 프레임에서는 아직 부르지 않는다(웹에서 compute 가 같은 스레드라 첫 화면이 먼저 나와야 함).
      expect(calls, 0);
      await tester.pump(const Duration(milliseconds: 200));
      expect(calls, 1);

      await openFold(tester);
      await goTo(tester, 29);
      expect(find.byKey(_pending), findsOneWidget);
      expect(find.text(engineReviewPending), findsOneWidget);

      done!.complete(r19Engine);
      await tester.pumpAndSettle();
      expect(find.byKey(_pending), findsNothing);
      expect(inEngine(engineFoldTitle), findsOneWidget);
      // 자리 표시는 재생 화면 그대로(바람 + 이름).
      expect(inEngine('점수 · 화료까지 본 추천: 3만 — 말풍선의 최선과 같음'), findsOneWidget);
      expect(inEngine('이 패 방총 위험: 약 2.1% (위협: 남 플레이어 1)'), findsOneWidget);
      expect(inEngine('가장 안전한 패: 5통'), findsOneWidget);
      // 개량 뒤 평균 · 속도 · 국수지는 "자세히" 안으로.
      expect(inEngine('개량 뒤'), findsNothing);
      expect(inEngine('국수지'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('paifu-engine-detail')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('paifu-engine-table')), findsOneWidget);
      expect(inEngine('개량 뒤 평균'), findsOneWidget);
      expect(inEngine('4만 (실제)'), findsOneWidget);
      // 표의 "방총 위험" 칸도 보정값(4만 엔진 1.85 → 2.1%, 5통 0.95 → 0.9% — 0.9% 칸은 5통 말고도 있음).
      expect(find.descendant(of: find.byKey(const ValueKey('paifu-engine-table')), matching: find.text('2.1%')), findsOneWidget);
      expect(find.descendant(of: find.byKey(const ValueKey('paifu-engine-table')), matching: find.text('0.9%')), findsWidgets);
      // 말풍선(등급)은 그대로.
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-bubble-title'))).data, '4만 버림 · 실수');
      expect(calls, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('r19: 텐파이 차례(화료율 열) · 리치 뒤(forced)는 참고값 없음', (tester) async {
      await pump(tester, r19);
      await tester.pump(const Duration(milliseconds: 200));
      done!.complete(r19Engine);
      await tester.pumpAndSettle();
      await openFold(tester);

      await goTo(tester, 39);
      expect(inEngine('점수 · 화료까지 본 추천: 3삭 — 말풍선의 최선과 같음'), findsOneWidget);
      expect(inEngine('이 패 방총 위험: 약 3.3%'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('paifu-engine-detail')));
      await tester.pumpAndSettle();
      expect(inEngine('화료율'), findsOneWidget);

      await goTo(tester, 44);
      expect(inEngine('이 걸음은 참고값이 없습니다'), findsOneWidget);
      expect(find.byKey(_pending), findsNothing);
      expect(find.byKey(const ValueKey('paifu-engine-detail')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('계산이 실패하면 "계산 중" 줄만 조용히 사라짐', (tester) async {
      await pump(tester, r19, run: (p) async {
        calls++;
        throw StateError('엔진 실패');
      });
      await tester.pump(const Duration(milliseconds: 200));
      await openFold(tester);
      await goTo(tester, 29);
      expect(calls, 1);
      expect(find.byKey(_pending), findsNothing);
      expect(inEngine('이 걸음은 참고값이 없습니다'), findsOneWidget);
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

    testWidgets('손패 없는 판(r20): 계산하지 않고 재생 화면엔 참고값이 없음', (tester) async {
      final p = _load('r20_143236');
      await pump(tester, p);
      await tester.pump(const Duration(seconds: 1));
      expect(calls, 0);
      expect(find.byKey(_pending), findsNothing);
      expect(find.byKey(_engine), findsNothing);
      expect(find.byKey(const ValueKey('paifu-fold-engine-btn')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('폰 세로 400×800: 참고값 · 자세히를 펼쳐도 넘침 없음, 시트는 수 띠 위', (tester) async {
      const size = Size(400, 800);
      await pump(tester, r19, size: size);
      await tester.pump(const Duration(milliseconds: 200));
      done!.complete(r19Engine);
      await tester.pumpAndSettle();
      await openFold(tester);
      var opened = 0;
      for (var i = 1; i < r19.states.length; i++) {
        await goTo(tester, i);
        expect(tester.takeException(), isNull, reason: '걸음 $i');
        final detail = find.byKey(const ValueKey('paifu-engine-detail'));
        if (detail.evaluate().isNotEmpty && find.byKey(const ValueKey('paifu-engine-table')).evaluate().isEmpty) {
          await tester.ensureVisible(detail);
          await tester.tap(detail);
          await tester.pumpAndSettle();
          opened++;
        }
        final sheet = tester.getRect(find.byKey(const ValueKey('paifu-fold-scroll')));
        expect(sheet.bottom, lessThanOrEqualTo(tester.getRect(find.byKey(const ValueKey('paifu-strip'))).top + 1),
            reason: '걸음 $i');
        expect(sheet.right, lessThanOrEqualTo(size.width), reason: '걸음 $i');
        expect(tester.takeException(), isNull, reason: '걸음 $i');
      }
      expect(opened, 1); // "자세히" 는 한 번 열면 걸음을 넘겨도 열린 채
    });
  });
}
