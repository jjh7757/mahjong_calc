import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/tile_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

Paifu _load(String name) =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/$name.json').readAsStringSync()) as Map<String, dynamic>);

/// 11-20: 예시의 녹화 전 순은 짐작으로 채워져("guess": true) 손패 모르는 순이 없다 — 그 경우를 보려고 짐작한 사건의 손패를 되돌린 r19.
Paifu _r19Unknown1st() {
  final j = jsonDecode(File('assets/paifu/r19_142013.json').readAsStringSync()) as Map<String, dynamic>;
  for (final e in (j['events'] as List).cast<Map<String, dynamic>>()) {
    if (e['guess'] == true) {
      e['hand'] = null;
      if (e['type'] == 'draw') e['tile'] = null;
      if (e['type'] == 'discard') e['tsumogiri'] = null;
    }
  }
  return Paifu.fromJson(j);
}

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

const _card = ValueKey('paifu-review-card');
const _summary = ValueKey('paifu-review-summary');
const _none = ValueKey('paifu-review-none');
const _nextFlag = ValueKey('paifu-review-next');

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<void> pump(WidgetTester tester, Paifu p, {Size size = const Size(1280, 800)}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p)));
    await tester.pump();
  }

  int step(WidgetTester tester) => tester.widget<Slider>(find.byType(Slider)).value.round();

  /// 방향키로 [target] 걸음까지 한 걸음씩 간다(끝 걸음에서 → 를 누르지 않으니 결과 화면은 안 뜬다).
  Future<void> goTo(WidgetTester tester, int target) async {
    while (step(tester) != target) {
      await tester.sendKeyEvent(step(tester) < target ? LogicalKeyboardKey.arrowRight : LogicalKeyboardKey.arrowLeft);
      await tester.pump();
    }
    await tester.pumpAndSettle();
  }

  Finder inCard(String text) => find.descendant(of: find.byKey(_card), matching: find.textContaining(text));

  Finder cardTiles() => find.descendant(of: find.byKey(_card), matching: find.byType(TileView));

  String summaryText(WidgetTester tester) =>
      tester.widget<Text>(find.descendant(of: find.byKey(_summary), matching: find.byType(Text)).first).data!;

  Finder anyBadge() => find.byWidgetPredicate(
      (w) => w.key is ValueKey<String> && (w.key! as ValueKey<String>).value.startsWith('paifu-badge-'));

  Future<void> tapNextFlag(WidgetTester tester) async {
    await tester.ensureVisible(find.byKey(_nextFlag));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(_nextFlag));
    await tester.pumpAndSettle();
  }

  // 11-20: r19 손패를 고친 정답으로 다시 만듦 — 옛 예시의 "5번째 버림 큰 실수"(효율 80)는 고치기 전 손패에서 나온 것이었고,
  // 고친 손패에선 5순 최선 · 6순 실수 · 7순 부정확(효율 93).
  group('r19 (손패 있음, 효율 93)', () {
    testWidgets('요약 줄: 패효율 · 0 이 아닌 등급 개수', (tester) async {
      await pump(tester, _load('r19_142013'));
      expect(find.byKey(_summary), findsOneWidget);
      final s = summaryText(tester);
      // 11-20: 녹화 전 첫 순을 짐작으로 채워 첫 버림도 평가됨(최선) — 93 → 94, 최선 5 → 6.
      expect(s, '패효율 94 · 최선 6 · 부정확 1 · 실수 1');
      expect(s, contains('패효율 94'));
      expect(s, contains('부정확 1'));
      expect(s, contains('· 실수 1'));
      expect(tester.takeException(), isNull);
    });

    testWidgets('6번째 버림(실수): 버린 걸음에만 카드 · 줄에 배지, 뽑은 걸음엔 없음', (tester) async {
      await pump(tester, _load('r19_142013'));
      // 뽑은 걸음(버리기 전): 답을 미리 보이지 않는다.
      await goTo(tester, 28);
      expect(find.byKey(_card), findsNothing);
      expect(find.byKey(_none), findsNothing);
      expect(find.byKey(const ValueKey('paifu-badge-28')), findsNothing);

      await goTo(tester, 29);
      expect(find.byKey(_card), findsOneWidget);
      expect(inCard('실수'), findsOneWidget);
      // 같은 샹텐이라 "n장 (m장 적음)".
      expect(inCard('4만 버림 → 1샹텐 · 유효패 10장'), findsOneWidget);
      expect(inCard('최선은 3만 → 15장 (5장 적음)'), findsOneWidget);
      expect(inCard('실제'), findsOneWidget);
      // 후보: 위에서 3개 + 그 안에 없는 실제 버림(4만, 4위).
      expect(cardTiles(), findsNWidgets(4));
      final badge = find.byKey(const ValueKey('paifu-badge-29'));
      expect(badge, findsOneWidget);
      expect(find.descendant(of: badge, matching: find.text('실수')), findsOneWidget);

      // 7번째 버림은 부정확(2위) — 실제 버림이 위 3개 안에 있어 후보 3개.
      await goTo(tester, 33);
      expect(inCard('부정확'), findsOneWidget);
      expect(inCard('최선은 3삭 → 12장 (2장 적음)'), findsOneWidget);
      expect(cardTiles(), findsNWidgets(3));
      expect(find.descendant(of: find.byKey(const ValueKey('paifu-badge-33')), matching: find.text('부정확')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('최선 버림은 차이 줄이 없다', (tester) async {
      await pump(tester, _load('r19_142013'));
      await goTo(tester, 9);
      expect(inCard('최선'), findsOneWidget); // 배지만
      expect(inCard('최선은'), findsNothing);
      expect(cardTiles(), findsNWidgets(3));
    });

    testWidgets('리치 뒤 버림(forced): "리치 중" 한 줄만, 배지 없음', (tester) async {
      await pump(tester, _load('r19_142013'));
      await goTo(tester, 43);
      expect(inCard('리치 중 — 고를 수 없는 버림'), findsOneWidget);
      expect(cardTiles(), findsNothing);
      expect(find.byKey(const ValueKey('paifu-badge-43')), findsNothing);
    });

    testWidgets('손패 모르는 첫 버림: "평가하지 않음" 한 줄, 카드 없음', (tester) async {
      await pump(tester, _r19Unknown1st());
      await goTo(tester, 4);
      expect(find.byKey(_card), findsNothing);
      expect(find.byKey(_none), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(_none)).data, '이 순은 손패 기록이 없어 평가하지 않음');
      expect(find.byKey(const ValueKey('paifu-badge-4')), findsNothing);
    });

    testWidgets('"다음 지적": 뒤의 부정확 이상 걸음으로, 끝에서는 처음 것으로 돌아감', (tester) async {
      await pump(tester, _load('r19_142013'));
      await tapNextFlag(tester);
      expect(step(tester), 29);
      await tapNextFlag(tester);
      expect(step(tester), 33);
      await tapNextFlag(tester);
      expect(step(tester), 29);

      await goTo(tester, 52);
      await tapNextFlag(tester);
      expect(step(tester), 29);
      expect(tester.takeException(), isNull);
    });

    testWidgets('넓은 화면: 사건 목록 자동 스크롤은 그대로', (tester) async {
      await pump(tester, _load('r19_142013'));
      await goTo(tester, 40);
      final log = tester.state<ScrollableState>(
        find.descendant(of: find.byType(ListView), matching: find.byType(Scrollable)),
      );
      expect(log.position.pixels, (38 * 40.0).clamp(0.0, log.position.maxScrollExtent));
      // 38 = 8번째 hero 버림(최선) 줄: 목록 맨 위에 배지와 함께 보인다.
      expect(find.descendant(of: find.byKey(const ValueKey('paifu-badge-38')), matching: find.text('최선')),
          findsOneWidget);
    });
  });

  group('r11 (수비 상황)', () {
    testWidgets('8번째 버림: 수비 배지 · 현물 문구 · 숫자 줄과 후보, forced 는 한 줄', (tester) async {
      await pump(tester, _load('r11_130921'));
      await goTo(tester, 40);
      expect(inCard('수비'), findsOneWidget);
      expect(inCard('다른 자리 리치 중 — 패효율 등급은 매기지 않음'), findsOneWidget);
      expect(inCard('버린 패는 현물이 아님'), findsOneWidget);
      expect(inCard('손 안 현물: 6만'), findsOneWidget);
      expect(inCard('9통 버림 → 1샹텐'), findsOneWidget);
      expect(cardTiles(), findsNWidgets(3));
      final badge = find.byKey(const ValueKey('paifu-badge-40'));
      expect(find.descendant(of: badge, matching: find.text('수비')), findsOneWidget);

      // 9번째도 수비.
      await goTo(tester, 46);
      expect(inCard('수비'), findsOneWidget);
      expect(inCard('손 안 현물: 6만 7삭'), findsOneWidget);

      // 리치 뒤(forced): 한 줄만.
      await goTo(tester, 51);
      expect(inCard('리치 중 — 고를 수 없는 버림'), findsOneWidget);
      expect(inCard('현물'), findsNothing);
      expect(cardTiles(), findsNothing);
      expect(find.byKey(const ValueKey('paifu-badge-51')), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('손패 없는 판(r20): 리뷰 위젯이 하나도 없다', (tester) async {
    // 11-20: r13 · r14 · r18 에 손패를 넣어 손패 없는 판은 r20(3반장)뿐.
    final p = _load('r20_143236');
    await pump(tester, p);
    for (var i = 0; i < p.states.length; i++) {
      if (i > 0) await goTo(tester, i);
      expect(find.byKey(_summary), findsNothing);
      expect(find.byKey(_card), findsNothing);
      expect(find.byKey(_none), findsNothing);
      expect(find.byKey(_nextFlag), findsNothing);
      expect(anyBadge(), findsNothing);
      expect(find.byKey(const ValueKey('paifu-panel-scroll')), findsNothing);
    }
    // 시작 손패 입력 단추는 그대로.
    expect(find.byKey(const ValueKey('paifu-start-hand')), findsOneWidget);
  });

  testWidgets('지적할 것이 없는 판은 "다음 지적" 단추가 비활성', (tester) async {
    await pump(tester, _small());
    expect(find.byKey(_summary), findsOneWidget);
    expect(summaryText(tester), startsWith('패효율 100 · 최선 1'));
    final button = find.ancestor(of: find.text('다음 지적'), matching: find.bySubtype<ButtonStyleButton>());
    expect(tester.widget<ButtonStyleButton>(button).onPressed, isNull);
    await goTo(tester, 3);
    expect(inCard('중 버림'), findsOneWidget);
  });

  group('화면 크기별 넘침 없음', () {
    for (final (name, size, narrow) in const [
      ('기본 800×600', Size(800, 600), false),
      ('태블릿 가로 1280×800', Size(1280, 800), false),
      ('태블릿 세로 800×1280', Size(800, 1280), true),
      ('폰 세로 400×800', Size(400, 800), true),
    ]) {
      testWidgets('$name: r19 모든 걸음', (tester) async {
        final p = _load('r19_142013');
        await pump(tester, p, size: size);
        expect(tester.takeException(), isNull);
        var cards = 0;
        for (var i = 1; i < p.states.length; i++) {
          await goTo(tester, i);
          expect(tester.takeException(), isNull, reason: '걸음 $i');
          final card = find.byKey(_card);
          if (card.evaluate().isEmpty) continue;
          cards++;
          if (narrow) {
            // 위 칸을 스크롤하면 카드 전체가 보인다.
            await tester.ensureVisible(card);
            await tester.pumpAndSettle();
          }
          // 넓은 화면은 스크롤 없이, 좁은 화면은 스크롤한 뒤 카드 전체가 위 칸 안에 보인다.
          final scroll = tester.getRect(find.byKey(const ValueKey('paifu-panel-scroll')));
          final r = tester.getRect(card);
          expect(r.top, greaterThanOrEqualTo(scroll.top - 1), reason: '걸음 $i');
          expect(r.bottom, lessThanOrEqualTo(scroll.bottom + 1), reason: '걸음 $i');
          expect(r.right, lessThanOrEqualTo(size.width), reason: '걸음 $i');
          // 사건 목록도 두 줄 이상 남는다.
          expect(tester.getSize(find.byType(ListView)).height, greaterThanOrEqualTo(80), reason: '걸음 $i');
          expect(tester.takeException(), isNull, reason: '걸음 $i');
        }
        expect(cards, 10); // 숫자 있는 버림 10번(11-20: 녹화 전 첫 버림도 짐작 손패로 평가)
      });
    }
  });
}
