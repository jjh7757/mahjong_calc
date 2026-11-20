import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/start_hand.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/tile_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

List<PaifuTile> _t(String s) => [for (final c in s.split(' ')) PaifuTile.parse(c)];
String _s(Iterable<PaifuTile> t) => t.map((x) => x.code).join(' ');

Map<String, dynamic> _d(int seat, String tile, {bool? tsumogiri, bool riichi = false}) =>
    {'type': 'discard', 'seat': seat, 'tile': tile, 'tsumogiri': tsumogiri, 'riichi': riichi};

/// hero = 자리 1. [events] 와 끝 손패만 바꿔 쓴다(버림만 적힌 패보).
Paifu _paifu(List<Map<String, dynamic>> events, {String? end, String type = 'ron'}) => Paifu.fromJson({
      'version': 1,
      'id': 'sh',
      'round': '동1국',
      'dealer': 0,
      'hero': 1,
      'names': ['가', '나', '다', '라'],
      'events': events,
      if (end != null)
        'result': {'type': type, 'winner': 1, 'loser': type == 'ron' ? 2 : null, 'win_tile': '1p', 'hand': end.split(' ')}
      else if (type == 'draw')
        'result': {'type': 'draw'},
    });

const _start = '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s 9s';

void main() {
  group('시작 손패 → 매 순 손패', () {
    test('뽑은 패 묶음 = 끝 손패 + 버린 패 − 시작 손패', () {
      final p = _paifu([_d(1, '9s'), _d(1, '9s'), _d(1, '7z')], end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 4p 7s');
      final r = StartHandInference.infer(p, _t(_start));
      expect(r.error, isNull);
      expect(r.exact, isTrue);
      expect(_s(r.draws), '4p 7s 7z');
      expect(r.turns, 3);
    });

    test('손에서 낸 차례 사이의 뽑기 순서는 안 정해진다 — 어느 순서로 봐도 있는 패만 확정', () {
      final p = _paifu([_d(1, '9s'), _d(1, '9s'), _d(1, '7z')], end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 4p 7s');
      final r = StartHandInference.infer(p, _t(_start));
      // 시작: 13장 다 앎.
      expect(_s(r.after[0].known), _start);
      // 1순 뒤: 9삭 하나를 버렸고 뽑은 패는 4통·7삭·중 가운데 하나.
      expect(_s(r.after[1].known), '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s');
      expect(r.after[1].unknown, 1);
      expect(_s(r.after[1].candidates), '4p 7s 7z');
      expect(r.after[1].drew, isNull);
      // 2순 뒤: 둘이 모름.
      expect(r.after[2].unknown, 2);
      // 3순 뒤: 중을 버렸으니 끝 손패 그대로.
      expect(r.after[3].complete, isTrue);
      expect(_s(r.after[3].known), '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 4p 7s');
      expect(r.completeTurns, 1);
    });

    test('쯔모기리 여부가 적혀 있으면 그만큼 좁혀진다', () {
      // 3순의 중을 손에서 냈다 → 중은 1·2순에 뽑았다.
      final a = _paifu([_d(1, '9s'), _d(1, '9s'), _d(1, '7z', tsumogiri: false)], end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 4p 7s');
      final ra = StartHandInference.infer(a, _t(_start));
      expect(_s(ra.after[2].known), '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 7z');
      expect(_s(ra.after[2].candidates), '4p 7s');
      expect(ra.after[3].tsumogiri, isFalse);

      // 리치 뒤 버림은 쯔모기리 → 그 순에 뽑은 패가 정해지고, 앞 순의 뽑기도 따라 정해진다.
      final b = _paifu(
        [_d(1, '9s', riichi: true), _d(1, '7z', tsumogiri: true), _d(1, '2z', tsumogiri: true)],
        end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s 4p',
      );
      final rb = StartHandInference.infer(b, _t(_start));
      expect(rb.error, isNull);
      expect(rb.after[1].drew, PaifuTile.parse('4p'));
      expect(rb.after[2].drew, PaifuTile.parse('7z'));
      expect(rb.after[3].drew, PaifuTile.parse('2z'));
      expect(rb.completeTurns, 3);
      expect(rb.after[2].tsumogiri, isTrue);
    });

    test('같은 패를 뽑아 버렸는지 손의 것을 버렸는지는 가르지 못한다', () {
      // 9삭을 뽑고 9삭을 버림 — 손에도 9삭이 있었다.
      final p = _paifu([_d(1, '9s')], end: _start);
      final r = StartHandInference.infer(p, _t(_start));
      expect(r.after[1].drew, PaifuTile.parse('9s'));
      expect(r.after[1].tsumogiri, isNull);
      expect(r.after[1].complete, isTrue);
    });

    test('적5 는 5 와 따로 센다', () {
      final p = _paifu([_d(1, '9s')], end: '1m 2m 3m 4m 0m 6m 7m 8m 9m 1p 1p 9s 9s');
      final r = StartHandInference.infer(p, _t(_start));
      expect(r.error, contains('5만'));
      final ok = StartHandInference.infer(p, _t('1m 2m 3m 4m 0m 6m 7m 8m 9m 1p 1p 9s 9s'));
      expect(ok.error, isNull);
      expect(_s(ok.after[0].known), '1m 2m 3m 4m 0m 6m 7m 8m 9m 1p 1p 9s 9s');
    });

    test('맞지 않는 시작 손패는 까닭을 말한다', () {
      final p = _paifu([_d(1, '9s'), _d(1, '7z')], end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s 4p');
      // 장수.
      expect(StartHandInference.infer(p, _t('1m 2m')).error, contains('13장'));
      // 시작 손패의 백이 버림에도 끝 손패에도 없다.
      final gone = StartHandInference.infer(p, _t('1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s 5z'));
      expect(gone.error, contains('백'));
      expect(gone.after, isEmpty);
      // 첫 순에 손에서 냈다고 적힌 패가 시작 손패에 없다.
      final q = _paifu([_d(1, '7z', tsumogiri: false), _d(1, '9s')], end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s 4p');
      expect(StartHandInference.infer(q, _t(_start)).error, contains('나올 수 없습니다'));
      // 운 판.
      final c = _paifu(
        [_d(0, '7z'), {'type': 'call', 'seat': 1, 'kind': 'call', 'from': 0, 'tiles': ['7z']}, _d(1, '9s')],
        end: _start,
      );
      expect(StartHandInference.infer(c, _t(_start)).error, contains('운 판'));
    });

    test('끝 손패가 없는 판(유국)은 아직 안 버린 시작 패만 확정', () {
      final p = _paifu(
        [_d(1, '9s'), _d(1, '4p'), _d(1, '9s', riichi: true), _d(1, '9m', tsumogiri: true)],
        type: 'draw',
      );
      final r = StartHandInference.infer(p, _t(_start));
      expect(r.error, isNull);
      expect(r.exact, isFalse);
      expect([for (final v in r.after) v.known.length], [13, 12, 12, 11, 11]);
      expect([for (final v in r.after) v.unknown], [0, 1, 1, 2, 2]);
      // 리치 뒤 쯔모기리한 9만은 손의 9만을 줄이지 않는다.
      expect(r.after[4].known.where((t) => t.tile == Tiles.parse('9m')).length, 1);
    });

    test('걸음 → 그때의 손패', () {
      final p = _paifu([_d(0, '1z'), _d(1, '9s'), _d(2, '2z'), _d(1, '9s'), _d(1, '7z')], end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 4p 7s');
      final r = StartHandInference.infer(p, _t(_start));
      expect(r.viewAt(p, 0)!.known.length, 13);
      expect(r.viewAt(p, 1)!.known.length, 13); // 자리 0 이 버림
      expect(r.viewAt(p, 2)!.unknown, 1); // hero 첫 버림 뒤
      expect(r.viewAt(p, 3)!.unknown, 1);
      expect(r.viewAt(p, 5)!.complete, isTrue);
      expect(r.viewAt(p, 6)!.complete, isTrue); // 결과 걸음
      // 뽑기가 안 적힌 패보의 "내 차례" 이동은 hero 가 버린 걸음으로.
      expect(p.heroTurnSteps, [2, 4, 5]);
    });
  });

  group('정답 손패가 있는 예시 판과 맞대기', () {
    // 버림만 남기고(손패·뽑기 지움, 쯔모기리는 리치 뒤만) 시작 손패를 넣었을 때, 헤아린 "확정" 이 사람이 적은 정답과 어긋나면 안 된다.
    for (final name in ['r11_130921', 'r12_131655', 'r17_140450', 'r19_142013']) {
      test('$name: 확정으로 낸 패는 모두 정답 손패 안에 있다', () {
        final j = jsonDecode(File('assets/paifu/$name.json').readAsStringSync()) as Map<String, dynamic>;
        final full = Paifu.fromJson(j);
        final hero = full.hero;
        // 정답: hero 버림마다 버린 뒤 손패. 처음 아는 "뽑기 전 손패" 를 시작 손패로 쓴다(그 앞 버림은 녹화 전이라 쯔모기리였다고 침).
        final events = (j['events'] as List).cast<Map<String, dynamic>>();
        final firstKnown = events.indexWhere((e) => e['type'] == 'draw' && e['seat'] == hero && e['hand'] != null);
        final start = _t(((events[firstKnown]['hand']) as List).cast<String>().join(' '));
        var riichi = false;
        final stripped = <Map<String, dynamic>>[];
        final truth = <List<PaifuTile>?>[];
        final truthDraw = <PaifuTile?>[];
        String? lastDraw;
        for (final (i, e) in events.indexed) {
          if (e['seat'] == hero && e['type'] == 'draw') {
            lastDraw = e['tile'] as String?;
            continue;
          }
          if (e['seat'] == hero && e['type'] == 'discard') {
            final before = i < firstKnown;
            stripped.add({...e, 'hand': null, 'tsumogiri': before || riichi ? true : null}..remove('hand'));
            truth.add(e['hand'] == null ? null : _t((e['hand'] as List).cast<String>().join(' ')));
            truthDraw.add(lastDraw == null ? null : PaifuTile.parse(lastDraw));
            if (e['riichi'] == true) riichi = true;
          } else {
            stripped.add(e);
          }
        }
        final p = Paifu.fromJson({...j, 'events': stripped});
        expect(p.hasHeroHands, isFalse);
        final r = StartHandInference.infer(p, start);
        expect(r.error, isNull);
        var complete = 0, known = 0, total = 0, drew = 0;
        for (var k = 1; k < r.after.length; k++) {
          final t = truth[k - 1];
          if (t == null) continue;
          final v = r.after[k];
          final left = [...t];
          for (final x in v.known) {
            expect(left.remove(x), isTrue, reason: '$name $k순: 확정으로 낸 ${x.code} 가 정답 손패에 없음');
          }
          expect(v.known.length + v.unknown, 13);
          if (v.drew != null) {
            expect(v.drew, truthDraw[k - 1], reason: '$name $k순: 뽑은 패');
            drew++;
          }
          total++;
          known += v.known.length;
          if (v.complete) complete++;
        }
        // ignore: avoid_print
        print('$name: 정답 있는 $total순 중 손패가 다 정해진 순 $complete · 확정 장수 평균 ${(known / total).toStringAsFixed(1)}/13 · 뽑은 패가 정해진 순 $drew');
      });
    }
  });

  group('패보 화면', () {
    Paifu small() => _paifu(
          [_d(0, '1z'), _d(1, '9s'), _d(2, '2z'), _d(1, '9s'), _d(1, '7z')],
          end: '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 4p 7s',
        );

    Future<void> pump(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: small())));
      await tester.pump();
      await tester.pump();
    }

    int faces(WidgetTester tester) => tester
        .widgetList(find.descendant(of: find.byKey(const ValueKey('paifu-hero-hand')), matching: find.byType(TileView)))
        .length;

    testWidgets('시작 손패를 골라 적용하면 손패가 채워지고, 다음에 열 때도 남아 있다', (tester) async {
      SharedPreferences.setMockInitialValues({});
      await pump(tester);
      expect(faces(tester), 0);
      await tester.tap(find.byKey(const ValueKey('paifu-start-hand')));
      await tester.pumpAndSettle();
      // 12장만 고르면 적용할 수 없다.
      for (final c in _start.split(' ').take(12)) {
        await tester.tap(find.byKey(ValueKey('start-pick-$c')));
        await tester.pump();
      }
      expect(tester.widget<FilledButton>(find.byKey(const ValueKey('start-apply'))).onPressed, isNull);
      await tester.tap(find.byKey(const ValueKey('start-pick-9s')));
      await tester.pump();
      expect(find.text('13 / 13'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('start-apply')));
      await tester.pumpAndSettle();

      expect(faces(tester), 13);
      expect(find.byKey(const ValueKey('paifu-start-summary')), findsOneWidget);
      expect(find.textContaining('3순 중 1순은 손패가 다 정해짐'), findsOneWidget);
      // hero 첫 버림 뒤: 12장 확정 + 뒷면 1장.
      await tester.tap(find.byKey(const ValueKey('paifu-next')));
      await tester.tap(find.byKey(const ValueKey('paifu-next')));
      await tester.pump();
      expect(faces(tester), 12);
      expect(find.textContaining('확정 12장 · 모름 1장'), findsOneWidget);
      expect(find.textContaining('후보 4통 7삭 중'), findsOneWidget);

      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('paifu.startHand.sh'), _start);
    });

    testWidgets('저장해 둔 시작 손패는 열 때 바로 적용되고, 안 맞으면 까닭이 뜬다', (tester) async {
      SharedPreferences.setMockInitialValues({'paifu.startHand.sh': _start});
      await pump(tester);
      await tester.pumpAndSettle();
      expect(faces(tester), 13);
      expect(find.text('시작 손패 고치기'), findsOneWidget);

      SharedPreferences.setMockInitialValues({'paifu.startHand.sh': '1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 9s 5z'});
      await tester.pumpWidget(const SizedBox());
      await pump(tester);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('paifu-start-error')), findsOneWidget);
      expect(faces(tester), 0);
    });

    testWidgets('판 중 손패가 이미 적힌 패보에는 입력 단추가 없다', (tester) async {
      SharedPreferences.setMockInitialValues({});
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final p = Paifu.fromJson(jsonDecode(File('assets/paifu/r11_130921.json').readAsStringSync()) as Map<String, dynamic>);
      await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p)));
      await tester.pump();
      expect(find.byKey(const ValueKey('paifu-start-hand')), findsNothing);
    });
  });
}
