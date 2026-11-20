import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/tile.dart';
import 'package:mahjong_calc/engine/yaku.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/paifu_score.dart';
import 'package:mahjong_calc/ui/paifu/paifu_screen.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

Paifu _r11() =>
    Paifu.fromJson(jsonDecode(File('assets/paifu/r11_130921.json').readAsStringSync()) as Map<String, dynamic>);

Map<String, dynamic> _discard(int seat, String tile, {bool riichi = false}) =>
    {'type': 'discard', 'seat': seat, 'tile': tile, 'tsumogiri': null, 'riichi': riichi};

/// 자리 1(남)이 123456789m 11p 23s 로 기다리다 화료. [events] 와 결과만 바꿔 쓴다.
Paifu _paifu(List<Map<String, dynamic>> events, Map<String, dynamic> result, {String round = '동1국', int honba = 0}) =>
    Paifu.fromJson({
      'version': 1,
      'id': 't',
      'round': round,
      'honba': honba,
      'dealer': 0,
      'hero': 1,
      'names': ['가', '나', '다', '라'],
      'dora_indicators': ['9s'],
      'ura_indicators': ['8m'],
      'events': events,
      'result': {
        'winner': 1,
        'loser': 2,
        'hand': ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2s', '3s'],
        ...result,
      },
    });

void main() {
  group('패보 → 점수', () {
    test('11-14 r11 예시: 리치 · 핑후 · 도라 1 = 3판 30부, 자 론 3,900', () {
      final s = scoreOf(_r11())!;
      expect(s.result.isValid, isTrue);
      expect(s.situation.riichi, isTrue);
      expect(s.situation.ippatsu, isFalse);
      expect(s.situation.isTsumo, isFalse);
      expect(s.situation.seatWind, Tiles.north); // 선이 자리 0, 화료자는 자리 3
      expect(s.situation.roundWind, Tiles.east);
      expect({for (final y in s.result.yaku) y.yaku}, {Yaku.riichi, Yaku.pinfu, Yaku.dora});
      expect(s.result.han, 3);
      expect(s.result.fu.total, 30);
      expect(s.result.payment.ron, 3900);
    });

    test('리치 뒤 한 바퀴 안에 울기 없이 화료하면 일발, 그 사이 울기가 있으면 아님', () {
      final ippatsu = _paifu(
        [_discard(0, '9p'), _discard(1, '7z', riichi: true), _discard(2, '1s')],
        {'type': 'ron', 'win_tile': '1s'},
      );
      final a = situationOf(ippatsu);
      expect(a.riichi, isFalse);
      expect(a.doubleRiichi, isTrue); // 첫 버림이 리치 선언이고 그 앞에 울기 없음
      expect(a.ippatsu, isTrue);

      final called = _paifu(
        [
          _discard(0, '9p'),
          _discard(1, '7z', riichi: true),
          {'type': 'call', 'seat': 3, 'kind': 'call', 'from': 1, 'tiles': ['7z']},
          _discard(3, '9p'),
          _discard(0, '1s'),
        ],
        {'type': 'ron', 'win_tile': '1s', 'loser': 0},
      );
      expect(situationOf(called).ippatsu, isFalse);

      final later = _paifu(
        [_discard(1, '9p'), _discard(1, '7z', riichi: true), _discard(1, '5z'), _discard(2, '4s')],
        {'type': 'ron', 'win_tile': '4s'},
      );
      final c = situationOf(later);
      expect(c.riichi, isTrue);
      expect(c.doubleRiichi, isFalse);
      expect(c.ippatsu, isFalse);
    });

    test('결과에 적힌 상황(flags)이 있으면 사건보다 그것을 쓴다', () {
      final p = _paifu(
        [_discard(1, '7z', riichi: true), _discard(2, '1s')],
        {
          'type': 'ron',
          'win_tile': '1s',
          'flags': {'riichi': true, 'double_riichi': false, 'ippatsu': false, 'last_tile': true},
        },
      );
      final s = situationOf(p);
      expect(s.riichi, isTrue);
      expect(s.doubleRiichi, isFalse);
      expect(s.ippatsu, isFalse);
      expect(s.lastTile, isTrue);
    });

    test('장풍·자풍·본장·쯔모가 계산에 들어간다', () {
      final p = _paifu(
        [_discard(1, '9p'), _discard(1, '7z', riichi: true), _discard(1, '5z')],
        {'type': 'tsumo', 'win_tile': '4s', 'loser': null},
        round: '남3국',
        honba: 2,
      );
      final s = scoreOf(p)!;
      expect(s.situation.roundWind, Tiles.south);
      expect(s.situation.seatWind, Tiles.south);
      expect(s.situation.honba, 2);
      expect(s.result.isValid, isTrue);
      expect({for (final y in s.result.yaku) y.yaku}, containsAll([Yaku.riichi, Yaku.menzenTsumo, Yaku.pinfu]));
      expect(s.result.payment.honba, 2);
    });

    test('울기 묶음: 새 꼴(kind · tiles)과 옛 꼴(패 목록)을 읽고 점수에 넣는다', () {
      final p = Paifu.fromJson({
        'version': 1,
        'id': 'm',
        'round': '동1국',
        'dealer': 0,
        'hero': 0,
        'events': [_discard(1, '5z')],
        'result': {
          'type': 'ron',
          'winner': 0,
          'loser': 1,
          'win_tile': '5z',
          'hand': ['2m', '3m', '4m', '6p', '7p', '8p', '5z'],
          'melds': [
            {'kind': 'pon', 'tiles': ['7z', '7z', '7z']},
            ['3s', '4s', '0s'],
          ],
        },
      });
      expect([for (final m in p.result!.melds) m.kind], ['pon', 'chi']);
      final s = scoreOf(p)!;
      expect(s.hand.melds.length, 2);
      expect(s.hand.redCount, 1);
      expect(s.result.isValid, isTrue);
      expect({for (final y in s.result.yaku) y.yaku}, contains(Yaku.akaDora));
      // 내보냈다 다시 읽어도 묶음이 남는다.
      final q = Paifu.fromJson(jsonDecode(jsonEncode(p.toJson())) as Map<String, dynamic>);
      expect([for (final m in q.result!.melds) '${m.kind}:${m.tiles.join()}'], ['pon:7z7z7z', 'chi:3s4s0s']);
    });

    test('유국·끝 손패 없음·장수 안 맞는 기록은 점수 없음', () {
      expect(scoreOf(_paifu([], {'type': 'draw', 'winner': null, 'hand': null, 'win_tile': null})), isNull);
      expect(scoreOf(_paifu([], {'type': 'ron', 'win_tile': null})), isNull);
      expect(
        scoreOf(_paifu([], {'type': 'ron', 'win_tile': '1s', 'hand': ['1m', '2m', '3m']})),
        isNull,
      );
    });
  });

  group('패보 화면 → 결과 화면', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));

    Future<void> pump(WidgetTester tester, Paifu p) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: PaifuScreen(paifu: p)));
      await tester.pump();
    }

    /// 자리 0 한 장 버리고 자리 1 이 리치, 자리 2 가 쏘는 짧은 판.
    Paifu short() => _paifu(
          [_discard(0, '9p'), _discard(1, '7z', riichi: true), _discard(2, '1s')],
          {'type': 'ron', 'win_tile': '1s'},
        );

    testWidgets('자동 재생이 끝까지 가면 점수를 계산해 결과 화면을 띄운다(보기 전용)', (tester) async {
      await pump(tester, short());
      await tester.tap(find.byKey(const ValueKey('paifu-play')));
      await tester.pump();
      for (var i = 0; i < 3; i++) {
        await tester.pump(const Duration(milliseconds: 1000));
        expect(find.byType(ResultScreen), findsNothing);
      }
      await tester.pump(const Duration(milliseconds: 1000)); // 끝 걸음
      await tester.pump(const Duration(milliseconds: 500));
      final screen = tester.widget<ResultScreen>(find.byType(ResultScreen));
      expect(screen.viewOnly, isTrue);
      expect(screen.result.isValid, isTrue);
      expect(screen.situation!.ippatsu, isTrue);
      expect(screen.hand!.winTile, Tiles.parse('1s'));
      expect(tester.takeException(), isNull);
    });

    testWidgets('손으로 끝까지 넘기면 바로 띄우지 않고, 단추나 "다음" 을 한 번 더 누르면 띄운다', (tester) async {
      await pump(tester, short());
      await tester.tap(find.byTooltip('끝'));
      await tester.pumpAndSettle();
      expect(find.byType(ResultScreen), findsNothing);
      expect(find.byKey(const ValueKey('paifu-score')), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('paifu-next')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(ResultScreen), findsOneWidget);
    });

    testWidgets('진행 중인 대국이 있어도 패보의 결과 화면에는 "대국에 반영" 이 없다', (tester) async {
      gameStore.start(const ['가', '나', '다', '라'], const GameSettings());
      addTearDown(() => gameStore.current = null);
      await pump(tester, short());
      await tester.tap(find.byTooltip('끝'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('paifu-score')));
      await tester.pump();
      await tester.pump(const Duration(seconds: 12)); // 역 연출이 끝날 때까지
      expect(find.byType(ResultScreen), findsOneWidget);
      expect(find.textContaining('대국에 반영'), findsNothing);
    });

    testWidgets('화료형이 아닌 기록은 결과 화면 대신 까닭을 적는다', (tester) async {
      final bad = _paifu(
        [_discard(2, '9s')],
        {'type': 'ron', 'win_tile': '9s'}, // 23s 에 9s — 화료형 아님
      );
      await pump(tester, bad);
      await tester.tap(find.byKey(const ValueKey('paifu-play')));
      await tester.pump();
      for (var i = 0; i < 4; i++) {
        await tester.pump(const Duration(milliseconds: 1000));
      }
      expect(find.byType(ResultScreen), findsNothing);
      expect(find.byKey(const ValueKey('paifu-score-error')), findsOneWidget);
    });
  });
}
