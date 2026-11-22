// 패보 복기 화면(설계서 docs/paifu_review_ui_design_1121.md): 판 요약(3-1) → 복기(말풍선 · 탁자 배지 · 수 띠 · 단추 줄,
// 3-2 ~ 3-5) · 단계 말풍선(3-4) · 최선 보기 막대(3-9) · 펼침(후보 · 참고값). 손패 없는 판은 바로 재생 화면.
// 11-21: 옛 평가 카드(ReviewCard) · 패널 요약 줄 시험을 이 구조로 바꿈. 짐작 손패(3-6)로 r19 1순은 평가하지 않아 패효율 93.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_review.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/paifu/review_view.dart';
import 'package:mahjong_calc/ui/tile_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

Paifu _load(String name) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$name.json').readAsStringSync()) as Map<String, dynamic>);

/// 손패가 적힌 짧은 판(hero = 자리 1, 버림 한 번 — 고립된 중을 버려 지적할 것이 없다).
Paifu _small() => Paifu.fromJson({
      'version': 1,
      'id': 'rv',
      'round': '동1국',
      'dealer': 0,
      'hero': 1,
      'names': ['가', '나', '다', '라'],
      'events': [
        {'type': 'discard', 'seat': 0, 'tile': '9s', 'tsumogiri': null, 'riichi': false},
        {
          'type': 'draw',
          'seat': 1,
          'tile': '0s',
          'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '7z'],
        },
        {
          'type': 'discard',
          'seat': 1,
          'tile': '7z',
          'tsumogiri': false,
          'riichi': false,
          'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '0s'],
        },
      ],
    });

const _bubble = ValueKey('paifu-bubble');
const _go = ValueKey('paifu-review-go');

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  /// 엔진 참고값은 끝나지 않는 것으로(이 파일은 엔진 없이 본다 — 참고값은 paifu_review_engine_ui_test.dart).
  Future<PaifuReview> never(Paifu p) => Completer<PaifuReview>().future;

  Future<void> pump(WidgetTester tester, Paifu p, {Size size = const Size(1280, 800)}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p, engineReview: never)));
    await tester.pump();
  }

  Future<void> tap(WidgetTester tester, Key key) async {
    await tester.tap(find.byKey(key));
    await tester.pumpAndSettle();
  }

  /// 요약 → 복기 시작.
  Future<void> startReview(WidgetTester tester) async {
    await tester.ensureVisible(find.byKey(const ValueKey('paifu-summary-start')));
    await tap(tester, const ValueKey('paifu-summary-start'));
  }

  int step(WidgetTester tester) => tester.widget<ReviewBubble>(find.byType(ReviewBubble)).step;
  String title(WidgetTester tester) => tester.widget<Text>(find.byKey(const ValueKey('paifu-bubble-title'))).data!;
  String? sentence(WidgetTester tester) {
    final f = find.byKey(const ValueKey('paifu-bubble-sentence'));
    return f.evaluate().isEmpty ? null : tester.widget<Text>(f).data;
  }

  String? corner(WidgetTester tester) {
    final f = find.descendant(of: find.byKey(const ValueKey('paifu-bubble-corner')), matching: find.byType(Text));
    return f.evaluate().isEmpty ? null : tester.widget<Text>(f).data;
  }

  List<String> lines(WidgetTester tester) => [
        for (var i = 0; i < 2; i++)
          if (find.byKey(ValueKey('paifu-bubble-line-$i')).evaluate().isNotEmpty)
            tester.widget<Text>(find.byKey(ValueKey('paifu-bubble-line-$i'))).data!,
      ];

  /// 방향키(한 걸음씩, 지금처럼)로 [target] 까지.
  Future<void> goTo(WidgetTester tester, int target) async {
    while (step(tester) != target) {
      await tester.sendKeyEvent(step(tester) < target ? LogicalKeyboardKey.arrowRight : LogicalKeyboardKey.arrowLeft);
      await tester.pump();
    }
    await tester.pumpAndSettle();
  }

  Finder heroTiles() => find.descendant(of: find.byKey(const ValueKey('paifu-hero-hand')), matching: find.byType(TileView));

  group('판 요약(3-1) — r19', () {
    testWidgets('손패 있는 판은 요약이 먼저: 패효율 · 평가 건수 · 등급 표(0 도 흐리게) · 평가 안 함 · 배울 장면', (tester) async {
      await pump(tester, _load('r19_142013'));
      expect(find.byKey(const ValueKey('paifu-summary')), findsOneWidget);
      expect(find.byType(ReviewBubble), findsNothing);
      expect(find.byType(Slider), findsNothing);
      expect(find.text('2026-11-14 2반장 남4국 · 론'), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-summary-pct'))).data, '93');
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-summary-evaluated'))).data, '버림 10번 가운데 7번을 평가했습니다.');
      expect(find.text('유효패 수만 본 값입니다. 수비와 점수 판단은 들어 있지 않습니다.'), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-summary-threshold'))).data, contains('임시 기준'));
      final counts = {
        for (final g in ReviewGrade.values)
          g: tester.widget<Text>(find.byKey(ValueKey('paifu-summary-count-${g.name}'))).data,
      };
      expect(counts, {
        ReviewGrade.best: '5',
        ReviewGrade.good: '0',
        ReviewGrade.inaccuracy: '1',
        ReviewGrade.mistake: '1',
        ReviewGrade.blunder: '0',
      });
      expect(tester.widget<Opacity>(find.byKey(const ValueKey('paifu-summary-grade-good'))).opacity, lessThan(1));
      expect(tester.widget<Opacity>(find.byKey(const ValueKey('paifu-summary-grade-best'))).opacity, 1);
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-summary-skip'))).data,
          '리치 중 2 · 수비 0 · 화료 형태 0 · 손패 모름 1');
      // 배울 장면: 실수(6순 4만, −5장) → 부정확(7순 1삭, −2장).
      final l0 = find.byKey(const ValueKey('paifu-summary-lesson-0'));
      expect(find.descendant(of: l0, matching: find.text('6순 4만 버림')), findsOneWidget);
      expect(find.descendant(of: l0, matching: find.text('유효패 −5장')), findsOneWidget);
      final l1 = find.byKey(const ValueKey('paifu-summary-lesson-1'));
      expect(find.descendant(of: l1, matching: find.text('7순 1삭 버림')), findsOneWidget);
      expect(find.descendant(of: l1, matching: find.text('유효패 −2장')), findsOneWidget);
      expect(find.byKey(const ValueKey('paifu-summary-lesson-2')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('배울 장면을 누르면 그 걸음의 복기 화면, "요약" 으로 다시 열림', (tester) async {
      await pump(tester, _load('r19_142013'));
      await tester.ensureVisible(find.byKey(const ValueKey('paifu-summary-lesson-1')));
      await tap(tester, const ValueKey('paifu-summary-lesson-1'));
      expect(step(tester), 34);
      expect(title(tester), '1삭 버림 · 부정확');
      await tap(tester, const ValueKey('paifu-open-summary'));
      expect(find.byKey(const ValueKey('paifu-summary')), findsOneWidget);
    });

    testWidgets('"처음부터 보기": 말풍선 없는 재생 화면(자동 재생 있음)', (tester) async {
      await pump(tester, _load('r19_142013'));
      await tester.ensureVisible(find.byKey(const ValueKey('paifu-summary-play')));
      await tap(tester, const ValueKey('paifu-summary-play'));
      expect(find.byType(ReviewBubble), findsNothing);
      expect(find.byKey(const ValueKey('paifu-play')), findsOneWidget);
      expect(tester.widget<Slider>(find.byType(Slider)).value, 0);
      // 재생 화면에서 복기로.
      await tap(tester, const ValueKey('paifu-open-review'));
      expect(find.byType(ReviewBubble), findsOneWidget);
      expect(find.byKey(const ValueKey('paifu-play')), findsNothing); // 자동 재생은 복기 화면에서 숨김(9절 ⑥)
    });

    testWidgets('지적이 없는 판: "지적할 곳이 없습니다", 복기 화면의 "다음 지적" 비활성', (tester) async {
      await pump(tester, _small());
      expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-summary-pct'))).data, '100');
      expect(find.text('이 판은 유효패 수에서 지적할 곳이 없습니다'), findsOneWidget);
      await startReview(tester);
      expect(tester.widget<IconButton>(find.byKey(const ValueKey('paifu-review-next'))).onPressed, isNull);
    });
  });

  group('복기 화면 — r19', () {
    testWidgets('큰 "다음": 내 버림마다 멈추고, 리치 단계 → 그 걸음의 수 말풍선 → … → 끝 단계', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      // r19 는 첫 뽑기가 짐작이라 배패 단계가 없다 — 시작 걸음은 한 줄 회색.
      expect(step(tester), 0);
      expect(title(tester), '시작');
      expect(find.byKey(const ValueKey('paifu-stage-start')), findsNothing);

      final seen = <(int, String)>[];
      for (var i = 0; i < 12; i++) {
        await tap(tester, _go);
        seen.add((step(tester), title(tester)));
      }
      expect(seen, [
        (4, '북 버림 · 짐작 손패'),
        (9, '동 버림 · 최선입니다'),
        (14, '발 버림 · 최선입니다'),
        (18, '7통 버림 · 최선입니다'),
        (23, '2통 버림 · 최선입니다'),
        (29, '4만 버림 · 실수'),
        (34, '1삭 버림 · 부정확'),
        (39, '리치'),
        (39, '3삭 버림 · 최선입니다'),
        (44, '4삭 버림 · 리치 중'),
        (49, '1만 버림 · 리치 중'),
        (53, '끝'),
      ]);
      expect(sentence(tester), startsWith('론'));
      expect(sentence(tester), endsWith('\n이 판 패효율 93'));
      expect(tester.takeException(), isNull);
    });

    testWidgets('말풍선: 제목 · 두 줄 비교 · 구석 숫자 · 한 문장(실수 · 부정확 · 최선 · 텐파이 · 리치 단계 · 짐작)', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      await goTo(tester, 29);
      expect(title(tester), '4만 버림 · 실수');
      expect(lines(tester), ['내 버림 4만 · 유효패 10장', '최선 3만(또는 3삭) · 유효패 15장']);
      expect(corner(tester), '−5장');
      expect(sentence(tester), '3만(또는 3삭)을 버렸다면 유효패가 5장 더 많았습니다. 차이가 큽니다.');

      await goTo(tester, 34);
      expect(lines(tester), ['내 버림 1삭 · 유효패 10장', '최선 3삭 · 유효패 12장']);
      expect(corner(tester), '−2장');
      expect(sentence(tester), '3삭을 버렸다면 유효패가 2장 더 많았습니다.');

      await goTo(tester, 9);
      expect(lines(tester), ['내 버림 동 · 유효패 14장']);
      expect(corner(tester), isNull);
      expect(sentence(tester), '유효패가 가장 많은 버림입니다.');

      // 방향키로 온 리치 걸음은 수 말풍선(텐파이라 "대기"). 단계는 "다음" · 단계 아이콘으로.
      await goTo(tester, 39);
      expect(title(tester), '3삭 버림 · 최선입니다');
      expect(lines(tester), ['내 버림 3삭 · 대기 3장']);
      expect(sentence(tester), '대기가 가장 많은 버림입니다.');
      await tap(tester, const ValueKey('paifu-stage-riichi'));
      expect(step(tester), 39);
      expect(title(tester), '리치');
      expect(sentence(tester), '8순에 리치했습니다. 그 뒤 2번은 뽑은 패를 그대로 버렸습니다.');

      await goTo(tester, 4);
      expect(lines(tester), isEmpty);
      expect(corner(tester), isNull);
      expect(sentence(tester), '이 순의 손패는 짐작이라 평가하지 않습니다.');

      // 남의 걸음 · 뽑는 걸음: 한 줄 회색(문장 없음).
      await goTo(tester, 30);
      expect(sentence(tester), isNull);
      expect(lines(tester), isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('펼치기 전 말풍선 글은 다섯 줄 이하(제목 1 + 비교 ≤ 2 + 문장 ≤ 2줄)', (tester) async {
      final p = _load('r19_142013');
      await pump(tester, p, size: const Size(400, 800));
      await startReview(tester);
      for (var i = 1; i < p.states.length; i++) {
        await goTo(tester, i);
        // 글 줄: 제목(1줄) + 비교 줄(각 1줄) + 문장(그려진 높이 ÷ 한 줄 높이).
        final titleH = tester.getSize(find.byKey(const ValueKey('paifu-bubble-title'))).height;
        expect(tester.widget<Text>(find.byKey(const ValueKey('paifu-bubble-title'))).maxLines, 1);
        var lineCount = 1 + lines(tester).length;
        final s = find.byKey(const ValueKey('paifu-bubble-sentence'));
        if (s.evaluate().isNotEmpty) {
          expect(tester.widget<Text>(s).maxLines, 2);
          lineCount += (tester.getSize(s).height / titleH).round();
        }
        expect(lines(tester).length, lessThanOrEqualTo(2), reason: '걸음 $i');
        expect(lineCount, lessThanOrEqualTo(5), reason: '걸음 $i');
      }
    });

    testWidgets('탁자 배지: 방금 버린 hero 패에 등급 아이콘, 등급 없는 걸음 · 남의 걸음엔 없음', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      await goTo(tester, 29);
      final badge = find.byKey(const ValueKey('paifu-river-badge'));
      expect(badge, findsOneWidget);
      expect(tester.widget<ReviewGradeIcon>(badge).grade, ReviewGrade.mistake);
      await goTo(tester, 28);
      expect(badge, findsNothing);
      await goTo(tester, 44); // 리치 중
      expect(badge, findsNothing);
      await goTo(tester, 4); // 짐작
      expect(badge, findsNothing);
      await goTo(tester, 9);
      expect(tester.widget<ReviewGradeIcon>(badge).grade, ReviewGrade.best);
    });

    testWidgets('수 띠: 내 버림에만 등급 아이콘, 누르면 그 걸음, ‹ › 는 한 걸음, "다음 지적" 은 돌아감', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      await goTo(tester, 29);
      final item = find.byKey(const ValueKey('paifu-strip-29'));
      expect(tester.widget<ReviewStripItem>(item).current, isTrue);
      expect(tester.widget<ReviewStripItem>(item).entry.label, '6·4만');
      expect(tester.widget<ReviewStripItem>(item).entry.grade, ReviewGrade.mistake);
      expect(tester.widget<ReviewStripItem>(find.byKey(const ValueKey('paifu-strip-28'))).entry.grade, isNull);
      expect(tester.widget<ReviewStripItem>(find.byKey(const ValueKey('paifu-strip-30'))).entry.mine, isFalse);
      expect(tester.widget<ReviewStripItem>(find.byKey(const ValueKey('paifu-strip-31'))).entry.grade, isNull);

      await tester.ensureVisible(find.byKey(const ValueKey('paifu-strip-31')));
      await tester.pumpAndSettle();
      await tap(tester, const ValueKey('paifu-strip-31'));
      expect(step(tester), 31);
      await tap(tester, const ValueKey('paifu-strip-prev'));
      expect(step(tester), 30);
      await tap(tester, const ValueKey('paifu-strip-next'));
      expect(step(tester), 31);

      await tap(tester, const ValueKey('paifu-review-next'));
      expect(step(tester), 34);
      await tap(tester, const ValueKey('paifu-review-next'));
      expect(step(tester), 29);
      await tap(tester, const ValueKey('paifu-stage-end'));
      expect(step(tester), 53);
      expect(title(tester), '끝');
      await tap(tester, const ValueKey('paifu-review-next'));
      expect(step(tester), 29);
      expect(tester.takeException(), isNull);
    });

    testWidgets('최선 보기: 버리기 전 14장(버린 4만은 흐리게) 위 막대, ★ 3만 · 3삭, 막대 누르면 한 줄, 끄면 13장', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      await goTo(tester, 29);
      expect(heroTiles(), findsNWidgets(13));
      await tap(tester, const ValueKey('paifu-best-view'));
      expect(heroTiles(), findsNWidgets(14));
      final dimmed = tester.widgetList<TileView>(heroTiles()).where((t) => t.dimmed).toList();
      expect(dimmed.map((t) => t.tile), [3]); // 4만(쯔모기리라 오른쪽 뽑은 패 자리)
      // 손패 종류 11가지(3m 4m 7m 8m 9m 3p 4p 5p 3s 5s 8s)마다 막대 하나.
      final bars = find.byWidgetPredicate(
          (w) => w.key is ValueKey<String> && (w.key! as ValueKey<String>).value.startsWith('paifu-bar-'));
      expect(bars, findsNWidgets(11));
      Finder inBar(int tile, String text) =>
          find.descendant(of: find.byKey(ValueKey('paifu-bar-$tile')), matching: find.text(text));
      expect(inBar(2, '★'), findsOneWidget);
      expect(inBar(20, '★'), findsOneWidget);
      expect(inBar(3, '버림'), findsOneWidget);
      expect(inBar(2, '15'), findsOneWidget);
      expect(inBar(3, '10'), findsOneWidget);
      expect(find.text('★'), findsNWidgets(2));

      await tap(tester, const ValueKey('paifu-bar-2'));
      expect(tester.widget<Text>(find.descendant(of: find.byKey(const ValueKey('paifu-bar-info')), matching: find.byType(Text))).data,
          '3만을 버리면 유효패: 2만 5만 3삭 4삭 8삭 (15장)');

      // 걸음을 넘기면 한 줄은 닫히고 막대는 그 걸음 것으로(켜 둔 채).
      await goTo(tester, 34);
      expect(find.byKey(const ValueKey('paifu-bar-info')), findsNothing);
      expect(heroTiles(), findsNWidgets(14));
      expect(tester.widgetList<TileView>(heroTiles()).where((t) => t.dimmed).map((t) => t.tile), [18]); // 1삭

      await tap(tester, const ValueKey('paifu-best-view'));
      expect(heroTiles(), findsNWidgets(13));
      expect(bars, findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('최선 보기: 손패 기록 없는 걸음(남의 걸음 · 짐작)에서는 흐린 단추 + "이 걸음은 손패 기록이 없습니다"', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      for (final s in [30, 4]) {
        await goTo(tester, s);
        await tester.tap(find.byKey(const ValueKey('paifu-best-view')));
        await tester.pump();
        expect(find.text('이 걸음은 손패 기록이 없습니다'), findsOneWidget, reason: '걸음 $s');
        expect(heroTiles(), findsNWidgets(13));
        await tester.pumpAndSettle(const Duration(seconds: 5));
      }
    });

    testWidgets('최선 보기: 적5 는 그 걸음의 손패 기록에서(r17 2번째)', (tester) async {
      await pump(tester, _load('r17_140450'));
      await startReview(tester);
      await goTo(tester, 8);
      await tap(tester, const ValueKey('paifu-best-view'));
      final reds = tester.widgetList<TileView>(heroTiles()).where((t) => t.red).toList();
      expect(reds.map((t) => t.tile), [22]);
    });

    testWidgets('후보 펼침: 위 3개 + 실제(4만), "실제" · "최선"(동률 둘) 표시, 걸음을 넘겨도 펼친 채', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      await goTo(tester, 29);
      expect(find.byKey(const ValueKey('paifu-fold-candidates')), findsNothing);
      await tap(tester, const ValueKey('paifu-fold-candidates-btn'));
      final fold = find.byKey(const ValueKey('paifu-fold-candidates'));
      expect(find.descendant(of: fold, matching: find.byType(TileView)), findsNWidgets(4));
      expect(find.descendant(of: fold, matching: find.text('실제')), findsOneWidget);
      expect(find.descendant(of: fold, matching: find.text('최선')), findsNWidgets(2));
      await goTo(tester, 34);
      expect(find.descendant(of: fold, matching: find.byType(TileView)), findsNWidgets(3));
      await goTo(tester, 30);
      expect(find.descendant(of: fold, matching: find.text('이 걸음은 후보가 없습니다')), findsOneWidget);
      // 참고값: 엔진이 아직이면 "계산 중".
      await tap(tester, const ValueKey('paifu-fold-engine-btn'));
      await goTo(tester, 29);
      expect(find.text(engineReviewPending), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('⚙: 사건 목록에서 고르면 그 걸음, "재생 화면으로" 는 자동 재생 있는 재생 화면', (tester) async {
      await pump(tester, _load('r19_142013'));
      await startReview(tester);
      await tap(tester, const ValueKey('paifu-review-settings'));
      expect(find.text('0 / 53'), findsOneWidget);
      await tap(tester, const ValueKey('paifu-settings-log'));
      expect(find.byKey(const ValueKey('paifu-log-sheet')), findsOneWidget);
      await tester.tap(find.text('6'));
      await tester.pumpAndSettle();
      expect(step(tester), 6);
      await tap(tester, const ValueKey('paifu-review-settings'));
      await tap(tester, const ValueKey('paifu-settings-play'));
      expect(find.byKey(const ValueKey('paifu-play')), findsOneWidget);
      expect(tester.widget<Slider>(find.byType(Slider)).value, 6);
      expect(find.byType(ReviewBubble), findsNothing);
    });
  });

  testWidgets('단계 말풍선: r15 배패(3샹텐) → 다음 → 첫 내 버림, r11 남의 리치 단계', (tester) async {
    await pump(tester, _load('r15_134151'));
    await startReview(tester);
    expect(step(tester), 0);
    expect(title(tester), '배패');
    expect(sentence(tester), '배패는 3샹텐이었습니다.');
    await tap(tester, _go);
    expect(step(tester), 5);
    expect(title(tester), '북 버림 · 최선입니다');

    await tester.pumpWidget(const SizedBox());
    await pump(tester, _load('r11_130921'));
    await startReview(tester);
    await tap(tester, const ValueKey('paifu-stage-riichi'));
    // r11: 자리 2(dealer 0 → 서)가 38 걸음에 먼저 리치, hero 는 46 걸음.
    expect(step(tester), 38);
    expect(sentence(tester), endsWith('자리가 리치했습니다. 여기부터 수비 판단은 평가하지 않습니다.'));
    expect(sentence(tester), startsWith('서'));
    await tap(tester, _go);
    expect(step(tester), 40);
    expect(title(tester), '9통 버림 · 수비');
    expect(sentence(tester), '다른 자리가 리치 중입니다. 버린 패는 현물이 아닙니다.');
    await tap(tester, _go);
    expect((step(tester), title(tester)), (46, '리치'));
    expect(sentence(tester), '9순에 리치했습니다. 그 뒤 7번은 뽑은 패를 그대로 버렸습니다.');
    await tap(tester, _go);
    expect((step(tester), title(tester)), (46, '4만 버림 · 수비'));
  });

  testWidgets('손패 없는 판(r20): 요약 없이 바로 재생 화면, 말풍선 · 띠 없음, 시작 손패 입력 단추 그대로', (tester) async {
    final p = _load('r20_143236');
    await pump(tester, p);
    expect(find.byKey(const ValueKey('paifu-summary')), findsNothing);
    expect(find.byType(ReviewBubble), findsNothing);
    expect(find.byKey(const ValueKey('paifu-strip')), findsNothing);
    expect(find.byKey(const ValueKey('paifu-open-summary')), findsNothing);
    expect(find.byKey(const ValueKey('paifu-start-hand')), findsOneWidget);
    expect(find.byKey(const ValueKey('paifu-play')), findsOneWidget);
  });

  group('화면 크기(7절): 말풍선 · 탁자 · 수 띠 · "다음" 이 스크롤 없이 한 화면, 걸음을 넘겨도 탁자 그대로', () {
    for (final (name, size) in const [
      ('태블릿 가로 1280×800', Size(1280, 800)),
      ('폰 세로 400×800', Size(400, 800)),
      ('기본 800×600', Size(800, 600)),
      ('태블릿 세로 800×1280', Size(800, 1280)),
    ]) {
      testWidgets('$name: r19 모든 걸음', (tester) async {
        final p = _load('r19_142013');
        await pump(tester, p, size: size);
        await startReview(tester);
        Rect? table0, bubble0;
        final screen = Offset.zero & size;
        for (var i = 0; i < p.states.length; i++) {
          await goTo(tester, i);
          expect(tester.takeException(), isNull, reason: '걸음 $i');
          final bubble = tester.getRect(find.byKey(_bubble));
          final table = tester.getRect(find.byType(PaifuTableView));
          final strip = tester.getRect(find.byKey(const ValueKey('paifu-strip')));
          final go = tester.getRect(find.byKey(_go));
          for (final (what, r) in [('말풍선', bubble), ('탁자', table), ('띠', strip), ('다음', go)]) {
            expect(screen.contains(r.topLeft) && screen.contains(r.bottomRight - const Offset(0.01, 0.01)), isTrue,
                reason: '걸음 $i $what $r');
            expect(r.height, greaterThan(0), reason: '걸음 $i $what');
          }
          // 가로: 탁자 왼쪽 · 오른쪽 패널에 위에서부터 말풍선 → 띠 → 단추. 세로: 말풍선 → 탁자 → 띠 → 단추.
          if (size.width > size.height * 1.2) {
            expect(table.right, lessThanOrEqualTo(bubble.left + 1), reason: '걸음 $i');
          } else {
            expect(bubble.bottom, lessThanOrEqualTo(table.top + 1), reason: '걸음 $i');
            expect(table.bottom, lessThanOrEqualTo(strip.top + 1), reason: '걸음 $i');
          }
          expect(bubble.bottom, lessThanOrEqualTo(strip.top + 1), reason: '걸음 $i');
          expect(strip.bottom, lessThanOrEqualTo(go.top + 1), reason: '걸음 $i');
          table0 ??= table;
          bubble0 ??= bubble;
          expect(table, table0, reason: '걸음 $i: 탁자가 움직임');
          expect(bubble, bubble0, reason: '걸음 $i: 말풍선 크기가 바뀜');
        }
      });
    }

    testWidgets('폰 세로 400×800: 최선 보기 막대가 패 폭 안 · 펼침을 다 열어도 넘침 없음', (tester) async {
      const size = Size(400, 800);
      final p = _load('r19_142013');
      await pump(tester, p, size: size);
      await startReview(tester);
      await goTo(tester, 9); // 최선 보기는 손패를 아는 내 버림 걸음에서 켠다
      await tap(tester, const ValueKey('paifu-best-view'));
      await tap(tester, const ValueKey('paifu-fold-candidates-btn'));
      await tap(tester, const ValueKey('paifu-fold-engine-btn'));
      var checked = 0;
      for (final s in [9, 14, 18, 23, 29, 34, 39, 44, 49]) {
        await goTo(tester, s);
        expect(tester.takeException(), isNull, reason: '걸음 $s');
        final tileW = tester.getSize(heroTiles().first).width;
        final bars = find.byWidgetPredicate(
            (w) => w.key is ValueKey<String> && (w.key! as ValueKey<String>).value.startsWith('paifu-bar-'));
        expect(bars, findsWidgets, reason: '걸음 $s');
        for (final e in bars.evaluate()) {
          final r = tester.getRect(find.byWidget(e.widget));
          expect(r.width, lessThanOrEqualTo(tileW + 0.5), reason: '걸음 $s');
          expect(r.left, greaterThanOrEqualTo(0));
          expect(r.right, lessThanOrEqualTo(size.width));
          checked++;
        }
        final sheet = tester.getRect(find.byKey(const ValueKey('paifu-fold-scroll')));
        expect(sheet.bottom, lessThanOrEqualTo(tester.getRect(find.byKey(const ValueKey('paifu-strip'))).top + 1));
      }
      expect(checked, greaterThan(50));
    });
  });
}
