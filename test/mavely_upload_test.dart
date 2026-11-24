import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/game/mavely_upload.dart';
import 'package:mahjong_calc/ui/game/settlement_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 마블리 올리기: 올릴 값(남은 공탁은 1위에게 주지 않고 공탁금으로), 채우기 스크립트, 올림 표시, 정산 화면 버튼.
/// 기대값은 규칙에서 손으로 정했다.
Game _game({List<int>? scores, int roundWind = 0, int roundNumber = 1, int dealer = 0, GameSettings settings = const GameSettings()}) =>
    Game(
      id: 'm',
      startedAt: DateTime(2026, 11, 24),
      settings: settings,
      names: const ['A', 'B', 'C', 'D'],
      scores: scores,
      roundWind: roundWind,
      roundNumber: roundNumber,
      dealer: dealer,
    );

int _sum(List<int> xs) => xs.fold(0, (a, b) => a + b);

/// 스크립트 안의 `var data = {...};` JSON 을 꺼낸다.
Map<String, dynamic> _dataOf(String script) {
  final m = RegExp(r'var data = (\{.*?\});\n').firstMatch(script);
  expect(m, isNotNull, reason: 'data 줄이 있어야 한다');
  return jsonDecode(m!.group(1)!) as Map<String, dynamic>;
}

void main() {
  group('올릴 값', () {
    test('(a) 공탁 없는 대국 → 점수 그대로, 공탁금 0', () {
      final g = _game(scores: [40000, 30000, 20000, 10000]);
      final e = mavelyEntryFor(g);
      expect(e.ok, isTrue);
      expect(e.names, ['A', 'B', 'C', 'D']);
      expect(e.points, [40000, 30000, 20000, 10000]);
      expect(e.deposit, 0);
      expect(e.stars, [0, 0, 0, 0]);
    });

    test('(b) 끝날 때 남은 공탁 2개가 1위에게 간 대국 → 1위 −2000, 공탁금 2000', () {
      // 남4국(친 D), B·C 리치 뒤 유국: 텐파이 B·C(+1500씩), A·D 노텐(−1500씩). 친 노텐 → 올라스 끝, A 가 반환점 이상 → 종료.
      final g = _game(scores: [40000, 25000, 20000, 15000], roundWind: 1, roundNumber: 4, dealer: 3);
      g.declareRiichi(1);
      g.declareRiichi(2);
      g.draw({1, 2});
      expect(g.endedBy, '종료');
      expect(g.riichiSticks, 0);
      // 앱 점수는 A 가 공탁 2000 을 가져간 값.
      expect(g.scores, [40500, 25500, 20500, 13500]);
      final i = g.events.indexWhere((e) => e.kind == 'adjust');
      expect(Game.isLeftoverStickEvent(g.events, i), isTrue);

      final e = mavelyEntryFor(g);
      expect(e.ok, isTrue);
      expect(e.points, [38500, 25500, 20500, 13500]);
      expect(e.deposit, 2000);
      expect(_sum(e.points) + e.deposit, 100000);

      // 저장했다 불러와도 같다.
      final back = mavelyEntryFor(Game.fromJson(jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>));
      expect(back.points, e.points);
      expect(back.deposit, 2000);
    });

    test('(b2) 같은 글의 수동 조정은 남은 공탁으로 보지 않는다', () {
      final g = _game(scores: [40000, 30000, 20000, 10000]);
      g.adjust([1000, -1000, 0, 0], '남은 공탁 1 → 1위 A');
      final i = g.events.length - 1;
      expect(Game.isLeftoverStickEvent(g.events, i), isFalse);
      final e = mavelyEntryFor(g);
      expect(e.points, [41000, 29000, 20000, 10000]);
      expect(e.deposit, 0);
    });

    test('(c) 토비(음수) 점수 + 아직 남은 공탁(끝나기 전 정산)', () {
      final g = _game(scores: [44000, 31000, 26000, -1000]);
      g.declareRiichi(1);
      expect(g.anyBusted, isTrue);
      final e = mavelyEntryFor(g);
      expect(e.ok, isTrue);
      expect(e.points, [44000, 30000, 26000, -1000]);
      expect(e.deposit, 1000);
      expect(_sum(e.points) + e.deposit, 100000);
    });

    test('(d) 시작점 30000 → 올리기 불가 사유', () {
      final g = _game(settings: const GameSettings(startPoints: 30000, returnPoints: 30000));
      final e = mavelyEntryFor(g);
      expect(e.ok, isFalse);
      expect(e.problem, contains('25000'));
      expect(e.problem, contains('30000'));
    });

    test('(d2) 합이 안 맞으면 사유(예외 아님)', () {
      final g = _game(scores: [40000, 30000, 20000, 9000]);
      final e = mavelyEntryFor(g);
      expect(e.ok, isFalse);
      expect(e.problem, contains('100000'));
    });

    test('(e) 별: 하네만 화료 → 화료자 ★1', () {
      final g = _game();
      g.win(
        winner: 1,
        payment: paymentFor(han: 6, fu: 30, isDealer: false, isTsumo: false, honba: 0),
        isTsumo: false,
        loser: 2,
      );
      final e = mavelyEntryFor(g);
      expect(e.ok, isTrue);
      expect(e.points, [25000, 37000, 13000, 25000]);
      expect(e.stars, [0, 1, 0, 0]);
    });

    test('(f) 직접 입력 대국(Game.manual) → 점수 · 별 그대로, 공탁금 0', () {
      final g = Game.manual(
        id: 'x',
        playedAt: DateTime(2026, 11, 20),
        settings: const GameSettings(),
        names: const ['가', '나', '다', '라'],
        scores: const [41000, 29000, 22000, 8000],
        stars: const [2, 0, 1, 0],
      );
      final e = mavelyEntryFor(g);
      expect(e.ok, isTrue);
      expect(e.names, ['가', '나', '다', '라']);
      expect(e.points, [41000, 29000, 22000, 8000]);
      expect(e.stars, [2, 0, 1, 0]);
      expect(e.deposit, 0);
    });
  });

  group('(g) 올림 표시 저장', () {
    test('옛 JSON(필드 없음) 읽기 · mavelyUploadedAt 왕복', () {
      final g = _game(scores: [40000, 30000, 20000, 10000]);
      final j = g.toJson();
      expect(j.containsKey('mavelyUploadedAt'), isFalse);
      final old = Game.fromJson(jsonDecode(jsonEncode(j)) as Map<String, dynamic>);
      expect(old.mavelyUploadedAt, isNull);

      g.mavelyUploadedAt = DateTime(2026, 11, 24, 21, 5, 7);
      final back = Game.fromJson(jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>);
      expect(back.mavelyUploadedAt, DateTime(2026, 11, 24, 21, 5, 7));
    });

    test('옛 기록의 남은 공탁 사건(글만 있는 JSON)도 가려낸다', () {
      final g = _game(scores: [41000, 30000, 19000, 10000]);
      final j = jsonDecode(jsonEncode(g.toJson())) as Map<String, dynamic>;
      (j['events'] as List).addAll(<dynamic>[
        {'kind': 'end', 'description': '종료 — 1위 A 40000', 'delta': [0, 0, 0, 0], 'round': '남4국'},
        {'kind': 'adjust', 'description': '남은 공탁 1 → 1위 A', 'delta': [1000, 0, 0, 0], 'round': '남4국'},
      ]);
      final e = mavelyEntryFor(Game.fromJson(jsonDecode(jsonEncode(j)) as Map<String, dynamic>));
      expect(e.points, [40000, 30000, 19000, 10000]);
      expect(e.deposit, 1000);
    });

    test('GameStore.markMavelyUploaded: 지난 대국 · 진행 중 대국', () async {
      SharedPreferences.setMockInitialValues({});
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
      final live = gameStore.current!;
      expect(gameStore.markMavelyUploaded(live.id, at: DateTime(2026, 11, 24, 20)), isTrue);
      expect(live.mavelyUploadedAt, DateTime(2026, 11, 24, 20));
      gameStore.finish();
      expect(gameStore.history.first.mavelyUploadedAt, DateTime(2026, 11, 24, 20));

      final done = gameStore.history.first;
      done.mavelyUploadedAt = null;
      var notified = 0;
      void l() => notified++;
      gameStore.addListener(l);
      expect(gameStore.markMavelyUploaded(done.id), isTrue);
      gameStore.removeListener(l);
      expect(done.mavelyUploadedAt, isNotNull);
      expect(notified, 1);
      expect(gameStore.markMavelyUploaded('없는 id'), isFalse);

      // 저장된 것을 다시 읽어도 남아 있다.
      await Future<void>.delayed(Duration.zero);
      await gameStore.load();
      expect(gameStore.history.firstWhere((h) => h.id == done.id).mavelyUploadedAt, isNotNull);
      gameStore.deleteHistory(done.id);
    });
  });

  group('(h) 채우기 스크립트', () {
    test('이름에 따옴표 · 한글, 음수 → rate_is_minus true · 절댓값', () {
      const e = MavelyEntry(
        names: ['김"철수', "O'Neil", r'백\슬래시', '라'],
        points: [52000, 31000, 18000, -3000],
        stars: [2, 0, 0, 1],
        deposit: 2000,
      );
      final js = mavelyFillScript(e);
      final d = _dataOf(js);
      expect(d['names'], ['김"철수', "O'Neil", r'백\슬래시', '라']);
      expect(d['rates'], [52000, 31000, 18000, 3000]);
      expect(d['minus'], [false, false, false, true]);
      expect(d['stars'], [2, 0, 0, 1]);
      expect(d['deposit'], 2000);
      // 따옴표는 JSON 이스케이프로 들어간다(문자열이 깨지지 않게).
      expect(js, contains(r'"김\"철수"'));
      expect(js, contains(r'"백\\슬래시"'));
      // 폼 찾기 · $set · 반환 전 점수 · 재시도 · 채널.
      expect(js, contains("'rate_is_minus'"));
      expect(js, contains(r'vm.$set(vm.names, i, data.names[i])'));
      expect(js, contains(r'vm.$set(vm.rates, i, data.rates[i])'));
      expect(js, contains(r'vm.$set(vm.rate_is_minus, i, data.minus[i])'));
      expect(js, contains(r'vm.$set(vm.stars, i, data.stars[i])'));
      expect(js, contains('vm.deposit = data.deposit'));
      expect(js, contains('vm.isNewInput = true'));
      expect(js, contains('setTimeout(fill, 200)'));
      expect(js, contains('Date.now() + 10000'));
      expect(js, contains('MavelyBridge.postMessage(JSON.stringify(o))'));
      expect(js, contains('unknownNames'));
      // 등록 버튼은 누르지 않는다.
      expect(js, isNot(contains('submit')));
    });

    test('이름은 멤버 목록 확인 뒤 넣고, 없는 이름 · 목록 못 불러옴은 \'\' 로', () {
      const e = MavelyEntry(names: ['A', 'B', 'C', 'D'], points: [40000, 30000, 20000, 10000], stars: [0, 0, 0, 0], deposit: 0);
      final js = mavelyFillScript(e);
      // 점수 채우기 블록(isNewInput ~ deposit)에는 이름을 넣는 줄이 없다.
      final start = js.indexOf('vm.isNewInput = true');
      final end = js.indexOf('vm.deposit = data.deposit');
      expect(start, greaterThan(0));
      expect(end, greaterThan(start));
      final scoreBlock = js.substring(start, end);
      expect(scoreBlock, isNot(contains('vm.names')));
      expect(scoreBlock, contains(r'vm.$set(vm.rates, i, data.rates[i])'));
      // 점수 블록 뒤에 fillNames 를 부른다.
      expect(js.indexOf('fillNames(vm);', end), greaterThan(end));
      // fillNames: 멤버 목록을 읽고, 비어 있으면 기한까지 다시, 없는 이름은 '' 로 바꾼 뒤 $set.
      final f = js.indexOf('function fillNames(vm)');
      expect(f, greaterThan(0));
      final fillNames = js.substring(f, js.indexOf('function fill()'));
      final members = fillNames.indexOf('memberNames(vm)');
      final blank = fillNames.indexOf("data.names[k] = ''");
      final setName = fillNames.indexOf(r'vm.$set(vm.names, i, data.names[i])');
      expect(members, greaterThanOrEqualTo(0));
      expect(blank, greaterThan(members));
      expect(setName, greaterThan(blank));
      expect(fillNames, contains('m.count === 0 && Date.now() < deadline'));
      expect(fillNames, contains('setTimeout(function () { fillNames(vm); }, 200)'));
      expect(fillNames, contains('loaded && m.known[wanted[k]]'));
      expect(fillNames, contains('membersLoaded: loaded'));
      expect(fillNames, contains('unknownNames: unknown'));
    });

    test('줄 구분 문자(U+2028)는 이스케이프', () {
      const e = MavelyEntry(names: ['가\u2028나', 'B', 'C', 'D'], points: [25000, 25000, 25000, 25000], stars: [0, 0, 0, 0], deposit: 0);
      final js = mavelyFillScript(e);
      expect(js.contains('\u2028'), isFalse);
      expect(_dataOf(js)['names'], ['가\u2028나', 'B', 'C', 'D']);
    });
  });

  group('정산 화면 버튼', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      mavelyUploadScreenBuilder = (g) => Scaffold(body: Text('가짜 마블리 ${g.id}'));
    });

    void setSize(WidgetTester tester) {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
    }

    testWidgets('settle-mavely 버튼 → 올리기 화면으로', (tester) async {
      setSize(tester);
      final g = _game(scores: [40000, 30000, 20000, 10000]);
      await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: g)));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('settle-mavely')), findsOneWidget);
      expect(find.text('마블리에 올리기'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('settle-mavely')));
      await tester.pumpAndSettle();
      expect(find.text('가짜 마블리 m'), findsOneWidget);
    });

    testWidgets('진행 중 대국에도 버튼', (tester) async {
      setSize(tester);
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
      addTearDown(() {
        if (gameStore.current != null) gameStore.discardCurrent();
      });
      await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: gameStore.current!)));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('settle-mavely')), findsOneWidget);
      expect(find.byKey(const ValueKey('settle-finish')), findsOneWidget);
    });

    testWidgets('올린 대국은 라벨이 바뀌고, 다시 올리면 중복 확인', (tester) async {
      setSize(tester);
      final g = _game(scores: [40000, 30000, 20000, 10000])..mavelyUploadedAt = DateTime(2026, 11, 24);
      await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: g)));
      await tester.pumpAndSettle();
      expect(find.text('마블리에 올림 ✓(다시 올리기)'), findsOneWidget);
      expect(find.text('마블리에 올리기'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('settle-mavely')));
      await tester.pumpAndSettle();
      expect(find.text('이미 올렸습니다. 또 올리면 중복됩니다.'), findsOneWidget);
      expect(find.text('가짜 마블리 m'), findsNothing);
      await tester.tap(find.byKey(const ValueKey('settle-mavely-again')));
      await tester.pumpAndSettle();
      expect(find.text('가짜 마블리 m'), findsOneWidget);
    });

    testWidgets('올리기 불가(시작점 30000)면 사유 스낵바, 화면은 안 연다', (tester) async {
      setSize(tester);
      final g = _game(settings: const GameSettings(startPoints: 30000, returnPoints: 30000));
      await tester.pumpWidget(MaterialApp(home: SettlementScreen(game: g)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('settle-mavely')));
      await tester.pump();
      expect(find.textContaining('마블리에 올릴 수 없습니다'), findsOneWidget);
      expect(find.textContaining('가짜 마블리'), findsNothing);
    });
  });
}
