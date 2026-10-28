import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/engine/score.dart' show payment;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/ui/game/win_sheet.dart';
import 'package:shared_preferences/shared_preferences.dart';

Game _game({int dealer = 0, int honba = 0}) => Game(
      id: 'p',
      startedAt: DateTime(2026, 10, 27),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      dealer: dealer,
      honba: honba,
    );

const dealerSit = Situation(isTsumo: true, seatWind: Tiles.east);

void main() {
  group('파오 대상 기본점(엔진)', () {
    test('대삼원 8000, 대사희 16000, 대삼원+자일색은 대삼원 몫만', () {
      final daisangen = calculate(Hand.parse('555z666z777z123m9s 9s'), const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(daisangen.yaku.map((y) => y.yaku), contains(Yaku.daisangen));
      expect(paoBasePoints(daisangen), 8000);

      // 울기 대삼원 + 자일색(멘젠이면 사암각 단기까지 붙어 더 커진다).
      final mixed = calculate(
          Hand.parse('111z2z 2z', melds: [Meld.pon(Tiles.white), Meld.pon(Tiles.green), Meld.pon(Tiles.red)]),
          const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(mixed.yaku.map((y) => y.yaku), containsAll([Yaku.daisangen, Yaku.tsuuiisou]));
      expect(mixed.basePoints, 16000);
      expect(paoBasePoints(mixed), 8000);

      final daisuushi = calculate(Hand.parse('111z222z333z444z 5z5z'), const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(daisuushi.yaku.map((y) => y.yaku), contains(Yaku.daisuushi));
      expect(paoBasePoints(daisuushi), 16000);

      final mangan = calculate(Hand.parse('123m456p789s11z22p 2p'), const Situation(isTsumo: false, seatWind: Tiles.south));
      expect(paoBasePoints(mangan), 0);
    });
  });

  group('파오 지불(Game.winDelta)', () {
    test('쯔모: 파오한 사람이 역만 전액, 다른 둘은 0', () {
      final g = _game(dealer: 0);
      // 자(B) 대삼원 쯔모 8000/16000 → 파오 C.
      final p = payment(8000, const Situation(isTsumo: true, seatWind: Tiles.south));
      final pao = payment(8000, const Situation(isTsumo: true, seatWind: Tiles.south, honba: 0));
      g.win(winner: 1, isTsumo: true, payment: p, paoSeat: 2, pao: pao);
      expect(g.scores, [25000, 57000, -7000, 25000]);
      expect(g.events.last.description, contains('파오(C)'));
    });

    test('쯔모 본장: 본장 100씩은 평소대로 셋이 낸다', () {
      final g = _game(dealer: 0, honba: 2);
      final p = payment(8000, const Situation(isTsumo: true, seatWind: Tiles.south, honba: 2));
      final pao = payment(8000, const Situation(isTsumo: true, seatWind: Tiles.south));
      g.win(winner: 1, isTsumo: true, payment: p, paoSeat: 2, pao: pao);
      // A(친) -200, C -32000-200, D -200, B +32600
      expect(g.scores, [24800, 57600, -7200, 24800]);
    });

    test('론: 파오한 사람과 방총자가 절반씩, 본장은 방총자', () {
      final g = _game(dealer: 0, honba: 1);
      final p = payment(8000, const Situation(isTsumo: false, seatWind: Tiles.south, honba: 1)); // 32300
      final pao = payment(8000, const Situation(isTsumo: false, seatWind: Tiles.south));
      g.win(winner: 1, loser: 3, isTsumo: false, payment: p, paoSeat: 2, pao: pao);
      expect(g.scores, [25000, 57300, 9000, 8700]);
    });

    test('파오한 사람이 방총자면 평소대로 전액', () {
      final g = _game(dealer: 0);
      final p = payment(8000, const Situation(isTsumo: false, seatWind: Tiles.south));
      g.win(winner: 1, loser: 2, isTsumo: false, payment: p, paoSeat: 2, pao: p);
      expect(g.scores, [25000, 57000, -7000, 25000]);
      expect(g.events.last.description, isNot(contains('파오')));
    });

    test('대삼원+자일색 더블 역만 쯔모: 대삼원 몫만 파오, 자일색 몫은 셋이 나눔', () {
      final g = _game(dealer: 0);
      final p = payment(16000, const Situation(isTsumo: true, seatWind: Tiles.south)); // 16000/32000 = 64000
      final pao = payment(8000, const Situation(isTsumo: true, seatWind: Tiles.south)); // 8000/16000 = 32000
      g.win(winner: 1, isTsumo: true, payment: p, paoSeat: 3, pao: pao);
      // 자일색 몫: A(친) 16000, C 8000, D 8000. 대삼원 몫 32000 은 D 전액.
      expect(g.scores, [9000, 89000, 17000, -15000]);
    });

    test('친 화료 쯔모 파오: 48000 전액', () {
      final g = _game(dealer: 0);
      final p = payment(8000, dealerSit);
      g.win(winner: 0, isTsumo: true, payment: p, paoSeat: 1, pao: p);
      expect(g.scores, [73000, -23000, 25000, 25000]);
    });

    test('공탁은 평소대로 화료자에게', () {
      final g = _game(dealer: 0)..declareRiichi(3);
      final p = payment(8000, const Situation(isTsumo: true, seatWind: Tiles.south));
      g.win(winner: 1, isTsumo: true, payment: p, paoSeat: 2, pao: p);
      expect(g.scores, [25000, 58000, -7000, 24000]);
      expect(g.riichiSticks, 0);
    });
  });

  group('화료 시트의 파오 칩', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
    });
    tearDown(() {
      if (gameStore.current != null) gameStore.discardCurrent();
    });

    Future<void> open(WidgetTester tester, {int? basePoints, int paoBase = 0, bool isTsumo = true}) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (c) => TextButton(
              onPressed: () => showWinSheet(c, gameStore.current!,
                  basePoints: basePoints, paoBase: paoBase, isTsumo: isTsumo, summary: '역만 32000', winner: 1),
              child: const Text('열기'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('열기'));
      await tester.pumpAndSettle();
    }

    testWidgets('계산해 온 대삼원이면 파오 칩이 뜨고 고르면 전액 지불', (tester) async {
      await open(tester, basePoints: 8000, paoBase: 8000);
      expect(find.byKey(const ValueKey('pao-none')), findsOneWidget);
      expect(find.byKey(const ValueKey('pao-1')), findsNothing); // 화료자 자신은 없음
      await tester.tap(find.byKey(const ValueKey('pao-2')));
      await tester.pumpAndSettle();
      expect(find.textContaining('파오 C 가 32000 전액'), findsOneWidget);
      await tester.tap(find.text('기록'));
      await tester.pumpAndSettle();
      expect(gameStore.current!.scores, [25000, 57000, -7000, 25000]);
    });

    testWidgets('계산해 온 만관이면 파오 칩이 없다', (tester) async {
      await open(tester, basePoints: 2000, paoBase: 0);
      expect(find.byKey(const ValueKey('pao-none')), findsNothing);
    });

    testWidgets('직접 입력에서 역만을 고르면 파오 칩이 뜬다', (tester) async {
      await open(tester);
      expect(find.byKey(const ValueKey('pao-none')), findsNothing);
      await tester.tap(find.widgetWithText(ChoiceChip, '역만'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('pao-none')), findsOneWidget);
    });
  });
}
