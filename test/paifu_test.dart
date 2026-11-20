import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_score.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/tile_view.dart';

/// 작은 판: hero = 자리 1. 자리 0 버림 → hero 뽑고 손에서 냄 → 자리 2 가 퐁 → 자리 2 리치 버림 → 자리 3 버림 →
/// 자리 0 버림 → hero 쯔모 화료.
Map<String, dynamic> _small() => {
      'version': 1,
      'id': 't',
      'title': '시험 판',
      'round': '동1국',
      'honba': 1,
      'dealer': 0,
      'hero': 1,
      'names': ['가', '나', '다', '라'],
      'dora_indicators': ['5m'],
      'ura_indicators': ['3p'],
      'start_hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '7z'],
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
        {'type': 'call', 'seat': 2, 'kind': 'pon', 'from': 1, 'tiles': ['7z', '7z', '7z']},
        {'type': 'discard', 'seat': 2, 'tile': '1s', 'tsumogiri': false, 'riichi': true},
        {'type': 'discard', 'seat': 3, 'tile': '4p', 'tsumogiri': null, 'riichi': false},
        {'type': 'discard', 'seat': 0, 'tile': '4p', 'tsumogiri': null, 'riichi': false},
        {
          'type': 'draw',
          'seat': 1,
          'tile': '3s',
          'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '0s'],
        },
      ],
      'result': {
        'type': 'tsumo',
        'winner': 1,
        'loser': null,
        'win_tile': '3s',
        'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '0s'],
      },
    };

void main() {
  group('패보 모델', () {
    test('걸음마다 강·손패·리치·울기가 쌓인다', () {
      final p = Paifu.fromJson(_small());
      expect(p.stepCount, 10); // 시작 + 사건 8 + 결과
      expect(p.states.length, 10);

      final s0 = p.states[0];
      expect(s0.heroHand!.length, 13);
      expect(s0.turn, 0);
      expect(s0.wallLeft, 70);

      // hero 가 뽑은 걸음: 뽑은 패가 따로, 적5 구분.
      final s2 = p.states[2];
      expect(s2.hasDrawn, isTrue);
      expect(s2.drawn, const PaifuTile(22, red: true));
      expect(s2.drawn!.code, '0s');
      expect(s2.wallLeft, 68); // 자리 0 한 장 + hero 한 장

      // hero 가 버린 걸음: 손패가 버린 뒤 줄로 바뀌고 뽑은 패 표시는 사라진다.
      final s3 = p.states[3];
      expect(s3.hasDrawn, isFalse);
      expect(s3.heroHand!.last.code, '0s');
      expect(s3.rivers[1].single.tsumogiri, isFalse);

      // 퐁: 버린 자리 강의 패가 울려 나감으로 바뀌고 운 자리에 묶음이 생긴다.
      final s4 = p.states[4];
      expect(s4.rivers[1].single.called, isTrue);
      expect(s4.melds[2].single.tiles.length, 3);
      expect(s4.melds[2].single.from, 1);

      // 퐁 뒤 버림은 뽑은 장수에 안 들어간다. 리치 선언.
      final s5 = p.states[5];
      expect(s5.riichi, [false, false, true, false]);
      expect(s5.rivers[2].single.riichi, isTrue);
      expect(s5.wallLeft, 68);

      final last = p.states.last;
      expect(last.finished, isTrue);
      expect(last.heroHand!.length, 13);
      expect(last.turn, 2);
    });

    test('자리 → 바람·화면 쪽', () {
      final p = Paifu.fromJson(_small());
      expect([for (var s = 0; s < 4; s++) p.windOf(s)], [0, 1, 2, 3]);
      // hero(1) 가 아래, 다음 차례(2)가 오른쪽, 3 이 위, 0 이 왼쪽.
      expect([for (var s = 0; s < 4; s++) p.sideOf(s)], [3, 0, 1, 2]);
      expect(p.heroTurnSteps, [2, 8]);
    });

    test('JSON 으로 내보냈다 다시 읽어도 같다', () {
      final p = Paifu.fromJson(_small());
      final q = Paifu.fromJson(jsonDecode(jsonEncode(p.toJson())) as Map<String, dynamic>);
      expect(jsonEncode(q.toJson()), jsonEncode(p.toJson()));
      expect(q.states.length, p.states.length);
    });

    test('손패를 모르는 순은 null 로 남는다', () {
      final j = _small();
      (j['events'] as List)[1] = {'type': 'draw', 'seat': 1, 'tile': null, 'hand': null};
      (j['events'] as List)[2] = <String, dynamic>{...((j['events'] as List)[2] as Map<String, dynamic>), 'hand': null};
      final p = Paifu.fromJson(j);
      expect(p.states[2].heroHand, isNull);
      expect(p.states[2].hasDrawn, isTrue);
      expect(p.states[2].drawn, isNull);
      expect(p.states[3].heroHand, isNull);
      expect(p.states[8].heroHand, isNotNull);
      expect(p.check(), isEmpty);
    });

    test('check: 맞는 기록은 문제 없음, 어긋난 기록은 잡는다', () {
      expect(Paifu.fromJson(_small()).check(), isEmpty);

      // 버린 뒤 손패가 계산과 다름.
      final a = _small();
      (((a['events'] as List)[2] as Map)['hand'] as List)[0] = '9p';
      expect(Paifu.fromJson(a).check().single, contains('hero 1번째 버림'));

      // 같은 패 5장.
      final b = _small();
      for (final i in [0, 5, 6]) {
        ((b['events'] as List)[i] as Map)['tile'] = '1p';
      }
      (b['dora_indicators'] as List).add('1p');
      expect(Paifu.fromJson(b).check().single, contains('1통'));

      // 리치 뒤에 손에서 냄.
      final c = _small();
      (c['events'] as List).insert(7, {'type': 'discard', 'seat': 2, 'tile': '9p', 'tsumogiri': false, 'riichi': false});
      expect(Paifu.fromJson(c).check().single, contains('리치 뒤'));
    });

    test('모르는 사건·버전은 거른다', () {
      final a = _small()..['version'] = 2;
      expect(() => Paifu.fromJson(a), throwsFormatException);
      final b = _small();
      ((b['events'] as List)[0] as Map)['type'] = 'peek';
      expect(() => Paifu.fromJson(b), throwsFormatException);
    });
  });

  group('패보 예시 파일', () {
    final dir = Directory('assets/paifu');
    final files = dir.existsSync()
        ? [
            for (final f in dir.listSync())
              if (f is File && f.path.endsWith('.json')) f,
          ]
        : <File>[];

    test('예시가 하나는 있다', () => expect(files, isNotEmpty));

    test('11-14 매장 판들이 들어 있고, 화료로 끝난 판은 점수가 계산된다', () {
      final all = {
        for (final f in files)
          f.uri.pathSegments.last: Paifu.fromJson(jsonDecode(f.readAsStringSync()) as Map<String, dynamic>),
      };
      expect(all.length, greaterThanOrEqualTo(10));
      expect({for (final p in all.values) p.id}.length, all.length, reason: 'id 가 겹침');
      for (final p in all.values) {
        final r = p.result;
        final s = scoreOf(p);
        if (r != null && r.type != 'draw') {
          expect(s?.result.isValid, isTrue, reason: '${p.id}: ${s?.result.error}');
        } else {
          expect(s, isNull, reason: p.id);
        }
      }
      // 손패까지 있는 판(사람이 적은 정답)과 버림만 있는 판이 섞여 있다.
      // 11-20: 유국 판(r13 · r15 · r16 · L16)에 텐파이 공개자 손패, r14 에 2순 정답 손패, r18 에 Opus 읽기 손패를 넣어
      // 손패 있는 판 10 · 없는 판 1(r20 — 3반장, 화료 기록 없음).
      expect(all.values.where((p) => p.hasHeroHands).length, greaterThanOrEqualTo(10));
      expect(all.values.where((p) => !p.hasHeroHands).length, greaterThanOrEqualTo(1));
      // 그날 일발 쯔모였던 동4국 1본장(HANDOFF 11-16 일발 누락 건)은 사건만으로 일발이 헤아려진다.
      final r14 = scoreOf(all['r14_133610.json']!)!;
      expect(r14.situation.ippatsu, isTrue);
      expect(r14.situation.isTsumo, isTrue);
    });

    for (final f in files) {
      test('${f.uri.pathSegments.last}: 읽히고 앞뒤가 맞는다', () {
        final p = Paifu.fromJson(jsonDecode(f.readAsStringSync()) as Map<String, dynamic>);
        expect(p.check(), isEmpty);
        expect(p.states.last.finished, p.result != null);
        final r = p.result;
        if (r != null && r.winner == p.hero && r.hand != null && p.hasHeroHands) {
          // 판 중 손패가 적힌 패보면: 마지막 사건 뒤의 hero 손패 = 결과의 끝 손패.
          expect(p.states[p.events.length].heroHand, r.hand);
        }
      });
    }
  });

  group('패보 화면', () {
    Future<void> pump(WidgetTester tester, Size size) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: Paifu.fromJson(_small()))));
      await tester.pump();
    }

    String now(WidgetTester tester) => tester.widget<Text>(find.byKey(const ValueKey('paifu-now'))).data!;

    int heroFaces(WidgetTester tester) => tester
        .widgetList(find.descendant(of: find.byKey(const ValueKey('paifu-hero-hand')), matching: find.byType(TileView)))
        .length;

    for (final (name, size) in [('태블릿 가로', const Size(1280, 800)), ('폰 세로', const Size(400, 800))]) {
      testWidgets('$name: 걸음을 넘기면 설명·손패·남은 패가 바뀐다', (tester) async {
        await pump(tester, size);
        expect(tester.takeException(), isNull);
        expect(now(tester), '시작');
        expect(heroFaces(tester), 13);
        expect(find.text('남은 패 70'), findsOneWidget);

        await tester.tap(find.byKey(const ValueKey('paifu-next')));
        await tester.pump();
        expect(now(tester), '동 가 · 9삭 버림');

        await tester.tap(find.byKey(const ValueKey('paifu-next')));
        await tester.pump();
        expect(now(tester), '남 나 · 적5삭 뽑음');
        expect(heroFaces(tester), 14);
        expect(find.text('남은 패 68'), findsOneWidget);

        await tester.tap(find.byKey(const ValueKey('paifu-next')));
        await tester.pump();
        expect(now(tester), '남 나 · 중 버림 (손에서)');
        expect(heroFaces(tester), 13);

        await tester.tap(find.byKey(const ValueKey('paifu-prev')));
        await tester.pump();
        expect(heroFaces(tester), 14);

        // 끝으로: 결과 걸음.
        await tester.tap(find.byTooltip('끝'));
        await tester.pumpAndSettle();
        expect(now(tester), '쯔모 (3삭) — 남 나');
        expect(heroFaces(tester), 14);
        expect(find.text('쯔모'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('버림만 적은 패보: 손패 안내 없이 뒷면, 종류 모르는 울기는 "울기", 끝 손패는 결과 걸음에', (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final p = Paifu.fromJson({
        'version': 1,
        'id': 'd',
        'round': '동1국',
        'dealer': 0,
        'hero': 1,
        'names': ['가', '나', '다', '라'],
        'events': [
          {'type': 'discard', 'seat': 0, 'tile': '7z', 'tsumogiri': null, 'riichi': false},
          {'type': 'call', 'seat': 2, 'kind': 'call', 'from': 0, 'tiles': ['7z']},
          {'type': 'discard', 'seat': 2, 'tile': '1s', 'tsumogiri': null, 'riichi': false},
        ],
        'result': {
          'type': 'ron',
          'winner': 1,
          'loser': 2,
          'win_tile': '1s',
          'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '3s'],
        },
      });
      expect(p.hasHeroHands, isFalse);
      expect(p.check(), isEmpty);
      // 울기 뒤 버림은 뽑은 장수에 안 든다.
      expect(p.states[3].draws, 1);
      await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p)));
      await tester.pump();
      expect(find.text('이 순의 손패는 기록에 없습니다'), findsNothing);
      expect(heroFaces(tester), 0);
      await tester.tap(find.byKey(const ValueKey('paifu-next')));
      await tester.tap(find.byKey(const ValueKey('paifu-next')));
      await tester.pump();
      expect(now(tester), '서 다 · 울기 중');
      await tester.tap(find.byTooltip('끝'));
      await tester.pumpAndSettle();
      expect(now(tester), '론 (1삭) — 남 나 ← 서 다');
      expect(heroFaces(tester), 14);
      expect(tester.takeException(), isNull);
    });

    testWidgets('예시 목록: 묶어 둔 판이 한 줄씩 나오고 누르면 재생 화면', (tester) async {
      tester.view.physicalSize = const Size(1280, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.runAsync(() async {
        await tester.pumpWidget(const MaterialApp(home: PaifuAssetListScreen()));
        await Future<void>.delayed(const Duration(milliseconds: 500));
      });
      await tester.pump();
      expect(find.text('2026-11-14 2반장 동1국'), findsOneWidget);
      expect(find.text('2026-11-14 2반장 남4국'), findsOneWidget);
      expect(find.textContaining('유국'), findsNWidgets(4)); // r13 · r15 · r16 · L16(같은 국 둘째 — 제목에 손패 주인)
      expect(find.text('2026-11-14 2반장 남2국 1본장 · 플레이어 2 손패'), findsOneWidget);
      await tester.tap(find.text('2026-11-14 2반장 동2국'));
      await tester.pumpAndSettle();
      expect(find.byType(PaifuScreen), findsOneWidget);
      expect(now(tester), '시작');
    });

    testWidgets('자동 재생은 끝에서 멈춘다', (tester) async {
      await pump(tester, const Size(1280, 800));
      await tester.tap(find.byKey(const ValueKey('paifu-play')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1000));
      expect(now(tester), '동 가 · 9삭 버림');
      for (var i = 0; i < 12; i++) {
        await tester.pump(const Duration(milliseconds: 1000));
      }
      await tester.pumpAndSettle();
      expect(now(tester), '쯔모 (3삭) — 남 나');
      expect(find.byTooltip('자동 재생'), findsOneWidget);
    });
  });
}
