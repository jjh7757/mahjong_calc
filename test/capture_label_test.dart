import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/ui/game/win_sheet.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/mount/capture_label.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _files = MethodChannel('dev.jjh.mahjong_calc/files');

List<Map<String, dynamic>> _tiles(String codes) => [
  for (final c in codes.split(' ')) {'tile': c, 'conf': 0.99},
];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(CaptureLog.clearPending);

  group('정답 대기', () {
    final t0 = DateTime(2026, 10, 23, 15);

    test('같은 국·시간 안이면 폴더를 한 번만 돌려준다', () {
      CaptureLog.setPending('Download/mahjong_calc/a', '동1국#0', now: t0);
      expect(CaptureLog.takePending('동1국#0', now: t0.add(const Duration(minutes: 3))), 'Download/mahjong_calc/a');
      expect(CaptureLog.takePending('동1국#0', now: t0), isNull);
    });

    test('다른 국이면 안 붙인다(대기는 남는다)', () {
      CaptureLog.setPending('d', '동1국#0', now: t0);
      expect(CaptureLog.takePending('동2국#0', now: t0), isNull);
      expect(CaptureLog.takePending('동1국#0', now: t0), 'd');
    });

    test('시간이 지나면 안 붙인다', () {
      CaptureLog.setPending('d', '동1국#0', now: t0);
      expect(CaptureLog.takePending('동1국#0', now: t0.add(CaptureLog.labelWindow + const Duration(seconds: 1))), isNull);
    });

    test('새 촬영이 앞선 대기를 덮어쓴다', () {
      CaptureLog.setPending('old', '동1국#0', now: t0);
      CaptureLog.setPending('new', '동1국#0', now: t0);
      expect(CaptureLog.takePending('동1국#0', now: t0), 'new');
    });
  });

  group('데스크톱 저장', () {
    test('Android 채널이 없으면 다운로드 폴더 아래 mahjong_calc/<시각>/ 에 쓴다', () async {
      final tmp = Directory.systemTemp.createTempSync('capture_log_');
      CaptureLog.desktopRootOverride = tmp.path;
      addTearDown(() {
        CaptureLog.desktopRootOverride = null;
        tmp.deleteSync(recursive: true);
      });
      final dir = CaptureLog.newDir(DateTime(2026, 10, 26, 15, 30, 5));
      expect(await CaptureLog.save(dir: dir, original: Uint8List.fromList([1, 2, 3]), warnings: ['w']), dir);
      expect(await CaptureLog.saveLabel(dir, {'winner': 0}), isTrue);
      final out = Directory('${tmp.path}/mahjong_calc/20261026_153005');
      expect(File('${out.path}/original.jpg').readAsBytesSync(), [1, 2, 3]);
      expect(jsonDecode(File('${out.path}/meta.json').readAsStringSync())['warnings'], ['w']);
      expect(jsonDecode(File('${out.path}/label.json').readAsStringSync()), {'winner': 0});
    });

    test('flutter test 중에는 기본 폴더(실제 다운로드)에 쓰지 않는다', () async {
      expect(CaptureLog.desktopBase, isNull);
      expect(await CaptureLog.saveFile('Download/mahjong_calc/x', 'a.txt', Uint8List(1), 'text/plain'), isFalse);
    });
  });

  group('label.json', () {
    const outcome = WinOutcome(winner: 2, loser: 0, isTsumo: false, roundLabel: '동1국', honba: 0);

    test('화료패는 마지막, 적도라는 0, 울기·도라·리치를 meta.merge 와 같은 키로', () {
      final e = HandEditor();
      for (final c in ['3m', '4m', '6p', '7p', '8p', '2s', '3s', '4s', '1z', '1z']) {
        e.closed.add(HandTile(Tiles.parse(c)));
      }
      e.closed.insert(1, HandTile(Tiles.parse('5m'), red: true)); // 적5만, 화료패로 지정
      e.winIndex = 1;
      e.melds.add(Meld.pon(Tiles.parse('7z')));
      e.meldRed.add(0);
      e.doraIndicators.add(Tiles.parse('2p'));

      final j = captureLabelJson(e, outcome, now: DateTime(2026, 10, 23));
      expect(j['closed'], ['3m', '4m', '6p', '7p', '8p', '2s', '3s', '4s', '1z', '1z', '0m']);
      expect(j['win_tile'], '0m');
      expect(j['melds'], ['[7z 7z 7z]']);
      expect(j['red_count'], 1);
      expect(j['riichi'], isFalse);
      expect(j['dora_indicators'], ['2p']);
      expect(j['winner'], 2);
      expect(j['loser'], 0);
      expect(j['is_tsumo'], isFalse);
      expect(j['round'], '동1국');
    });

    test('meta.merge 와 label 의 비교 키가 같다', () {
      final g = Game(
        id: 'g',
        startedAt: DateTime(2026, 10, 23),
        settings: const GameSettings(),
        names: const ['A', 'B', 'C', 'D'],
      );
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('7m 8m 9m 7p 8p 9p 8s 9s 5z 5z'),
          'melds': [
            {
              'type': 'pon',
              'tiles': ['6z', '6z', '6z'],
              'conf': 0.99,
            },
          ],
          'win_tile': {'tile': '7s', 'conf': 0.99},
        }),
        center: null,
        winnerSide: Side.top,
        game: g,
        seats: const SeatMap(0),
      );
      final merge = CaptureLog.mergeJson(m);
      final label = captureLabelJson(HandEditor()..setFromMerge(m, g), outcome);
      const keys = [
        'winner',
        'is_tsumo',
        'loser',
        'closed',
        'win_tile',
        'melds',
        'red_count',
        'riichi',
        'dora_indicators',
      ];
      for (final k in keys) {
        expect(merge.containsKey(k), isTrue, reason: k);
        expect(label.containsKey(k), isTrue, reason: k);
      }
      // 그대로 반영했으면 손패 부분은 같다.
      for (final k in ['closed', 'win_tile', 'melds', 'red_count']) {
        expect(label[k], merge[k], reason: k);
      }
      expect(merge['closed'], ['7m', '8m', '9m', '7p', '8p', '9p', '8s', '9s', '5z', '5z', '7s']);
    });
  });

  testWidgets('화료 형태가 아닌 결과에도 "판독 수정" 버튼과 플래그가 있다', (tester) async {
    var fixed = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: ResultScreen(
          result: ScoreResult.failure('화료 형태가 아닙니다'),
          flags: const ['확신이 낮은 패 1장'],
          onFix: () => fixed++,
        ),
      ),
    );
    expect(find.text('화료 형태가 아닙니다'), findsOneWidget);
    expect(find.textContaining('확신이 낮은 패'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('result-fix')));
    expect(fixed, 1);

    // 직접 입력(onFix 없음)이면 버튼이 없다.
    await tester.pumpWidget(MaterialApp(home: ResultScreen(result: ScoreResult.failure('x'))));
    expect(find.byKey(const ValueKey('result-fix')), findsNothing);
  });

  testWidgets('촬영 뒤 같은 국을 "대국에 반영" 하면 label.json 을 쓴다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    addTearDown(gameStore.discardCurrent);

    final saved = <Map<Object?, Object?>>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(_files, (call) async {
      saved.add(call.arguments as Map<Object?, Object?>);
      return 'content://x';
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(_files, null));

    gameStore.resume(
      const ['A', 'B', 'C', 'D'],
      const GameSettings(),
      scores: const [25000, 25000, 25000, 25000],
      roundWind: 1,
      roundNumber: 2,
      honba: 1,
    );
    final g = gameStore.current!;
    // 거치 촬영이 이 국에서 찍었다고 표시.
    CaptureLog.setPending('Download/mahjong_calc/shot1', CaptureLog.roundKey(g.roundLabel, g.honba));

    await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
    // 대국 중 첫 화면은 테이블(폰도 같음, 2026-10-29) → 직접 계산.
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('table-calc')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('game-seat-2')));
    await tester.tap(find.byKey(const ValueKey('game-seat-2')));
    await tester.pump();
    for (final code in parseTiles('123m456p789s23m55p4m').tiles) {
      final key = find.byKey(ValueKey('palette-$code'));
      await tester.ensureVisible(key);
      await tester.tap(key);
      await tester.pump();
    }
    await tester.tap(find.text('점수 계산'));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('대국에 반영'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ChoiceChip, 'A').last);
    await tester.pump();
    await tester.tap(find.text('기록').last);
    await tester.pumpAndSettle();

    final label = saved.where((a) => a['name'] == 'label.json').toList();
    expect(label, hasLength(1));
    expect(label.single['dir'], 'Download/mahjong_calc/shot1');
    final j = jsonDecode(utf8.decode(label.single['bytes'] as Uint8List)) as Map<String, dynamic>;
    expect(j['winner'], 2);
    expect(j['loser'], 0);
    expect(j['is_tsumo'], isFalse);
    expect(j['round'], '남2국 1본장');
    expect(j['honba'], 1);
    expect((j['closed'] as List).length, 14);
    expect(j['win_tile'], '4m');
    expect((j['closed'] as List).last, '4m');
    // 테이블 화면으로 돌아왔고, 손패는 비워졌고 대기도 소진됐다.
    expect(find.byKey(const ValueKey('table-calc')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('table-calc')));
    await tester.pumpAndSettle();
    expect(find.text('손패 0/14'), findsOneWidget);
    expect(CaptureLog.takePending(CaptureLog.roundKey('남2국 1본장', 1)), isNull);
  });
}
