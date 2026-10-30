import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart';
import 'package:mahjong_calc/ui/hand_editor.dart';

/// 입력 화면 값과 계산·기록(label.json)이 어긋나지 않게 하는 규칙(2026-10-30 점검).
void main() {
  test('리치 입력 뒤 울기(치)를 더하면 리치·일발·뒷도라가 꺼진다', () {
    final e = HandEditor()..setRiichi(true);
    e.setIppatsu(true);
    e.uraIndicators.add(Tiles.parse('4s'));
    expect(e.addMeld(Meld.chi(Tiles.parse('2m'))), isNull);
    expect(e.hasRiichi, isFalse);
    expect(e.ippatsu, isFalse);
    expect(e.uraIndicators, isEmpty);
  });

  test('applySituation: 결과 화면 칩으로 고친 상황을 받아들인다', () {
    final e = HandEditor()..setRiichi(true);
    e.uraIndicators.add(Tiles.parse('4s'));
    e.applySituation(e.situation.copyWith(riichi: false));
    expect(e.hasRiichi, isFalse);
    expect(e.uraIndicators, isEmpty, reason: '리치가 꺼지면 뒷도라도');

    e.applySituation(e.situation.copyWith(doubleRiichi: true, ippatsu: true, lastTile: true));
    expect(e.doubleRiichi, isTrue);
    expect(e.riichi, isFalse);
    expect(e.ippatsu, isTrue);
    expect(e.lastTile, isTrue);
  });

  test('applySituation: 울었으면 리치는 켜지지 않는다', () {
    final e = HandEditor();
    expect(e.addMeld(Meld.chi(Tiles.parse('2m'))), isNull);
    e.applySituation(e.situation.copyWith(riichi: true, ippatsu: true));
    expect(e.hasRiichi, isFalse);
    expect(e.ippatsu, isFalse);
  });
}
