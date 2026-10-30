import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:mahjong_calc/ui/tile_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final m5 = Tiles.parse('5m'), p5 = Tiles.parse('5p');

  /// 탕야오 손패: 5만·5통이 있고, 적5 는 5만 한 장.
  Hand hand({List<int> redTiles = const [], int redCount = 1}) => Hand(
        closedTiles: [for (final c in '2m 3m 4m 5m 6m 7m 3p 4p 5p 6s 7s 8s 2s 2s'.split(' ')) Tiles.parse(c)],
        winTile: Tiles.parse('2s'),
        redCount: redCount,
        redTiles: redTiles,
      );

  group('어느 패를 적도라 그림으로', () {
    test('종류를 알면 그 패만, 한 장씩', () {
      final r = RedMarks(hand(redTiles: [p5]));
      expect(r.take(m5), isFalse);
      expect(r.take(p5), isTrue);
      expect(r.take(p5), isFalse);
    });

    test('5 가 아닌 패·자패는 적도라가 아니다', () {
      final r = RedMarks(hand(redTiles: [m5]));
      expect(r.take(Tiles.parse('4m')), isFalse);
      expect(r.take(Tiles.parse('5z')), isFalse);
      expect(r.take(m5), isTrue);
    });

    test('개수만 알면 나오는 5 부터 개수만큼', () {
      final r = RedMarks(hand());
      expect(r.marks([Tiles.parse('4m'), m5, p5]), [false, true, false]);
    });

    test('적도라 없으면 일반 패, 손패 없어도 된다', () {
      expect(RedMarks(hand(redCount: 0)).take(m5), isFalse);
      expect(RedMarks(null).take(m5), isFalse);
    });

    test('묶음의 적도라는 그 묶음의 5', () {
      final meld = Meld.chi(Tiles.parse('4p'));
      expect(redTilesOf([m5], [meld], [1]), [m5, p5]);
      expect(redTilesOf(const [], [meld], [0]), isEmpty);
      expect(redTilesOf(const [], [Meld.chi(Tiles.parse('6m'))], [1]), isEmpty, reason: '5 없는 묶음');
    });
  });

  test('병합·입력 화면이 어느 패가 적도라인지 넘긴다', () {
    final g = Game(id: 'g', startedAt: DateTime(2026), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D']);
    final m = mergeReading(
      hand: HandReading(
        tiles: [for (final c in '2m 3m 4m 0m 6m 7m 3p 4p 5p 6s 7s 8s 2s'.split(' ')) ReadTile.fromCode(c, 0.99)!],
        winTile: ReadTile.fromCode('2s', 0.99),
      ),
      center: null,
      winnerSide: Side.bottom,
      game: g,
      seats: const SeatMap(0),
    );
    expect(m.hand!.redCount, 1);
    expect(m.hand!.redTiles, [m5]);

    final e = HandEditor();
    for (final c in '2m 3m 4m 6m 7m 3p 4p 5p 6s 7s 8s 2s 2s'.split(' ')) {
      e.closed.add(HandTile(Tiles.parse(c)));
    }
    e.closed.insert(3, HandTile(m5, red: true));
    expect(e.hand!.redTiles, [m5]);
  });

  group('결과 화면', () {
    setUp(() => SharedPreferences.setMockInitialValues({}));

    List<int> redDrawn(WidgetTester tester) => [
          for (final v in tester.widgetList<TileView>(find.byType(TileView)))
            if (v.red) v.tile,
        ];

    Future<void> open(WidgetTester tester, Size size, {List<String> flags = const []}) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final h = hand(redTiles: [m5]);
      final s = Situation(isTsumo: false, seatWind: Tiles.south);
      await tester.pumpWidget(MaterialApp(home: ResultScreen(result: calculate(h, s), hand: h, situation: s, flags: flags)));
      await tester.pumpAndSettle();
    }

    testWidgets('키오스크: 적5만 을 빨간 그림으로, 5통은 일반 그림', (tester) async {
      await open(tester, const Size(1280, 800));
      expect(redDrawn(tester), [m5]);
    });

    testWidgets('폰: 분해한 손패에서도 같다', (tester) async {
      await open(tester, const Size(400, 900));
      expect(redDrawn(tester), [m5]);
    });

    testWidgets('키오스크: 확인할 것이 길어도 손패에 안 가리고, 누르면 전부 보인다', (tester) async {
      final flags = [for (var i = 1; i <= 6; i++) '$i번 확인 문구입니다. ' * 12];
      await open(tester, const Size(1280, 800), flags: flags);

      final box = find.byKey(const ValueKey('result-kiosk-flags'));
      final bottom = tester.getBottomLeft(box).dy;
      final tiles = find.byType(TileView);
      final top = [for (final e in tiles.evaluate()) tester.getTopLeft(find.byWidget(e.widget).first).dy]
          .reduce((a, b) => a < b ? a : b);
      expect(bottom, lessThanOrEqualTo(top));
      expect(tester.getRect(box).right, lessThanOrEqualTo(1280 - 100), reason: '오른쪽 위 론 도장과 겹치지 않는다');

      await tester.tap(box);
      await tester.pumpAndSettle();
      expect(find.text('• ${flags.last}'), findsOneWidget);
      await tester.tap(find.text('닫기'));
      await tester.pumpAndSettle();
      expect(find.text('• ${flags.last}'), findsNothing);
    });

    testWidgets('키오스크: 확인할 것이 없으면 문구 자리도 없다', (tester) async {
      await open(tester, const Size(1280, 800));
      expect(find.byKey(const ValueKey('result-kiosk-flags')), findsNothing);
    });
  });
}
