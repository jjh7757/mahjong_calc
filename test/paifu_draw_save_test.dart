import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/discard_recorder.dart';
import 'package:mahjong_calc/paifu/draw_paifu.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/paifu/table_facts.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 가운데 기기 반 크기 100, 패 30×40(discard_recorder_test 와 같은 꼴).
const _hd = 100.0;

RiverSighting _at(Side side, int col, String tile, {bool sideways = false}) {
  final u = -77.0 + 31 * col, v = 120.0;
  final (dx, dy) = switch (side) {
    Side.bottom => (u, v),
    Side.right => (v, -u),
    Side.top => (-u, -v),
    Side.left => (-v, u),
  };
  final across = side == Side.bottom || side == Side.top;
  final upright = across != sideways;
  return RiverSighting(dx: dx, dy: dy, w: upright ? 30 : 40, h: upright ? 40 : 30, tile: tile, conf: 0.97);
}

/// 선(아래)부터 두 바퀴 버린 기록기. 오른쪽 자리는 두 번째 버림이 리치 선언패(눕힘).
DiscardRecorder _recorder() {
  final rec = DiscardRecorder(dealer: Side.bottom);
  var t = DateTime(2026, 11, 24, 12);
  final table = <RiverSighting>[];
  const order = [Side.bottom, Side.right, Side.top, Side.left];
  const tiles = ['1z', '9m', '2z', '1p', '5s', '3p', '7z', '9s'];
  for (var i = 0; i < 8; i++) {
    table.add(_at(order[i % 4], i ~/ 4, tiles[i], sideways: i == 5));
    for (var k = 0; k < 2; k++) {
      rec.add(t, [...table], hd: _hd);
      t = t.add(const Duration(seconds: 3));
    }
  }
  return rec;
}

/// 거치 화면이 하는 것과 같게: 사진 아래 자리 2, 친 2.
Paifu? _draw(DiscardRecorder rec, Set<int> tenpai, {PaifuTile? dora}) => drawPaifu(
      events: rec.toPaifu(id: 'g/동3국/1', bottomSeat: 2, dealerSeat: 2, hero: 2).events,
      id: 'g/동3국/1',
      dealerSeat: 2,
      tenpai: tenpai,
      round: '동3국',
      honba: 1,
      names: const ['가', '나', '다', '라'],
      startScores: const [25000, 24000, 26000, 25000],
      kyotaku: 1,
      dora: dora,
    );

void main() {
  test('유국 패보: type draw · 텐파이 자리 순 · 손패 없음 · 메모', () {
    final p = _draw(_recorder(), {3, 1})!;
    expect(p.result!.type, 'draw');
    expect(p.result!.tenpai, [1, 3]);
    expect(p.result!.winner, isNull);
    expect(p.result!.loser, isNull);
    expect(p.result!.winTile, isNull);
    expect(p.result!.hand, isNull);
    expect(p.result!.flags, isNull);
    expect(p.result!.melds, isEmpty);
    expect(p.title, '동3국 1본장');
    expect(p.round, '동3국');
    expect(p.honba, 1);
    expect(p.dealer, 2);
    expect(p.startScores, [25000, 24000, 26000, 25000]);
    expect(p.kyotaku, 1);
    expect(p.note, drawPaifuNote);
    expect(p.hasHeroHands, isFalse);
    // 버림 8장, 자리 번호는 사진 아래 = 2 부터 차례.
    final discards = [for (final e in p.events) if (e.type == PaifuEventType.discard) '${e.seat}${e.tile}'];
    expect(discards, ['21z', '39m', '02z', '11p', '25s', '33p', '07z', '19s']);
    // 오른쪽(자리 3) 두 번째 버림이 리치 선언패.
    expect(p.events.where((e) => e.riichi).map((e) => e.seat), [3]);
    expect(p.check(), isEmpty);
  });

  test('hero: 텐파이 자리 중 첫 자리, 아무도 텐파이가 아니면 친', () {
    expect(drawHero({3, 1}, 2), 1);
    expect(drawHero({2}, 0), 2);
    expect(drawHero(const {}, 2), 2);
    expect(drawHero({7, -1}, 0), 0); // 자리 번호가 아닌 값은 버린다
    final rec = _recorder();
    expect(_draw(rec, {3, 1})!.hero, 1);
    final noten = _draw(rec, const {})!;
    expect(noten.hero, 2);
    expect(noten.result!.tenpai, isEmpty);
  });

  test('도라: 판 중 확정한 표시패 하나, 없으면 빈 목록 · 뒷도라는 늘 빈 목록', () {
    final rec = _recorder();
    final withDora = _draw(rec, {1}, dora: const PaifuTile(4, red: true))!;
    expect(withDora.doraIndicators, [const PaifuTile(4, red: true)]);
    expect(withDora.uraIndicators, isEmpty);
    final none = _draw(rec, {1})!;
    expect(none.doraIndicators, isEmpty);
    expect(none.uraIndicators, isEmpty);
  });

  test('버림이 없으면 null(저장하지 않음)', () {
    expect(drawPaifu(events: const [], id: 'x', dealerSeat: 0, tenpai: {0}), isNull);
    expect(_draw(DiscardRecorder(dealer: Side.bottom), {0}), isNull);
  });

  test('JSON 왕복: tenpai 칸이 남고, 옛 파일(tenpai 없음)은 null', () {
    final p = _draw(_recorder(), {1, 3}, dora: const PaifuTile(30))!;
    final j = jsonDecode(jsonEncode(p.toJson())) as Map<String, dynamic>;
    expect(j['result']['type'], 'draw');
    expect(j['result']['tenpai'], [1, 3]);
    expect((j['result'] as Map).containsKey('flags'), isFalse);
    final back = Paifu.fromJson(j);
    expect(back.result!.type, 'draw');
    expect(back.result!.tenpai, [1, 3]);
    expect(back.hero, 1);
    expect(back.doraIndicators, [const PaifuTile(30)]);
    expect(back.events.length, p.events.length);
    expect(back.check(), isEmpty);
    expect(jsonEncode(back.toJson()), jsonEncode(p.toJson()));

    // 모두 노텐: 빈 목록도 그대로 남는다(모름 null 과 다르다).
    final noten = Paifu.fromJson(jsonDecode(jsonEncode(_draw(_recorder(), const {})!.toJson())) as Map<String, dynamic>);
    expect(noten.result!.tenpai, isEmpty);

    // 옛 파일: result 에 tenpai 가 없으면 null, 다시 쓸 때도 칸을 만들지 않는다.
    final old = Map<String, dynamic>.of(j);
    old['result'] = Map<String, dynamic>.of(j['result'] as Map<String, dynamic>)..remove('tenpai');
    final oldP = Paifu.fromJson(old);
    expect(oldP.result!.tenpai, isNull);
    expect((oldP.toJson()['result'] as Map).containsKey('tenpai'), isFalse);

    // 화료 결과는 tenpai 를 쓰지 않는다.
    const ron = PaifuResult(type: 'ron', winner: 0, loser: 1);
    expect(ron.toJson().containsKey('tenpai'), isFalse);
    expect(PaifuResult.fromJson(ron.toJson()).tenpai, isNull);
  });

  test('탁자 사실표: 유국 패보에서 예외 없이 result.type == draw', () {
    final p = _draw(_recorder(), {1, 3}, dora: const PaifuTile(30))!;
    final f = tableFacts(p);
    expect(() => jsonEncode(f), returnsNormally);
    final game = f['game'] as Map<String, dynamic>;
    final result = game['result'] as Map<String, dynamic>;
    expect(result['type'], 'draw');
    expect(result['winner'], isNull);
    expect(result['loser'], isNull);
    expect(result['win_tile'], isNull);
    expect(game['dora_indicators'], ['4z']);
    expect(game['round'], '동3국');
  });
}
