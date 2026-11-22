import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/paifu/discard_recorder.dart';
import 'package:mahjong_calc/paifu/paifu.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 가운데 기기 반 크기 100, 패 30×40. 강 첫 줄은 기기에서 120, 줄 간격 42, 칸 간격 31.
const _hd = 100.0;

/// 그 자리 기준 (칸 [col], 줄 [row])의 패 한 장을 사진 좌표로. [du]·[dv] = 자리 기준으로 더 밀기.
RiverSighting _at(Side side, int col, int row, String tile,
    {double conf = 0.97, bool sideways = false, double du = 0, double dv = 0}) {
  final u = -77.0 + 31 * col + du, v = 120.0 + 42 * row + dv;
  final (dx, dy) = switch (side) {
    Side.bottom => (u, v),
    Side.right => (v, -u),
    Side.top => (-u, -v),
    Side.left => (-v, u),
  };
  final across = side == Side.bottom || side == Side.top;
  final upright = across != sideways; // 사진에서 세로로 긴가
  return RiverSighting(dx: dx, dy: dy, w: upright ? 30 : 40, h: upright ? 40 : 30, tile: tile, conf: conf);
}

/// 장면을 차례로 넣는다. 장면마다 3초.
class _Feed {
  final DiscardRecorder rec;
  var _t = DateTime(2026, 11, 17, 12);
  _Feed({Side? dealer, DiscardRecorderConfig config = const DiscardRecorderConfig()})
      : rec = DiscardRecorder(dealer: dealer, config: config);

  /// [melds] = 그 장면의 자리별 울기 상자 수(안 주면 기록기가 울기 상자를 모르는 것으로).
  void add(List<RiverSighting> tiles, {int times = 1, Map<Side, int>? melds, Map<Side, List<String>>? meldTiles}) {
    for (var i = 0; i < times; i++) {
      rec.add(_t, tiles, hd: _hd, melds: melds, meldTiles: meldTiles);
      _t = _t.add(const Duration(seconds: 3));
    }
  }

  List<String> river(Side s) =>
      [for (final d in rec.rivers()[s]!) '${d.tile}${d.taken ? '*' : ''}${d.sideways ? '=' : ''}'];
  List<String> line() => [for (final d in rec.timeline()) '${d.side.name} ${d.tile}'];
}

List<T> _pick<T>(List<T> all, List<int> idx) => [for (final i in idx) all[i]];

void main() {
  group('자리 정하기', () {
    test('기기 둘레 띠 안의 패는 그 변의 자리, 띠 밖은 없음', () {
      expect(assignSide(0, 120, _hd)!.$1, Side.bottom);
      expect(assignSide(130, 0, _hd)!.$1, Side.right);
      expect(assignSide(0, -200, _hd)!.$1, Side.top);
      expect(assignSide(-240, 20, _hd)!.$1, Side.left);
      expect(assignSide(0, 30, _hd), isNull); // 기기 위
      expect(assignSide(0, 300, _hd), isNull); // 손패·패산 쪽
    });

    test('자리 기준 좌표: 네 자리 모두 첫 칸이 같은 (u, v)', () {
      for (final s in Side.values) {
        final t = _at(s, 0, 0, '1m');
        final a = assignSide(t.dx, t.dy, _hd)!;
        expect(a.$1, s);
        expect(a.$2, closeTo(-77, 1e-9));
        expect(a.$3, closeTo(120, 1e-9));
      }
    });

    test('모서리: 여섯 칸을 넘은 일곱째 패도 제 자리(u 넘침이 작은 쪽)', () {
      final t = _at(Side.bottom, 6, 0, '1m'); // u = 109: 아래 자리에서 4 넘침, 오른쪽 자리로 보면 20 넘침
      expect(assignSide(t.dx, t.dy, _hd)!.$1, Side.bottom);
    });
  });

  group('버림 기록', () {
    test('차례로 버리면 자리별 강과 한 줄 순서가 나온다', () {
      final f = _Feed(dealer: Side.top);
      final table = <RiverSighting>[];
      // 선(위)부터 위 → 왼쪽 → 아래 → 오른쪽, 두 바퀴.
      const order = [Side.top, Side.left, Side.bottom, Side.right];
      const tiles = ['1m', '2m', '3m', '4m', '5p', '6p', '7p', '8p'];
      for (var i = 0; i < 8; i++) {
        table.add(_at(order[i % 4], i ~/ 4, 0, tiles[i]));
        f.add([...table], times: 2);
      }
      expect(f.river(Side.top), ['1m', '5p']);
      expect(f.river(Side.left), ['2m', '6p']);
      expect(f.river(Side.bottom), ['3m', '7p']);
      expect(f.river(Side.right), ['4m', '8p']);
      expect(f.line(), ['top 1m', 'left 2m', 'bottom 3m', 'right 4m', 'top 5p', 'left 6p', 'bottom 7p', 'right 8p']);
      expect(f.rec.count, 8);
    });

    test('한 장면에 여럿이 새로 보이면 차례(아래 → 오른쪽 → 위 → 왼쪽)로 한 장씩 돌린다', () {
      final f = _Feed(dealer: Side.right);
      f.add([_at(Side.right, 0, 0, '1z')], times: 2);
      // 다음 장면까지 위·왼쪽·아래·오른쪽·위가 버렸다(오른쪽과 위는 두 장째).
      f.add([
        _at(Side.right, 0, 0, '1z'),
        _at(Side.right, 1, 0, '5z'),
        _at(Side.top, 0, 0, '2z'),
        _at(Side.top, 1, 0, '6z'),
        _at(Side.left, 0, 0, '3z'),
        _at(Side.bottom, 0, 0, '4z'),
      ], times: 2);
      expect(f.line(), ['right 1z', 'top 2z', 'left 3z', 'bottom 4z', 'right 5z', 'top 6z']);
    });

    test('선의 강에 패가 두 장면 이어 보이기 전(패 나누는 중)의 패는 버린다', () {
      final f = _Feed(dealer: Side.bottom);
      f.add([_at(Side.left, 2, 0, '9s')]); // 나누다 흘린 패
      f.add([]);
      f.add([_at(Side.bottom, 0, 0, '1m')], times: 2);
      f.add([_at(Side.bottom, 0, 0, '1m'), _at(Side.right, 0, 0, '2m')], times: 2);
      expect(f.river(Side.left), isEmpty);
      expect(f.line(), ['bottom 1m', 'right 2m']);
    });

    test('종류는 확신도 합 투표', () {
      final f = _Feed();
      f.add([_at(Side.bottom, 0, 0, '6p', conf: 0.5)]);
      f.add([_at(Side.bottom, 0, 0, '9p', conf: 0.9)], times: 3);
      final d = f.rec.rivers()[Side.bottom]!.single;
      expect(d.tile, '9p');
      expect(d.seen, 4);
      expect(d.share, closeTo(2.7 / 3.2, 1e-9));
    });

    test('여섯 장이 넘으면 다음 줄, 순서는 줄 → 칸', () {
      final f = _Feed();
      final t = [
        for (var i = 0; i < 8; i++) _at(Side.left, i % 6, i ~/ 6, '${i + 1}s'),
      ];
      // 뒤 줄부터 넣어도 강 위치로 순서를 잡는다.
      f.add(t.reversed.toList(), times: 2);
      expect(f.river(Side.left), ['1s', '2s', '3s', '4s', '5s', '6s', '7s', '8s']);
    });
  });

  group('울려 나감', () {
    test('마지막 칸만 두 장면 안 보이면 울려 나감, 그 자리에 다음 패가 놓여도 따로 적힌다', () {
      final f = _Feed();
      final a = _at(Side.top, 0, 0, '1z'), b = _at(Side.top, 1, 0, '5z');
      f.add([a], times: 2);
      f.add([a, b], times: 2);
      f.add([a], times: 2); // 5z 를 가져감
      expect(f.river(Side.top), ['1z', '5z*']);
      f.add([a, _at(Side.top, 1, 0, '7p')], times: 2);
      expect(f.river(Side.top), ['1z', '5z*', '7p']);
    });

    test('여러 칸이 같이 안 보이면 가림 — 울려 나감이 아니다', () {
      final f = _Feed();
      final t = [for (var i = 0; i < 4; i++) _at(Side.bottom, i, 0, '${i + 1}m')];
      f.add(t, times: 2);
      f.add([t[0], t[1]], times: 3); // 손이 뒤 두 칸을 가림
      f.add(t, times: 2);
      expect(f.river(Side.bottom), ['1m', '2m', '3m', '4m']);
    });

    test('마지막 칸이 확실한 다른 패로 두 장면 이어 읽히면 앞 패는 울려 나간 것', () {
      final f = _Feed();
      final a = _at(Side.bottom, 0, 0, '1m');
      f.add([a, _at(Side.bottom, 1, 0, '5z')], times: 2);
      f.add([a, _at(Side.bottom, 1, 0, '6z')], times: 3); // 빈 장면 없이 發 이 白 자리에
      expect(f.river(Side.bottom), ['1m', '5z*', '6z']);
    });

    test('확신이 낮은 다른 읽기는 같은 칸의 표일 뿐이다', () {
      final f = _Feed();
      f.add([_at(Side.bottom, 0, 0, '4p')], times: 3);
      f.add([_at(Side.bottom, 0, 0, '1s', conf: 0.4)], times: 2);
      expect(f.river(Side.bottom), ['4p']);
    });
  });

  group('한 장면만 보이고 사라진 패', () {
    final a = _at(Side.top, 0, 0, '1z'), b = _at(Side.top, 1, 0, '3z');
    const none = <Side, int>{};

    test('그 무렵 울기 상자가 늘면 울려 나간 버림(버리자마자 가져감)', () {
      final f = _Feed();
      f.add([a, b], times: 3, melds: none);
      f.add([a, b, _at(Side.top, 2, 0, '0p')], melds: none); // 한 장면만 보임
      f.add([a, b], times: 3, melds: {Side.left: 3}); // 왼쪽 자리에 퐁 묶음이 생김
      expect(f.river(Side.top), ['1z', '3z', '0p*']);
    });

    test('울기 상자가 그대로면 헛것 — 버림으로도 울기로도 안 적는다(손에 든 패가 한 번 잡힘)', () {
      final f = _Feed();
      f.add([a, b], times: 3, melds: {Side.left: 3});
      f.add([a, b, _at(Side.top, 2, 0, '1s', dv: 14)], melds: {Side.left: 3});
      f.add([a, b], times: 3, melds: {Side.left: 3});
      expect(f.river(Side.top), ['1z', '3z']);
      // 패보에도 울기 사건이 안 생긴다.
      final p = f.rec.toPaifu(id: 'x', bottomSeat: 0, dealerSeat: 0, hero: 0);
      expect(p.events.where((e) => e.type == PaifuEventType.call), isEmpty);
      // 국 시작 점수 · 공탁: 안 주면 없음(열쇠도 안 생김), 주면 패보 머리에.
      expect(p.startScores, isNull);
      expect(p.kyotaku, isNull);
      expect(p.toJson().containsKey('start_scores'), isFalse);
      final q = f.rec.toPaifu(id: 'x', bottomSeat: 0, dealerSeat: 0, hero: 0, startScores: [25000, 24000, 26000, 24000], kyotaku: 1);
      expect(q.startScores, [25000, 24000, 26000, 24000]);
      expect(q.kyotaku, 1);
      expect(q.toJson()['start_scores'], [25000, 24000, 26000, 24000]);
      expect(jsonEncode(q.events.map((e) => e.toJson()).toList()), jsonEncode(p.events.map((e) => e.toJson()).toList()));
    });

    test('울기 상자가 한 장만 늘어난 것(낱장 헛 검출)은 울기가 아니다', () {
      final f = _Feed();
      f.add([a, b], times: 3, melds: none);
      f.add([a, b, _at(Side.top, 2, 0, '1s')], melds: none);
      f.add([a, b], times: 3, melds: {Side.right: 1});
      expect(f.river(Side.top), ['1z', '3z']);
    });

    test('오래전부터 있던 묶음이나 한참 뒤에 생긴 묶음은 근거가 아니다', () {
      final f = _Feed();
      f.add([a, b], times: 3, melds: {Side.bottom: 3});
      f.add([a, b, _at(Side.top, 2, 0, '1s')], melds: {Side.bottom: 3});
      f.add([a, b], times: 14, melds: {Side.bottom: 3}); // 42초
      f.add([a, b], times: 2, melds: {Side.bottom: 3, Side.left: 3});
      expect(f.river(Side.top), ['1z', '3z']);
    });

    test('두 장면 넘게 보인 패는 울기 상자와 상관없이 울려 나감', () {
      final f = _Feed();
      f.add([a], times: 2, melds: none);
      f.add([a, b], times: 2, melds: none);
      f.add([a], times: 3, melds: none); // 묶음이 카메라에 안 잡힘
      expect(f.river(Side.top), ['1z', '3z*']);
    });

    test('울기 상자 수를 안 받은 기록기는 예전처럼 다 인정한다', () {
      final f = _Feed();
      f.add([a, b], times: 3);
      f.add([a, b, _at(Side.top, 2, 0, '1s')]);
      f.add([a, b], times: 3);
      expect(f.river(Side.top), ['1z', '3z', '1s*']);
    });

    test('방금 사라져 뒤 장면이 아직 없으면 지우지 않는다', () {
      final f = _Feed();
      f.add([a, b], times: 3, melds: none);
      f.add([a, b, _at(Side.top, 2, 0, '1s')], melds: none);
      // 뒤 장면 없음 — 마지막 장면에서 처음 보인 패는 버림으로 남는다.
      expect(f.river(Side.top), ['1z', '3z', '1s']);
    });
  });

  group('울기 묶음', () {
    /// 위 자리가 [tile] 을 버리고(두 장면), 그 패가 사라진 뒤 [side] 자리에 묶음 [meld] 이 생긴 판을 패보로.
    Paifu play(String tile, Side side, List<String> meld, {Side next = Side.left, List<String> had = const []}) {
      final f = _Feed(dealer: Side.top);
      final a = _at(Side.top, 0, 0, '1z');
      Map<Side, List<String>> m(List<String> now) => {side: now};
      f.rec.add(DateTime(2026, 11, 17, 11, 59, 50), [a], hd: _hd, meldTiles: m(had));
      f.rec.add(DateTime(2026, 11, 17, 11, 59, 55), [a], hd: _hd, meldTiles: m(had));
      final b = _at(Side.top, 1, 0, tile);
      for (final (i, now) in [had, had, [...had, ...meld], [...had, ...meld], [...had, ...meld]].indexed) {
        f.rec.add(DateTime(2026, 11, 17, 12, 0, i * 3), i < 2 ? [a, b] : [a, _at(next, 0, 0, '9p')], hd: _hd, meldTiles: m(now));
      }
      // 사진 아래 = 자리 0 → 위 = 2, 왼쪽 = 3, 오른쪽 = 1.
      return f.rec.toPaifu(id: 'm', bottomSeat: 0, dealerSeat: 2, hero: 0);
    }

    String call(Paifu p) {
      final e = p.events.singleWhere((e) => e.type == PaifuEventType.call);
      return '${e.seat}<${e.from} ${e.callKind} ${e.callTiles.join(' ')}';
    }

    test('퐁: 늘어난 상자 셋이 같은 패', () {
      // 맞은편(아래)이 가져감 → 가져온 패는 가운데 칸.
      expect(call(play('5z', Side.bottom, ['5z', '5z', '5z'], next: Side.bottom)), '0<2 pon 5z 5z 5z');
      // 적5 가 낀 퐁: 읽힌 그대로.
      expect(call(play('0p', Side.left, ['5p', '0p', '5p'])), '3<2 pon 0p 5p 5p');
    });

    test('치: 가져간 패를 낀 이어진 세 장, 가져온 패가 첫 칸(왼쪽 자리에서 옴)', () {
      expect(call(play('7m', Side.left, ['8m', '6m', '7m'])), '3<2 chi 7m 6m 8m');
      expect(call(play('1s', Side.left, ['2s', '3s', '1s'])), '3<2 chi 1s 2s 3s');
    });

    test('대명깡: 같은 패 넷', () {
      expect(call(play('9s', Side.right, ['9s', '9s', '9s', '9s'], next: Side.right)), '1<2 kan 9s 9s 9s 9s');
    });

    test('앞서 있던 묶음은 빼고 새로 늘어난 상자만 본다', () {
      expect(call(play('7z', Side.left, ['7z', '7z', '7z'], had: ['5z', '5z', '5z'])), '3<2 pon 7z 7z 7z');
    });

    test('한 장이 가려 둘만 보인 퐁은 보통 패로 채운다', () {
      expect(call(play('3z', Side.left, ['3z', '3z'])), '3<2 pon 3z 3z 3z');
    });

    test('가져간 자리는 다음에 버린 자리가 아니라 울기 상자가 늘어난 자리', () {
      // 다음 버림이 오른쪽에서 처음 보였어도 묶음은 왼쪽에 생겼다.
      expect(call(play('5z', Side.left, ['5z', '5z', '5z'], next: Side.right)), '3<2 pon 5z 5z 5z');
    });

    test('늘어난 상자가 그 패와 상관없으면(남의 손패가 울기로 읽힘) 그 자리는 아니다 — 다음에 버린 자리, 종류 모름', () {
      expect(call(play('5z', Side.right, ['2m', '3m', '4m'])), '3<2 call 5z');
    });

    test('치 모양이 다 안 보이면 가져간 자리만 적는다', () {
      expect(call(play('7m', Side.left, ['7m', '8m'])), '3<2 call 7m');
    });

    test('뒤에 버림이 없으면 쏘인 패 — 펼친 손패가 울기 상자로 읽혀도 울기가 아니다', () {
      final f = _Feed();
      final a = _at(Side.top, 0, 0, '1z'), b = _at(Side.top, 1, 0, '6s');
      f.add([a], times: 2, meldTiles: const {});
      f.add([a, b], times: 2, meldTiles: const {});
      f.add([a], times: 3, meldTiles: {
        Side.left: ['5s', '6s', '7s'],
      });
      expect(f.river(Side.top), ['1z', '6s*']);
      final p = f.rec.toPaifu(id: 'x', bottomSeat: 0, dealerSeat: 0, hero: 0);
      expect(p.events.where((e) => e.type == PaifuEventType.call), isEmpty);
    });

    test('패보로 풀면 묶음이 그 자리에 놓이고 강에서는 빠진다', () {
      final p = play('7m', Side.left, ['8m', '6m', '7m']);
      expect(p.check(), isEmpty);
      final end = p.states.last;
      expect(end.melds[3].single.kind, 'chi');
      expect(end.melds[3].single.tiles.map((t) => t.code), ['7m', '6m', '8m']);
      expect(end.rivers[2].last.called, isTrue);
    });
  });

  group('국의 경계', () {
    test('네 강이 두 장면 이어 비면 지난 국의 칸을 버리고 새로 적는다', () {
      final f = _Feed(dealer: Side.bottom);
      // 지난 국의 끝 탁자에서 기록이 시작됐다.
      final old = [
        for (var i = 0; i < 6; i++) ...[_at(Side.bottom, i, 0, '9m'), _at(Side.top, i, 0, '9p')],
      ];
      f.add(old, times: 3);
      expect(f.rec.count, 12);
      f.add([], times: 4); // 패를 밀어 넣고 새로 나눔
      expect(f.rec.count, 0);
      expect(f.rec.resets, 1);
      // 새 국: 선이 오른쪽으로 바뀜. 선의 강에 패가 두 장면 이어 보인 뒤부터 적는다.
      f.rec.dealer = Side.right;
      f.add([_at(Side.right, 0, 0, '1z')], times: 2);
      f.add([_at(Side.right, 0, 0, '1z'), _at(Side.top, 0, 0, '2z')], times: 2);
      expect(f.line(), ['right 1z', 'top 2z']);
      // 빈 장면이 더 이어져도 비울 칸이 없으면 세지 않는다.
      expect(f.rec.resets, 1);
    });

    test('한 장면만 통째로 안 보이면(가림) 그대로 이어 적는다', () {
      final f = _Feed();
      final t = [for (var i = 0; i < 4; i++) _at(Side.bottom, i, 0, '${i + 1}m')];
      f.add(t, times: 2);
      f.add([]);
      f.add([...t, _at(Side.right, 0, 0, '7z')], times: 2);
      expect(f.rec.resets, 0);
      expect(f.river(Side.bottom), ['1m', '2m', '3m', '4m']);
      expect(f.river(Side.right), ['7z']);
    });
  });

  group('가림·밀림에 버티기', () {
    List<RiverSighting> row(List<String> tiles, {double du = 0}) =>
        [for (final (i, t) in tiles.indexed) _at(Side.left, i % 6, i ~/ 6, t, du: du)];

    test('강을 통째로 한 장 반 밀어도 칸이 따라간다', () {
      final f = _Feed();
      const tiles = ['4z', '2z', '1z', '2p'];
      f.add(row(tiles), times: 3);
      f.add(row(tiles, du: 46), times: 3);
      expect(f.river(Side.left), tiles);
    });

    test('몇 장만 보이는 장면에 새 패가 놓여도 칸이 한 칸씩 밀리지 않는다(11-14 r11 왼쪽)', () {
      final f = _Feed();
      const first = ['4z', '2z', '1z', '2p', '2z', '1p', '9m', '9p'];
      f.add(row(first), times: 5);
      // 손이 왼쪽을 덮어 첫 줄 뒤 세 장만 보이고, 둘째 줄 셋째 칸에 새 패(놓는 중이라 살짝 어긋남).
      f.add([..._pick(row(first), [3, 4, 5]), _at(Side.left, 2, 1, '9s', du: 12)]);
      f.add([...row(first), _at(Side.left, 2, 1, '9s')], times: 3);
      expect(f.river(Side.left), [...first, '9s']);
      for (final d in f.rec.rivers()[Side.left]!) {
        expect(d.share, greaterThan(0.99), reason: '${d.tile} 칸에 다른 패의 표가 섞임');
      }
    });

    test('한 장면에서만 보인 어긋난 상자는 헛것으로 빠진다', () {
      const tiles = ['1m', '2m', '3m'];
      List<RiverSighting> r() => [for (final (i, t) in tiles.indexed) _at(Side.bottom, i, 0, t)];
      // 같은 장면에 진짜 버림(넷째 칸)과 헛 상자(손에 든 패)가 같이 보임 → 헛 상자는 마지막 칸이 아니라서
      // 울려 나감이 안 되고, 한 번뿐이라 빠진다.
      final g = _Feed();
      g.add(r(), times: 2);
      g.add([...r(), _at(Side.bottom, 1, 1, '7p', dv: 20), _at(Side.bottom, 3, 0, '4m')]);
      g.add([...r(), _at(Side.bottom, 3, 0, '4m')], times: 3);
      expect(g.river(Side.bottom), ['1m', '2m', '3m', '4m']);
    });

    test('한 패에 겹친 상자는 하나로', () {
      final a = _at(Side.bottom, 0, 0, '9p');
      final dup = RiverSighting(dx: a.dx + 3, dy: a.dy + 4, w: 24, h: 30, tile: '1s', conf: 0.5);
      expect(dedupeSightings([dup, a]), [a]);
      final f = _Feed();
      f.add([a, dup], times: 3);
      expect(f.river(Side.bottom), ['9p']);
    });
  });

  group('패보로', () {
    test('눕힌 패 = 리치 선언패, 그 뒤 버림은 쯔모기리, 울려 나간 패는 다음에 버린 자리가 가져감', () {
      // 사진 아래 = 자리 2. 선 = 자리 0(위).
      final f = _Feed(dealer: Side.top);
      final t = <RiverSighting>[];
      void put(RiverSighting s) {
        t.add(s);
        f.add([...t], times: 2);
      }

      put(_at(Side.top, 0, 0, '3z')); // 자리 0
      put(_at(Side.left, 0, 0, '4z')); // 자리 1
      put(_at(Side.bottom, 0, 0, '6m', sideways: true)); // 자리 2 리치
      put(_at(Side.right, 0, 0, '7z')); // 자리 3
      t.removeLast(); // 7z 를 자리 0 이 퐁
      f.add([...t], times: 2);
      put(_at(Side.top, 1, 0, '1s'));
      put(_at(Side.left, 1, 0, '0p'));
      put(_at(Side.bottom, 1, 0, '4p'));

      expect(f.river(Side.bottom), ['6m=', '4p']);
      expect(f.river(Side.right), ['7z*']);

      final p = f.rec.toPaifu(
        id: 'g/동1국/0/0',
        bottomSeat: 2,
        dealerSeat: 0,
        hero: 2,
        names: const ['가', '나', '다', '라'],
        round: '동1국',
        result: PaifuResult(type: 'tsumo', winner: 2, winTile: PaifuTile.parse('9s')),
      );
      expect(p.check(), isEmpty);
      final ev = [
        for (final e in p.events)
          e.type == PaifuEventType.call
              ? '${e.seat} call<${e.from} ${e.callTiles.single}'
              : '${e.seat} ${e.tile}${e.riichi ? ' riichi' : ''}${e.tsumogiri == true ? ' tsumogiri' : ''}',
      ];
      expect(ev, ['0 3z', '1 4z', '2 6m riichi', '3 7z', '0 call<3 7z', '0 1s', '1 0p', '2 4p tsumogiri']);
      expect(p.hasHeroHands, isFalse);

      // 걸음으로 풀면: 7z 는 강에서 빠지고 자리 0 의 울기로, 리치봉은 자리 2.
      final end = p.states.last;
      expect(end.rivers[3].single.called, isTrue);
      expect(end.melds[0].single.tiles.single.code, '7z');
      expect(end.riichi, [false, false, true, false]);
      // 버림 7장 가운데 울기 바로 뒤 버림(자리 0 의 1s)은 패산에서 안 뽑았다.
      expect(end.draws, 6);
      // JSON 으로 오가도 같다.
      expect(Paifu.fromJson(p.toJson()).states.length, p.states.length);
    });

    test('마지막 버림이 사라져도(론) 뒤에 버림이 없으면 울기로 적지 않는다', () {
      final f = _Feed();
      final a = _at(Side.bottom, 0, 0, '1m'), b = _at(Side.right, 0, 0, '8m');
      f.add([a], times: 2);
      f.add([a, b], times: 2);
      f.add([a], times: 2);
      final p = f.rec.toPaifu(id: 'x', bottomSeat: 0, dealerSeat: 0, hero: 0);
      expect(p.events.map((e) => e.type), [PaifuEventType.discard, PaifuEventType.discard]);
    });
  });

  // 헛 칸 처리 후보(docs/recorder_ghost_slot_plan_1121.md). A = 옛 동작(dropUnconfirmed false), B = minNewSlotConf 0.5(미채택),
  // C = dropUnconfirmed(채택, 기본 켬). B 만 볼 때는 C 를 명시적으로 끈다.
  group('헛 칸 처리(C 채택, 기본 켬)', () {
    const a = DiscardRecorderConfig(dropUnconfirmed: false);
    const b = DiscardRecorderConfig(minNewSlotConf: 0.5, dropUnconfirmed: false);
    const c = DiscardRecorderConfig(dropUnconfirmed: true);
    const bc = DiscardRecorderConfig(minNewSlotConf: 0.5, dropUnconfirmed: true);

    /// 11-14 r19 오른쪽 꼴: 놓이는 중인 3z 가 제자리 밖에서 0.40 으로 한 장면 → 제자리 3z → 9s → 6s 가 두 장면 보이고
    /// 사라짐(위가 퐁) → 그 자리에 다음 9s(확신도 0.85 — r19 에서는 뒤에 생긴 다른 헛 칸 때문에 6s 칸이 마지막이 아니어서
    /// "바뀜" 규칙이 못 걸렸다. 여기서는 확신도로 그 규칙을 비켜 간다).
    _Feed r19(DiscardRecorderConfig config) {
      final f = _Feed(config: config);
      final t = [
        _at(Side.right, 0, 0, '1z'),
        _at(Side.right, 1, 0, '4z'),
        _at(Side.right, 2, 0, '3z'),
        _at(Side.right, 3, 0, '9s'),
        _at(Side.right, 4, 0, '6s'),
        _at(Side.right, 4, 0, '9s', conf: 0.85), // 0.9 미만 — "마지막 칸이 다른 패로 바뀜" 에는 안 걸림
      ];
      const none = {Side.top: <String>[]};
      f.add(_pick(t, [0, 1]), times: 3, meldTiles: none);
      f.add([..._pick(t, [0, 1]), _at(Side.right, 2, 0, '3z', conf: 0.40, dv: 30)], meldTiles: none); // 놓이는 중
      f.add(_pick(t, [0, 1, 2]), times: 3, meldTiles: none);
      f.add(_pick(t, [0, 1, 2, 3]), times: 3, meldTiles: none);
      f.add(_pick(t, [0, 1, 2, 3, 4]), times: 2, meldTiles: none);
      f.add(_pick(t, [0, 1, 2, 3]), times: 3, meldTiles: {
        Side.top: ['6s', '6s', '6s'],
      });
      f.add(_pick(t, [0, 1, 2, 3, 5]), times: 3, meldTiles: {
        Side.top: ['6s', '6s', '6s'],
      });
      return f;
    }

    test('r19 꼴: 옛 동작(A)은 헛 칸 때문에 6s 울려 나감을 놓치고 6s 칸이 다음 9s 와 합쳐진다', () {
      expect(r19(a).river(Side.right), ['1z', '4z', '3z', '9s', '9s']);
    });

    test('기본 설정은 C(dropUnconfirmed 켬) · B 끔', () {
      const d = DiscardRecorderConfig();
      expect(d.dropUnconfirmed, isTrue);
      expect(d.minNewSlotConf, 0);
    });

    for (final (name, config) in [('B', b), ('C', c), ('B+C', bc), ('기본값', const DiscardRecorderConfig())]) {
      test('r19 꼴: $name 이면 6s 울려 나감(위가 퐁)이 적힌다', () {
        final f = r19(config);
        expect(f.river(Side.right), ['1z', '4z', '3z', '9s', '6s*', '9s']);
        // 사진 아래 = 자리 0 → 오른쪽 = 1, 위 = 2.
        final p = f.rec.toPaifu(id: 'x', bottomSeat: 0, dealerSeat: 1, hero: 0);
        final e = p.events.singleWhere((e) => e.type == PaifuEventType.call);
        expect('${e.seat}<${e.from} ${e.callKind} ${e.callTiles.join(' ')}', '2<1 pon 6s 6s 6s');
      });
    }

    test('C 에서도 버리자마자 가져가 한 장면만 보인 진짜 버림(마지막 칸)은 남는다', () {
      final a = _at(Side.top, 0, 0, '1z'), b3 = _at(Side.top, 1, 0, '3z');
      for (final config in [c, bc]) {
        final f = _Feed(config: config);
        f.add([a, b3], times: 3, melds: const {});
        f.add([a, b3, _at(Side.top, 2, 0, '0p')], melds: const {}); // 한 장면만 보임
        f.add([a, b3], times: 3, melds: {Side.left: 3}); // 왼쪽 자리에 퐁 묶음
        f.add([a, b3, _at(Side.top, 2, 0, '7p')], times: 2, melds: {Side.left: 3}); // 그 자리에 다음 버림
        expect(f.river(Side.top), ['1z', '3z', '0p*', '7p']);
      }
    });

    test('B: 확신도 낮은 상자도 이미 있는 칸에는 붙고, 어느 칸에도 안 붙으면 새 칸을 안 만든다', () {
      final f = _Feed(config: b);
      f.add([_at(Side.bottom, 0, 0, '4p')], times: 3);
      f.add([_at(Side.bottom, 0, 0, '1s', conf: 0.4)], times: 2); // 놓여 있는 패가 흐리게 읽힘
      final d = f.rec.rivers()[Side.bottom]!.single;
      expect(d.tile, '4p');
      expect(d.seen, 5);
      // 떨어진 곳의 낮은 확신도 상자: B 가 없으면(A) 세 장면이면 칸이 되지만 B 는 안 만든다.
      final low = _at(Side.bottom, 2, 0, '8s', conf: 0.4);
      f.add([_at(Side.bottom, 0, 0, '4p'), low], times: 3);
      expect(f.river(Side.bottom), ['4p']);
      final g = _Feed(config: a);
      g.add([_at(Side.bottom, 0, 0, '4p')], times: 3);
      g.add([_at(Side.bottom, 0, 0, '4p'), low], times: 3);
      expect(g.river(Side.bottom), ['4p', '8s']);
    });
  });

  test('겹쳐 보기 상자(사진 비율) → 기록기 입력: 중심·기기 크기는 리치봉 구역에서', () {
    // 4:3 사진, 리치봉 구역이 가로 0.45~0.60(= 세로 단위 0.2), 세로 0.4~0.6.
    final g = sightingsOf(
      [(x: 0.5, y: 0.7, w: 0.03, h: 0.05, tile: '5m', conf: 0.9)],
      zoneXmin: 0.45,
      zoneXmax: 0.60,
      zoneYmin: 0.4,
      zoneYmax: 0.6,
      aspect: 4 / 3,
    );
    expect(g.hd, closeTo(0.1 * deviceShareOfSticksZone, 1e-9));
    final t = g.sightings.single;
    expect(t.dx, closeTo((0.515 - 0.525) * 4 / 3, 1e-9));
    expect(t.dy, closeTo(0.725 - 0.5, 1e-9));
    expect(t.w, closeTo(0.04, 1e-9));
    expect(assignSide(t.dx, t.dy, g.hd)!.$1, Side.bottom);
  });
}
