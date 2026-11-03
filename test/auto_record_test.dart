import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/ui/game/win_sheet.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 거치 촬영 자동 반영: 확실한 판독이면 결과 화면에서 카운트다운 뒤 시트 없이 기록, 그 전엔 취소.

/// 핑후 쯔모 손패(리치), 서가(자리 2).
ScoreResult _result() {
  final e = HandEditor();
  for (final c in ['1m', '2m', '3m', '4p', '5p', '6p', '7s', '8s', '9s', '2m', '3m', '5p', '5p', '4m']) {
    e.closed.add(HandTile(Tiles.parse(c)));
  }
  e.isTsumo = true;
  e.riichi = true;
  e.seatWind = Tiles.west;
  final r = e.calculate();
  assert(r.isValid, r.error);
  return r;
}

void main() {
  setUp(() {
    // 결과 음성(연출 속도를 음성에 맞춤)은 꺼서 시간표대로 재생한다.
    SharedPreferences.setMockInitialValues({'voice.result': false});
    gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
  });
  tearDown(() {
    if (gameStore.current != null) gameStore.discardCurrent();
  });

  group('자동 반영 조건', () {
    String? block({
      List<String> warnings = const [],
      List<MergeIssue> issues = const [],
      int others = 0,
      bool tsumo = false,
      int? loser = 1,
      bool valid = true,
      int pao = 0,
      bool over = false,
    }) =>
        autoRecordBlocker(
            warnings: warnings,
            issues: issues,
            otherWinners: others,
            isTsumo: tsumo,
            loser: loser,
            resultValid: valid,
            paoBase: pao,
            gameOver: over);

    test('확인할 것 없음 + 화료자 한 명 + 방총자 앎이면 반영', () {
      expect(block(), isNull);
      expect(block(tsumo: true, loser: null), isNull);
    });
    test('경고: 도라 표시패를 못 읽었거나, 리치 화료인데 뒷도라까지 2장이 안 보이거나, 확신이 낮으면', () {
      List<String> cautions({List<MergeIssue> issues = const [], int dora = 1, bool riichi = false}) =>
          autoRecordCautions(issues: issues, doraIndicators: dora, riichi: riichi);
      expect(cautions(), isEmpty);
      expect(cautions(dora: 2, riichi: true), isEmpty);
      expect(cautions(dora: 0), ['도라']);
      expect(cautions(dora: 0, riichi: true), ['도라']);
      expect(cautions(riichi: true), ['표시패']);
      expect(cautions(issues: const [MergeIssue.uncertainTiles, MergeIssue.meldUncertain]), ['손패', '울기']);
      expect(cautions(issues: const [MergeIssue.doraFallback]), ['도라']);
      // 리치가 아닌데 표시패가 많은 것은 경고하지 않는다(갤러리 연출 장면 D 는 표시패 3장, 개발 세트로 확인 불가).
      expect(cautions(dora: 3), isEmpty);
      // 경고 대상은 막지 않는다.
      for (final i in cautionIssues) {
        expect(block(issues: [i]), isNull, reason: i.name);
      }
    });
    test('설명용 플래그(강 끝 론·리치 판단·추적 울기)만 있으면 반영', () {
      // 운영 앱 흐름 B·C·D 12장면 중 11장면이 이 경우였다(점수 모두 정답).
      expect(block(issues: const [MergeIssue.winFromDiscard, MergeIssue.riichiMismatch]), isNull);
      expect(block(issues: const [MergeIssue.winFromDiscard, MergeIssue.riichiImpossible]), isNull);
      expect(block(issues: const [MergeIssue.meldTracked]), isNull);
    });
    test('하나라도 애매하면 사람이 확인', () {
      expect(block(warnings: const ['자리 판독 3번이 엇갈림']), '판독 경고 1개');
      for (final i in [
        MergeIssue.loserAmbiguous,
        MergeIssue.winFromWait,
        MergeIssue.winTileUnknown,
        MergeIssue.winTileAssumed,
        MergeIssue.ronTsumoUnknown,
        MergeIssue.tileCountMismatch,
        MergeIssue.invalidHand,
        MergeIssue.multiRon,
      ]) {
        expect(block(issues: [i]), isNotNull, reason: i.name);
      }
      expect(block(others: 1), '동시 론');
      expect(block(loser: null), '방총자를 모름');
      expect(block(valid: false), '화료 형태가 아님');
      expect(block(pao: 8000), '파오 대상 역만');
      expect(block(over: true), '대국이 이미 끝남');
    });
  });

  test('시트 없이 기록: 자동 리치 포함, 문구 끝 "(자동)", 되돌리기 가능', () {
    final r = _result();
    final o = recordWinDirect(
        basePoints: r.basePoints, isTsumo: true, summary: r.summary, winner: 2, winnerRiichi: true);
    final g = gameStore.current!;
    expect(o.autoRiichiSeats, {2});
    expect(g.events.map((e) => e.kind), ['riichi', 'win']);
    expect(g.events.last.description, contains('(자동)'));
    expect(g.scores.fold<int>(0, (a, b) => a + b), 100000);
    expect(g.scores[2], greaterThan(25000));
    gameStore.rewind();
    expect(g.scores, [25000, 25000, 25000, 25000]);
    expect(g.events, isEmpty);
  });

  test('확인할 것을 안은 자동 기록은 문구에 남는다', () {
    final r = _result();
    recordWinDirect(
        basePoints: r.basePoints, isTsumo: true, summary: r.summary, winner: 2, winnerRiichi: true, cautions: const ['표시패', '울기']);
    expect(gameStore.current!.events.last.description, contains('(자동·확인 필요: 표시패, 울기)'));
  });

  group('결과 화면 카운트다운', () {
    Future<void> open(WidgetTester tester, {Duration? after = const Duration(seconds: 3), List<String> cautions = const []}) async {
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (c) => TextButton(
            onPressed: () => Navigator.of(c).push(MaterialPageRoute(
              builder: (_) => ResultScreen(
                result: _result(),
                isTsumo: true,
                gameSeat: 2,
                winnerRiichi: true,
                autoRecordAfter: after,
                autoCautions: cautions,
              ),
            )),
            child: const Text('열기'),
          ),
        ),
      ));
      await tester.tap(find.text('열기'));
      await tester.pumpAndSettle();
    }

    testWidgets('연출이 끝나면 카운트다운 뒤 기록하고 닫힌다', (tester) async {
      await open(tester);
      // pumpAndSettle 이 점수 이동판 연출까지 기다리는 동안 1초쯤 지났을 수 있다.
      int left() => int.parse(
          tester.widget<Text>(find.byKey(const ValueKey('result-auto-left'))).data!.split('초').first);
      final first = left();
      expect(first, inInclusiveRange(1, 3));
      expect(find.text('대국에 반영 (동1국)'), findsNothing); // 수동 버튼은 숨김
      expect(gameStore.current!.events, isEmpty);
      if (first > 1) {
        await tester.pump(const Duration(seconds: 1));
        expect(left(), first - 1);
      }
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(find.text('열기'), findsOneWidget);
      expect(gameStore.current!.events.last.description, contains('(자동)'));
    });

    testWidgets('취소하면 기록하지 않고 "대국에 반영" 버튼이 돌아온다', (tester) async {
      await open(tester);
      await tester.tap(find.byKey(const ValueKey('result-auto-cancel')));
      await tester.pump();
      expect(find.byKey(const ValueKey('result-auto-bar')), findsNothing);
      expect(find.text('대국에 반영 (동1국)'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      expect(gameStore.current!.events, isEmpty);
    });

    testWidgets('지금 반영은 바로 기록', (tester) async {
      await open(tester);
      await tester.tap(find.byKey(const ValueKey('result-auto-now')));
      await tester.pumpAndSettle();
      expect(gameStore.current!.events.map((e) => e.kind), ['riichi', 'win']);
      expect(find.text('열기'), findsOneWidget);
    });

    testWidgets('"지금 반영" 이 겹쳐 눌려도(카운트다운 끝과 터치) 한 번만 기록한다', (tester) async {
      await open(tester);
      final now = find.byKey(const ValueKey('result-auto-now'));
      await tester.tap(now);
      await tester.tap(now, warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(gameStore.current!.events.map((e) => e.kind), ['riichi', 'win']);
      expect(find.text('열기'), findsOneWidget, reason: '홈 화면까지 pop 되면 안 된다');
    });

    testWidgets('자동 반영이 꺼져 있으면 카운트다운 없음', (tester) async {
      await open(tester, after: null);
      expect(find.byKey(const ValueKey('result-auto-bar')), findsNothing);
      await tester.pump(const Duration(seconds: 5));
      expect(gameStore.current!.events, isEmpty);
    });

    testWidgets('확인할 것이 있으면 경고를 띄우고 그대로 카운트다운한다', (tester) async {
      await open(tester, cautions: const ['표시패', '손패']);
      expect(find.byKey(const ValueKey('result-auto-caution')), findsOneWidget);
      expect(find.text('표시패 · 손패 확인'), findsOneWidget);
      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
      expect(gameStore.current!.events.last.description, contains('자동·확인 필요'));
    });

    testWidgets('경고가 없으면 경고 줄도 없다', (tester) async {
      await open(tester);
      expect(find.byKey(const ValueKey('result-auto-caution')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('result-auto-cancel')));
      await tester.pump();
    });

    testWidgets('키오스크: 경고 줄과 카운트다운이 넘치지 않는다', (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await open(tester, cautions: const ['도라', '손패', '울기']);
      expect(find.byKey(const ValueKey('result-auto-caution')), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const ValueKey('result-auto-cancel')));
      await tester.pump();
      expect(find.byKey(const ValueKey('result-auto-caution')), findsNothing);
    });

    testWidgets('키오스크: 사진 판독 리치 화료는 표시패를 도라 줄에만, 직접 넣은 뒷도라만 뒷도라 줄', (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      Future<void> show(List<int> ura) async {
        final hand = Hand.parse('223344m567p67s55s 8s');
        final sit = Situation(
            isTsumo: false, seatWind: Tiles.south, riichi: true, doraIndicators: [Tiles.parse('4z'), Tiles.parse('1m')], uraIndicators: ura);
        await tester.pumpWidget(MaterialApp(
            key: UniqueKey(), home: ResultScreen(result: calculate(hand, sit), hand: hand, situation: sit)));
        await tester.pumpAndSettle();
      }

      await show(const []);
      expect(find.text('뒷도라'), findsNothing);
      await show([Tiles.parse('4z')]);
      expect(find.text('뒷도라'), findsOneWidget);
    });

    testWidgets('키오스크 결과 화면에도 같은 줄', (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await open(tester);
      expect(find.byKey(const ValueKey('result-auto-bar')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('result-auto-cancel')));
      await tester.pump();
      expect(find.text('대국에 반영 (동1국)'), findsOneWidget);
    });
  });
}
