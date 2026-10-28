import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';

void main() {
  test('천화를 켜면 쯔모가 되고 손패 없이 바로 계산', () {
    final e = HandEditor()..setFirstTurnWin(true);
    expect(e.isTsumo, isTrue);
    expect(e.firstTurnWinOnly, isTrue);
    final r = e.calculate();
    expect(r.isValid, isTrue);
    expect(r.yaku.map((y) => y.yaku), [Yaku.tenhou]);
    expect(r.payment.total, 48000);
  });

  test('자 자리면 지화', () {
    final e = HandEditor()
      ..setSeatWind(Tiles.west)
      ..setFirstTurnWin(true);
    expect(e.calculate().yaku.map((y) => y.yaku), [Yaku.chiihou]);
  });

  test('론으로 바꾸거나 부르면 꺼진다', () {
    final e = HandEditor()..setFirstTurnWin(true);
    e.setTsumo(false);
    expect(e.firstTurnWin, isFalse);
    e.setFirstTurnWin(true);
    e.addMeld(Meld.pon(Tiles.white));
    expect(e.firstTurnWin, isFalse);
  });

  test('손패를 넣으면 손패로 계산(다른 역만이 겹침)', () {
    final e = HandEditor()..setFirstTurnWin(true);
    for (final c in ['1z', '1z', '1z', '2z', '2z', '2z', '3z', '3z', '3z', '4z', '4z', '4z', '5z', '5z']) {
      e.add(Tiles.parse(c));
    }
    expect(e.firstTurnWinOnly, isFalse);
    final r = e.calculate();
    expect(r.yaku.map((y) => y.yaku), contains(Yaku.tenhou));
    expect(r.yakumanCount, greaterThan(1));
  });
}
