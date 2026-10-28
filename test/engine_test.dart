import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';

Situation ron({int seat = Tiles.south, int round = Tiles.east, int honba = 0}) =>
    Situation(isTsumo: false, seatWind: seat, roundWind: round, honba: honba);

Situation tsumo({int seat = Tiles.south, int round = Tiles.east}) =>
    Situation(isTsumo: true, seatWind: seat, roundWind: round);

List<Yaku> yakuOf(ScoreResult r) => r.yaku.map((y) => y.yaku).toList();

void main() {
  group('패 파싱', () {
    test('표기법 파싱과 적도라', () {
      final p = parseTiles('123m0p7z');
      expect(p.tiles, [0, 1, 2, 13, 33]);
      expect(p.redCount, 1);
    });

    test('도라 표시패 → 도라', () {
      expect(Tiles.doraFromIndicator(Tiles.parse('9m')), Tiles.parse('1m'));
      expect(Tiles.doraFromIndicator(Tiles.parse('4z')), Tiles.parse('1z'));
      expect(Tiles.doraFromIndicator(Tiles.parse('7z')), Tiles.parse('5z'));
      expect(Tiles.doraFromIndicator(Tiles.parse('5z')), Tiles.parse('6z'));
    });
  });

  group('화료 판정', () {
    test('화료 형태가 아니면 실패', () {
      final r = calculate(Hand.parse('123m456p789s1234m 5m'), ron());
      expect(r.isValid, isFalse);
      expect(r.error, '화료 형태가 아닙니다');
    });

    test('역이 없으면 실패', () {
      final hand =
          Hand.parse('567p789s11m22p 2p', melds: [Meld.chi(Tiles.parse('2m'))]);
      final r = calculate(hand, ron());
      expect(r.isValid, isFalse);
      expect(r.error, '역이 없습니다');
    });
  });

  group('일반역과 점수', () {
    test('핑후 쯔모: 2판 20부, 400/700', () {
      final r = calculate(Hand.parse('123m456p789s23m55p 4m'), tsumo());
      expect(yakuOf(r), containsAll([Yaku.pinfu, Yaku.menzenTsumo]));
      expect(r.han, 2);
      expect(r.fu.total, 20);
      expect(r.payment.tsumoFromNonDealer, 400);
      expect(r.payment.tsumoFromDealer, 700);
    });

    test('핑후 론: 1판 30부, 1000', () {
      final r = calculate(Hand.parse('123m456p789s23m55p 4m'), ron());
      expect(yakuOf(r), [Yaku.pinfu]);
      expect(r.fu.total, 30);
      expect(r.payment.ron, 1000);
    });

    test('도라는 역이 있을 때만 더해진다', () {
      final sit = Situation(
          isTsumo: true,
          seatWind: Tiles.south,
          doraIndicators: [Tiles.parse('3m')]);
      final r = calculate(Hand.parse('123m456p789s23m55p 4m'), sit);
      expect(r.han, 3);
      expect(r.payment.tsumoFromDealer, 1300);
      expect(r.payment.tsumoFromNonDealer, 700);
    });

    test('탕야오 핑후 론: 2판 30부, 2000', () {
      final r = calculate(Hand.parse('234m567p345s67m55s 8m'), ron());
      expect(yakuOf(r), containsAll([Yaku.tanyao, Yaku.pinfu]));
      expect(r.payment.ron, 2000);
    });

    test('치또이쯔 론: 2판 25부, 1600', () {
      final r = calculate(Hand.parse('1133m5577p2299s4z 4z'), ron());
      expect(yakuOf(r), [Yaku.chiitoitsu]);
      expect(r.fu.total, 25);
      expect(r.payment.ron, 1600);
    });

    test('량페코가 치또이쯔보다 높게 선택된다', () {
      final r = calculate(
          Hand.parse('223344m667788p2z 2z'), ron(seat: Tiles.west));
      expect(yakuOf(r), [Yaku.ryanpeikou]);
      expect(r.han, 3);
      expect(r.fu.total, 40);
      expect(r.payment.ron, 5200);
    });

    test('울고 또이또이 + 장풍: 3판 40부, 5200', () {
      final hand = Hand.parse('888m999s2s 2s',
          melds: [Meld.pon(Tiles.east), Meld.pon(Tiles.parse('2p'))]);
      final r = calculate(hand, ron());
      expect(yakuOf(r), containsAll([Yaku.toitoi, Yaku.roundWind]));
      expect(r.han, 3);
      expect(r.fu.total, 40);
      expect(r.payment.ron, 5200);
    });

    test('울고 혼일색 + 연풍패 친 론: 4판 30부, 11600 / 끌어올림이면 12000', () {
      final hand = Hand.parse('456p678p55p11z 1z',
          melds: [Meld.chi(Tiles.parse('1p'))]);
      final r = calculate(hand, ron(seat: Tiles.east));
      expect(yakuOf(r),
          containsAll([Yaku.honitsu, Yaku.seatWind, Yaku.roundWind]));
      expect(r.han, 4);
      expect(r.fu.total, 30);
      expect(r.payment.ron, 11600);

      final k = calculate(hand, ron(seat: Tiles.east),
          rules: const RuleSet(kiriageMangan: true));
      expect(k.limit, Limit.mangan);
      expect(k.payment.ron, 12000);
    });

    test('친 쯔모 삼색 + 백: 4판 30부, 3900 올', () {
      final r =
          calculate(Hand.parse('234m234p234s22m55z 5z'), tsumo(seat: Tiles.east));
      expect(yakuOf(r),
          containsAll([Yaku.sanshokuDoujun, Yaku.haku, Yaku.menzenTsumo]));
      expect(r.fu.total, 30);
      expect(r.payment.tsumoFromNonDealer, 3900);
      expect(r.payment.total, 11700);
    });

    test('청일색 일기통관 핑후 론: 9판 배만 16000', () {
      final r = calculate(Hand.parse('123456789m1123m 4m'), ron());
      expect(yakuOf(r), containsAll([Yaku.chinitsu, Yaku.ittsu, Yaku.pinfu]));
      expect(r.han, 9);
      expect(r.limit, Limit.baiman);
      expect(r.payment.ron, 16000);
    });

    test('본장은 론 300, 쯔모 각 100', () {
      final r = calculate(Hand.parse('123m456p789s23m55p 4m'), ron(honba: 2));
      expect(r.payment.ron, 1600);
    });

    test('쿠이탄 금지면 울고 탕야오는 역 없음', () {
      final hand =
          Hand.parse('567p345s6m 6m', melds: [Meld.chi(Tiles.parse('2m')), Meld.pon(Tiles.parse('4p'))]);
      expect(calculate(hand, ron()).isValid, isTrue);
      expect(
          calculate(hand, ron(), rules: const RuleSet(kuitan: false)).isValid,
          isFalse);
    });
  });

  group('역만', () {
    test('국사무쌍 13면: 더블 역만 64000 / 옵션 끄면 32000', () {
      final hand = Hand.parse('19m19p19s1234567z 1m');
      final r = calculate(hand, ron());
      expect(yakuOf(r), [Yaku.kokushi13]);
      expect(r.payment.ron, 64000);

      final s = calculate(hand, ron(), rules: const RuleSet(doubleYakuman: false));
      expect(yakuOf(s), [Yaku.kokushi]);
      expect(s.payment.ron, 32000);
    });

    test('사암각 단기 쯔모: 16000/32000', () {
      final r = calculate(Hand.parse('111m222p333s444m5z 5z'), tsumo());
      expect(yakuOf(r), [Yaku.suuankouTanki]);
      expect(r.payment.tsumoFromDealer, 32000);
      expect(r.payment.tsumoFromNonDealer, 16000);
    });

    test('샨폰 론이면 사암각이 아니라 또이또이 산안커', () {
      final hand = Hand.parse('111m222p333s44m55z 5z');
      final r = calculate(hand, ron());
      expect(yakuOf(r), containsAll([Yaku.toitoi, Yaku.sanankou, Yaku.haku]));
      expect(r.limit, Limit.mangan);
      expect(r.payment.ron, 8000);

      final t = calculate(hand, tsumo());
      expect(yakuOf(t), [Yaku.suuankou]);
    });

    test('대삼원 + 자일색은 더블 역만', () {
      final r = calculate(Hand.parse('555z666z777z11z22z 2z'), ron());
      expect(yakuOf(r), containsAll([Yaku.daisangen, Yaku.tsuuiisou]));
      expect(r.yakumanCount, 2);
      expect(r.payment.ron, 64000);
    });

    test('순정 구련보등', () {
      final r = calculate(Hand.parse('1112345678999m 5m'), tsumo());
      expect(yakuOf(r), [Yaku.chuuren9]);
    });

    test('천화는 친 첫 쯔모', () {
      final sit = Situation(isTsumo: true, seatWind: Tiles.east, firstTurnWin: true);
      final r = calculate(Hand.parse('123m456p789s23m55p 4m'), sit);
      expect(yakuOf(r), [Yaku.tenhou]);
    });

    test('천화·지화는 화료패를 어느 장으로 넣어도 가장 높은 점수', () {
      final sit = Situation(isTsumo: true, seatWind: Tiles.east, firstTurnWin: true);
      // 같은 14장: 화료패를 1m(쌍퐁)으로 넣든 5z(단기)로 넣든 결과가 같아야 한다.
      final a = calculate(Hand.parse('11m222p333s444z55z 1m'), sit);
      final b = calculate(Hand.parse('111m222p333s444z5z 5z'), sit);
      expect(a.payment.total, b.payment.total);
      expect(yakuOf(a), yakuOf(b));
      expect(yakuOf(a), contains(Yaku.tenhou));
    });

    test('손패 없이 천화·지화만', () {
      final ten = firstTurnWinOnly(
          Situation(isTsumo: true, seatWind: Tiles.east, firstTurnWin: true));
      expect(yakuOf(ten), [Yaku.tenhou]);
      expect(ten.payment.total, 48000);
      final chi = firstTurnWinOnly(
          Situation(isTsumo: true, seatWind: Tiles.south, firstTurnWin: true));
      expect(yakuOf(chi), [Yaku.chiihou]);
      expect(chi.payment.total, 32000);
      expect(chi.summary, '역만');
    });
  });

  group('부수', () {
    test('안깡 자패 32부', () {
      final hand = Hand.parse('234m567p88s23s 4s',
          melds: [Meld.closedKan(Tiles.white)]);
      final r = calculate(hand, ron());
      expect(yakuOf(r), [Yaku.haku]);
      // 20 + 멘젠 론 10 + 백 안깡 32 = 62 → 70
      expect(r.fu.total, 70);
    });

    test('울고 핑후형 론은 30부', () {
      final hand = Hand.parse('456p678s23m55s 4m',
          melds: [Meld.chi(Tiles.parse('2m'))]);
      final r = calculate(hand, ron());
      expect(yakuOf(r), [Yaku.tanyao]);
      expect(r.fu.total, 30);
    });

    test('간짱 대기 멘젠 론 40부', () {
      final sit = Situation(isTsumo: false, seatWind: Tiles.south, riichi: true);
      final r = calculate(Hand.parse('123m456p789s24m55p 3m'), sit);
      expect(yakuOf(r), [Yaku.riichi]);
      expect(r.fu.total, 40);
    });
  });
}
