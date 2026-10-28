import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/engine/calculator.dart' show Tiles;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 실제 서버 응답(게임 화면 2차 실행)에서 가져온 locate JSON.
final Map<String, dynamic> locateJson = {
  'hands': [
    {'side': 'bottom', 'box': [855, 185, 995, 870], 'face_up': true, 'conf': 0.98},
    {'side': 'right', 'box': [225, 740, 745, 845], 'face_up': true, 'conf': 0.96},
    {'side': 'bottom', 'box': [0, 0, 10, 10], 'face_up': false, 'conf': 0.1}, // 중복: 무시
    {'side': 'north', 'box': [0, 0, 10, 10], 'face_up': true, 'conf': 0.5}, // 모르는 side
    {'side': 'top', 'box': [50, 100, 40, 900], 'face_up': true, 'conf': 0.7}, // 뒤집힌 상자
  ],
  'rivers': [
    {'side': 'bottom', 'box': [500, 415, 640, 580], 'conf': 0.9},
    {'side': 'top', 'box': [180, 430, 280, 570], 'conf': 0.9},
  ],
  'dead_wall': null,
  'center': null,
  'notes': '',
  'model': 'gemini-3.8-flash',
  'latency_ms': 5500,
};

Game _game({int dealer = 0, int roundWind = 0, int honba = 0, Set<int>? riichi}) => Game(
      id: 'g',
      startedAt: DateTime(2026, 10, 23),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
      dealer: dealer,
      roundWind: roundWind,
      honba: honba,
      riichiSeats: riichi,
    );

List<Map<String, dynamic>> _tiles(String codes, {double conf = 0.95}) =>
    [for (final c in codes.split(' ')) {'tile': c, 'conf': conf}];

Map<String, dynamic> _center({
  String dora = '',
  Map<String, bool> riichi = const {},
  Map<String, String?> last = const {},
}) =>
    {
      'dora_indicators': dora.isEmpty ? [] : _tiles(dora),
      'riichi': riichi,
      'last_discards': last,
      'last_discards_conf': {for (final k in last.keys) k: 0.9},
    };

void main() {
  group('NormBox', () {
    test('픽셀 변환과 패딩·잘림', () {
      const b = NormBox(800, 100, 900, 600);
      expect(b.toPixels(2000, 1000).toString(), 'PixelRect(200, 800, 1000×100)');
      // 10% 패딩: 너비 500 → 50씩, 높이 100 → 10씩
      final p = b.toPixels(2000, 1000, pad: 0.1);
      expect([p.x, p.y, p.width, p.height], [100, 790, 1200, 120]);
      // 이미지 밖은 잘린다
      final q = const NormBox(0, 0, 100, 100).toPixels(1000, 1000, pad: 0.5);
      expect([q.x, q.y, q.width, q.height], [0, 0, 150, 150]);
    });

    test('fromList 는 범위를 자르고 뒤집힌 상자를 버린다', () {
      expect(NormBox.fromList([-5, 10.6, 1200, 900]), const NormBox(0, 11, 1000, 900));
      expect(NormBox.fromList([500, 100, 400, 900]), isNull);
      expect(NormBox.fromList([1, 2, 3]), isNull);
      expect(NormBox.fromList(['a', 1, 2, 3]), isNull);
    });
  });

  group('TableLayout', () {
    test('서버 JSON 파싱: 자리당 하나, 눕힌 자리, center 는 강 합집합', () {
      final l = TableLayout.fromJson(locateJson);
      expect(l.hands.map((h) => h.side), [Side.bottom, Side.right]);
      expect(l.faceUpSides, [Side.bottom, Side.right]);
      expect(l.singleFaceUp, isNull);
      expect(l.hand(Side.bottom)!.box, const NormBox(855, 185, 995, 870));
      expect(l.river(Side.top)!.conf, 0.9);
      expect(l.center, const NormBox(180, 415, 640, 580));
      expect(l.deadWall, isNull);
      expect(l.latencyMs, 5500);
    });

    test('toJson → fromJson 왕복', () {
      final l = TableLayout.fromJson(locateJson);
      final back = TableLayout.fromJson(l.toJson());
      expect(back.toJson(), l.toJson());
      expect(back.center, l.center);
    });
  });

  group('SeatMap', () {
    test('아래 자리를 기준으로 반시계 순서', () {
      const m = SeatMap(2);
      expect(m.seatOf(Side.bottom), 2);
      expect(m.seatOf(Side.right), 3);
      expect(m.seatOf(Side.top), 0);
      expect(m.seatOf(Side.left), 1);
      for (var s = 0; s < 4; s++) {
        expect(m.seatOf(m.sideOf(s)), s);
      }
      expect(const SeatMap(0).sideOf(3), Side.left);
    });
  });

  group('Cropper', () {
    // 40×20 이미지에 표시점 하나를 찍고 자리별로 돌려 '글자 윗부분이 위로 가는지' 본다.
    img.Image withMarker(int x, int y) {
      final im = img.Image(width: 40, height: 20);
      im.setPixelRgb(x, y, 255, 0, 0);
      return im;
    }

    ({int x, int y}) markerOf(img.Image im) {
      for (var y = 0; y < im.height; y++) {
        for (var x = 0; x < im.width; x++) {
          if (im.getPixel(x, y).r > 128) return (x: x, y: y);
        }
      }
      throw StateError('marker not found');
    }

    const whole = NormBox(0, 0, 1000, 1000);

    test('bottom 은 그대로', () {
      final out = TableImage(withMarker(20, 2)).cropImage(whole);
      expect((out.width, out.height), (40, 20));
      expect(markerOf(out), (x: 20, y: 2));
    });

    test('right: 윗부분이 왼쪽을 향한 것을 바로 세운다', () {
      final out = TableImage(withMarker(2, 10)).cropImage(whole, side: Side.right);
      expect((out.width, out.height), (20, 40));
      final m = markerOf(out);
      expect(m.y, lessThan(5));
      expect((m.x - 10).abs(), lessThan(3));
    });

    test('left: 윗부분이 오른쪽을 향한 것을 바로 세운다', () {
      final out = TableImage(withMarker(37, 10)).cropImage(whole, side: Side.left);
      expect((out.width, out.height), (20, 40));
      final m = markerOf(out);
      expect(m.y, lessThan(5));
      expect((m.x - 10).abs(), lessThan(3));
    });

    test('top: 180도', () {
      final out = TableImage(withMarker(20, 17)).cropImage(whole, side: Side.top);
      expect((out.width, out.height), (40, 20));
      final m = markerOf(out);
      expect(m.y, lessThan(4));
      expect((m.x - 19).abs(), lessThan(3));
    });

    test('구역 크롭과 축소본', () {
      final im = img.Image(width: 400, height: 200);
      final t = TableImage(im);
      final c = t.cropImage(const NormBox(500, 250, 1000, 750));
      expect((c.width, c.height), (200, 100));
      final small = img.decodeJpg(t.shrunkJpeg(maxSide: 100))!;
      expect((small.width, small.height), (100, 50));
      final jpg = t.cropJpeg(const NormBox(0, 0, 500, 500), side: Side.right);
      expect(img.decodeJpg(Uint8List.fromList(jpg))!.width, 100);
    });
  });

  group('읽기 모델', () {
    test('HandReading: 적도라·울기·화료패', () {
      final h = HandReading.fromJson({
        'tiles': _tiles('3m 0m 2p'),
        'melds': [
          {'type': 'chi', 'tiles': ['3s', '4s', '0s'], 'conf': 0.8},
          {'type': 'kan_closed', 'tiles': ['1z', '1z', '1z', '1z'], 'conf': 0.9},
          {'type': 'ron', 'tiles': ['1m', '1m', '1m'], 'conf': 0.9}, // 모르는 type
          {'type': 'pon', 'tiles': ['1m', '1m'], 'conf': 0.9}, // 장수 틀림
        ],
        'win_tile': {'tile': '7s', 'conf': 0.4},
        'latency_ms': 4000,
      });
      expect(h.tiles.map((t) => t.code), ['3m', '0m', '2p']);
      expect(h.tiles[1].red, isTrue);
      expect(h.tiles[1].tile, Tiles.parse('5m'));
      expect(h.melds.length, 2);
      expect(h.melds[0].tiles.map((t) => t.code), ['3s', '4s', '0s']);
      expect(h.melds[1].isOpen, isFalse);
      expect(h.winTile!.code, '7s');
      expect(h.totalTiles, 3 + 1 + 3 + 4);
    });

    test('CenterReading: 네 자리 모두 채우고 없는 값은 null', () {
      final c = CenterReading.fromJson(_center(
        dora: '3p 0s',
        riichi: {'left': true},
        last: {'bottom': '7s', 'top': null},
      ));
      expect(c.doraIndicators.map((t) => t.code), ['3p', '0s']);
      expect(c.riichiAt(Side.left), isTrue);
      expect(c.riichiAt(Side.top), isFalse);
      expect(c.lastDiscardAt(Side.bottom)!.code, '7s');
      expect(c.lastDiscardAt(Side.top), isNull);
      expect(c.lastDiscardAt(Side.right), isNull);
    });
  });

  group('merge', () {
    final seats = const SeatMap(0);

    test('뒷도라: 도라와 구분하지 않고 모두 도라 표시패로 센다', () {
      final center = CenterReading.fromJson({
        ..._center(dora: '5p', last: {'right': '4m'}),
        'ura_dora_indicators': _tiles('9s'),
      });
      expect(center.uraIndicators.map((t) => t.code), ['9s']);
      expect(center.toJson()['ura_dora_indicators'], [
        {'tile': '9s', 'conf': 0.95},
      ]);
      // 공개 전 사진(키 없음)이면 비어 있다.
      expect(CenterReading.fromJson(_center()).uraIndicators, isEmpty);

      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
          'win_tile': {'tile': '4m', 'conf': 0.9},
        }),
        center: center,
        winnerSide: Side.bottom,
        game: _game(riichi: {0}),
        seats: seats,
      );
      expect(m.situation.doraIndicators, [Tiles.parse('5p'), Tiles.parse('9s')]);
      expect(m.situation.uraIndicators, isEmpty);
    });

    group('표시패를 어디서 읽나(매장: 리치 화료면 도라·뒷도라를 손패 옆으로 가져감)', () {
      final hand = HandReading.fromJson({
        'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
        'win_tile': {'tile': '4m', 'conf': 0.9},
      });
      CenterReading center({String dora = '', String side = ''}) => CenterReading.fromJson({
            ..._center(dora: dora),
            'hand_side_indicators': side.isEmpty ? [] : _tiles(side),
          });
      List<int> indicators(CenterReading c, {required bool riichi}) => mergeReading(
            hand: hand,
            center: c,
            winnerSide: Side.bottom,
            game: _game(riichi: riichi ? {0} : null),
            seats: seats,
          ).situation.doraIndicators;
      final p = Tiles.parse;

      test('리치 화료면 손패 옆 표시패를 쓴다(가운데에서 읽은 것이 있어도)', () {
        expect(indicators(center(dora: '3z', side: '5s 9s'), riichi: true), [p('5s'), p('9s')]);
      });

      test('리치가 아니면 가운데(왕패)를 쓴다(손패 옆 패가 있어도)', () {
        expect(indicators(center(dora: '3z', side: '5s 9s'), riichi: false), [p('3z')]);
      });

      test('쓰려던 쪽이 비었으면 다른 쪽', () {
        expect(indicators(center(dora: '3z'), riichi: true), [p('3z')]);
        expect(indicators(center(side: '5s'), riichi: false), [p('5s')]);
      });

      test('깡으로 도라 2장·뒷도라 1장처럼 홀수여도 그대로 센다(짝 검사 없음)', () {
        final m = mergeReading(
          hand: hand,
          center: center(side: '5s 2m 9s'),
          winnerSide: Side.bottom,
          game: _game(riichi: {0}),
          seats: seats,
        );
        expect(m.situation.doraIndicators, [p('5s'), p('2m'), p('9s')]);
        expect(m.flags.map((f) => f.issue), isNot(contains(MergeIssue.tileCountMismatch)));
      });

      test('손패 옆 표시패는 JSON 으로 저장·복원된다', () {
        final c = center(dora: '3z', side: '5s 9s');
        expect(CenterReading.fromJson(c.toJson()).handSideIndicators.map((t) => t.code), ['5s', '9s']);
      });
    });

    test('론: 화료패가 오른쪽 강 끝에 있으면 방총자는 오른쪽 자리', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
          'melds': [],
          'win_tile': {'tile': '4m', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(_center(dora: '5p', last: {'right': '4m', 'top': '9p'})),
        winnerSide: Side.bottom,
        game: _game(dealer: 1, roundWind: 1, honba: 2),
        seats: seats,
      );
      expect(m.winner, 0);
      expect(m.isTsumo, isFalse);
      expect(m.loser, 1);
      expect(m.hand, isNotNull);
      expect(m.hand!.winTile, Tiles.parse('4m'));
      expect(m.closed.length, 14);
      expect(m.situation.seatWind, Tiles.north); // 친이 1이면 자리 0 은 북
      expect(m.situation.roundWind, Tiles.south);
      expect(m.situation.honba, 2);
      expect(m.situation.doraIndicators, [Tiles.parse('5p')]);
      expect(m.situation.riichi, isFalse);
      expect(m.flags, isEmpty);
      expect(m.needsFix, isFalse);
    });

    test('강 끝을 못 읽은 자리가 하나이고 대기패도 하나면 그 자리가 그 패로 쏘였다고 본다', () {
      // 갤러리 D 처럼 南 단기 대기인데 오른쪽 강 끝 판독이 빈 답으로 왔다.
      TableMerge merge(String tiles, Map<String, String?> last) => mergeReading(
            hand: HandReading.fromJson({'tiles': _tiles(tiles)}),
            center: CenterReading.fromJson(_center(last: last)),
            winnerSide: Side.bottom,
            game: _game(),
            seats: seats,
          );

      final m = merge('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 1z 2z', {'right': null, 'top': '9p', 'left': '3z'});
      expect(m.hand, isNotNull);
      expect(m.hand!.winTile, Tiles.parse('2z'));
      expect(m.isTsumo, isFalse);
      expect(m.loser, 1);
      expect(m.hasFlag(MergeIssue.winFromWait), isTrue);
      expect(m.uncertain, isEmpty);

      // 대기패가 수패 5 면 적도라인지 몰라 그 패를 확인하게 한다.
      final five = merge('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 1z 5m', {'right': null, 'top': '9p', 'left': '3z'});
      expect(five.hand!.winTile, Tiles.parse('5m'));
      expect(five.uncertain, {13});

      // 못 읽은 자리가 둘이면 누가 쏘였는지 모른다 → 묻는다.
      final two = merge('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 1z 2z', {'right': null, 'top': null, 'left': '3z'});
      expect(two.hand, isNull);
      expect(two.hasFlag(MergeIssue.winTileUnknown), isTrue);
      expect(two.hasFlag(MergeIssue.winFromWait), isFalse);
    });

    test('화료패 없이 13장이면 강 끝 패 중 화료되는 패로 론, 그 자리가 방총자', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
        }),
        // 위 9p 는 화료가 안 되고, 왼쪽 4m 이 된다.
        center: CenterReading.fromJson(_center(last: {'right': '5z', 'top': '9p', 'left': '4m'})),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(m.closed.length, 14);
      expect(m.hand, isNotNull);
      expect(m.hand!.winTile, Tiles.parse('4m'));
      expect(m.isTsumo, isFalse);
      expect(m.loser, 3);
      expect(m.hasFlag(MergeIssue.winFromDiscard), isTrue);
      expect(m.hasFlag(MergeIssue.winTileAssumed), isFalse);

      // 강 끝 패로도 화료가 안 되면 예전처럼 장수 부족.
      final none = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
        }),
        center: CenterReading.fromJson(_center(last: {'right': '5z', 'top': '9p'})),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(none.hand, isNull);
      expect(none.hasFlag(MergeIssue.tileCountMismatch), isTrue);

      // 왼쪽 강 끝을 못 읽었고 대기패가 1m·4m 둘이라 못 정한다 → 후보를 적어 묻는다.
      expect(none.hasFlag(MergeIssue.winTileUnknown), isTrue);
      expect(none.flags.firstWhere((f) => f.issue == MergeIssue.winTileUnknown).message, contains('1만·4만'));

      // 강 전체만 오고 last_discards 가 없으면 강의 마지막 장을 쓴다.
      final c = CenterReading.fromJson({
        ..._center(),
        'rivers': {'left': ['1z', '9m', '4m']},
      });
      expect(c.lastDiscardAt(Side.left)?.code, '4m');
      expect(c.toJson()['rivers']['left'], ['1z', '9m', '4m']);
    });

    test('왕패 크롭의 도라·뒷도라가 있으면 가운데 판독 대신 쓴다', () {
      final center = CenterReading.fromJson(_center(dora: '2s', riichi: {'right': true}));
      final wall = CenterReading.fromJson({
        ..._center(dora: '9s'),
        'ura_dora_indicators': _tiles('5s'),
      });
      final merged = center.withWall(wall);
      expect(merged.doraIndicators.map((t) => t.code), ['9s']);
      expect(merged.uraIndicators.map((t) => t.code), ['5s']);
      expect(merged.riichiAt(Side.right), isTrue);
      expect(center.withWall(CenterReading.fromJson(_center())).doraIndicators.map((t) => t.code), ['2s']);
    });

    test('쯔모: 어느 강 끝에도 없음. 리치는 사진·기록 불일치 플래그', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
          'win_tile': {'tile': '4m', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(
            _center(riichi: {'top': true}, last: {'right': '1z', 'top': '9p', 'left': '4m'})),
        winnerSide: Side.top,
        game: _game(),
        seats: seats,
      );
      expect(m.winner, 2);
      expect(m.isTsumo, isFalse); // 왼쪽 강 끝 4m → 론
      expect(m.loser, 3);
      expect(m.situation.riichi, isTrue);
      expect(m.hasFlag(MergeIssue.riichiMismatch), isTrue);

      final t = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
          'win_tile': {'tile': '4m', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(_center(last: {'right': '1z'})),
        winnerSide: Side.top,
        game: _game(riichi: {2}),
        seats: seats,
      );
      expect(t.isTsumo, isTrue);
      expect(t.loser, isNull);
      expect(t.situation.riichi, isTrue); // 기록에만 있어도 리치
      expect(t.hasFlag(MergeIssue.riichiMismatch), isTrue);
    });

    test('울린 손패면 사진·기록의 리치를 버리고 riichiImpossible 플래그', () {
      // 실기기 기록(2026-10-23): 발 퐁 손패인데 중앙 판독이 리치 램프를 봤다.
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('7m 8m 9m 7p 8p 9p 8s 9s 5z 5z'),
          'melds': [
            {'type': 'pon', 'tiles': ['6z', '6z', '6z'], 'conf': 0.99},
          ],
          'win_tile': {'tile': '7s', 'conf': 0.99},
        }),
        center: CenterReading.fromJson(_center(riichi: {'top': true}, last: {'bottom': '1s'})),
        winnerSide: Side.top,
        game: _game(),
        seats: seats,
      );
      expect(m.hand, isNotNull);
      expect(m.situation.riichi, isFalse);
      expect(m.hasFlag(MergeIssue.riichiImpossible), isTrue);
      expect(m.hasFlag(MergeIssue.riichiMismatch), isFalse);

      // 기록에 리치가 있어도 마찬가지(점수판에서 잘못 눌렀을 때).
      final r = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('7m 8m 9m 7p 8p 9p 8s 9s 5z 5z'),
          'melds': [
            {'type': 'pon', 'tiles': ['6z', '6z', '6z'], 'conf': 0.99},
          ],
          'win_tile': {'tile': '7s', 'conf': 0.99},
        }),
        center: CenterReading.fromJson(_center(last: {'bottom': '1s'})),
        winnerSide: Side.top,
        game: _game(riichi: {2}),
        seats: seats,
      );
      expect(r.situation.riichi, isFalse);
      expect(r.hasFlag(MergeIssue.riichiImpossible), isTrue);

      // 안깡만 있는 멘젠 손패는 리치 가능.
      final k = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('7m 8m 9m 7p 8p 9p 8s 9s 5z 5z'),
          'melds': [
            {'type': 'kan_closed', 'tiles': ['6z', '6z', '6z', '6z'], 'conf': 0.99},
          ],
          'win_tile': {'tile': '7s', 'conf': 0.99},
        }),
        center: CenterReading.fromJson(_center(riichi: {'top': true}, last: {'bottom': '1s'})),
        winnerSide: Side.top,
        game: _game(riichi: {2}),
        seats: seats,
      );
      expect(k.situation.riichi, isTrue);
      expect(k.hasFlag(MergeIssue.riichiImpossible), isFalse);
    });

    test('울기: 퐁·치(적도라) → 엔진 Meld, 적도라 수 집계', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 1z'),
          'melds': [
            {'type': 'pon', 'tiles': ['7z', '7z', '7z'], 'conf': 0.9},
            {'type': 'chi', 'tiles': ['4s', '0s', '6s'], 'conf': 0.9},
          ],
          'win_tile': {'tile': '1z', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(_center(last: {'left': '1z'})),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(m.hand, isNotNull);
      expect(m.hand!.melds.length, 2);
      expect(m.hand!.melds[1].tiles, [Tiles.parse('4s'), Tiles.parse('5s'), Tiles.parse('6s')]);
      expect(m.meldRed, [0, 1]);
      expect(m.redCount, 1);
      expect(m.hand!.redCount, 1);
      expect(m.loser, 3);
      expect(m.flags, isEmpty);
    });

    test('틀린 치(서버 conf 0)는 고쳐서 넣고 플래그', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 1z 1z 2z 2z'),
          'melds': [
            {'type': 'chi', 'tiles': ['2s', '4s', '0s'], 'conf': 0.0},
          ],
          'win_tile': {'tile': '2z', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(_center()),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(m.hand, isNotNull);
      expect(m.hasFlag(MergeIssue.meldUncertain), isTrue);
      expect(m.hand!.melds.single.tiles.first, Tiles.parse('2s'));
    });

    test('장수가 안 맞으면 hand 는 null', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p'),
          'win_tile': {'tile': '1z', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(_center()),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(m.hand, isNull);
      expect(m.needsFix, isTrue);
      expect(m.hasFlag(MergeIssue.tileCountMismatch), isTrue);
    });

    test('화료패 없음 → 마지막 장 가정. 두 강에 있으면 화료자 다음 차례에 가까운 자리가 방총자. 확신 낮은 패 표시', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': [
            ..._tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
            {'tile': '4m', 'conf': 0.3},
          ],
          'win_tile': null,
        }),
        center: CenterReading.fromJson(_center(last: {'right': '4m', 'left': '4m'})),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(m.hasFlag(MergeIssue.winTileAssumed), isTrue);
      expect(m.hand!.winTile, Tiles.parse('4m'));
      expect(m.isTsumo, isFalse);
      // 아래 화료자 다음 차례는 오른쪽(1). 왼쪽 4m 은 화료자 차례 전에 버린 것(동순 후리텐).
      expect(m.loser, 1);
      expect(m.hasFlag(MergeIssue.loserAmbiguous), isTrue);
      expect(m.flags.firstWhere((f) => f.issue == MergeIssue.loserAmbiguous).message, contains('후리텐'));
      expect(m.uncertain, {13});
      expect(m.hasFlag(MergeIssue.uncertainTiles), isTrue);
    });

    group('론패 후보가 둘 이상이면 화료자 다음 차례에 가까운 자리(동순 후리텐)', () {
      // 13장 경로: 강 끝 중 화료되는 패가 둘.
      test('13장, 위·왼쪽 강 끝이 모두 4m: 아래 화료자 → 위(2)', () {
        final m = mergeReading(
          hand: HandReading.fromJson({'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m')}),
          center: CenterReading.fromJson(_center(last: {'right': '5z', 'top': '4m', 'left': '4m'})),
          winnerSide: Side.bottom,
          game: _game(),
          seats: seats,
        );
        expect(m.hand!.winTile, Tiles.parse('4m'));
        expect(m.isTsumo, isFalse);
        expect(m.loser, 2);
        expect(m.hasFlag(MergeIssue.loserAmbiguous), isTrue);
        expect(m.hasFlag(MergeIssue.winFromDiscard), isFalse);
      });

      test('13장, 아래·오른쪽 강 끝이 모두 4m: 왼쪽 화료자 → 아래(0, 왼쪽의 다음 차례)', () {
        final m = mergeReading(
          hand: HandReading.fromJson({'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m')}),
          center: CenterReading.fromJson(_center(last: {'bottom': '4m', 'right': '4m', 'top': '9p'})),
          winnerSide: Side.left,
          game: _game(),
          seats: seats,
        );
        expect(m.winner, 3);
        expect(m.loser, 0);
        expect(m.hasFlag(MergeIssue.loserAmbiguous), isTrue);
      });

      // 14장 경로: 화료패가 따로 읽혔고 그 패가 두 강 끝에 있다.
      test('14장, 화료패 4m 이 오른쪽·왼쪽 강 끝에: 위 화료자 → 왼쪽(3, 위의 다음 차례)', () {
        final m = mergeReading(
          hand: HandReading.fromJson({
            'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
            'win_tile': {'tile': '4m', 'conf': 0.9},
          }),
          center: CenterReading.fromJson(_center(last: {'right': '4m', 'left': '4m'})),
          winnerSide: Side.top,
          game: _game(),
          seats: seats,
        );
        expect(m.winner, 2);
        expect(m.isTsumo, isFalse);
        expect(m.loser, 3);
        expect(m.hasFlag(MergeIssue.loserAmbiguous), isTrue);
        expect(m.hasFlag(MergeIssue.winTileAssumed), isFalse);
      });

      test('동시 론의 다른 화료자 강은 후보에서 빠진다', () {
        final m = mergeReading(
          hand: HandReading.fromJson({
            'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
            'win_tile': {'tile': '4m', 'conf': 0.9},
          }),
          center: CenterReading.fromJson(_center(last: {'right': '4m', 'left': '4m'})),
          winnerSide: Side.bottom,
          game: _game(),
          seats: seats,
          otherWinners: {Side.right},
        );
        expect(m.loser, 3);
        expect(m.hasFlag(MergeIssue.loserAmbiguous), isFalse);
      });

      test('아래 자리가 1번 자리여도(SeatMap) 차례 계산은 자리 번호 기준', () {
        final m = mergeReading(
          hand: HandReading.fromJson({
            'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
            'win_tile': {'tile': '4m', 'conf': 0.9},
          }),
          center: CenterReading.fromJson(_center(last: {'right': '4m', 'left': '4m'})),
          winnerSide: Side.bottom,
          game: _game(),
          seats: const SeatMap(1),
        );
        expect(m.winner, 1);
        expect(m.loser, 2); // 오른쪽 = 1 + 1
      });
    });

    test('중앙을 못 읽으면 론/쯔모 미정 플래그, 도라 없음', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 2m 3m 4p 5p 6p 7s 8s 9s 1z 1z 2m 3m'),
          'win_tile': {'tile': '4m', 'conf': 0.9},
        }),
        center: null,
        winnerSide: Side.left,
        game: _game(),
        seats: const SeatMap(1),
      );
      expect(m.winner, 0); // left = bottomSeat(1) + 3 = 0
      expect(m.hasFlag(MergeIssue.ronTsumoUnknown), isTrue);
      expect(m.situation.doraIndicators, isEmpty);
      expect(m.hand, isNotNull);
    });

    test('같은 패 5장이면 invalidHand', () {
      final m = mergeReading(
        hand: HandReading.fromJson({
          'tiles': _tiles('1m 1m 1m 1m 4p 5p 6p 7s 8s 9s 1z 1z 2z'),
          'win_tile': {'tile': '1m', 'conf': 0.9},
        }),
        center: CenterReading.fromJson(_center()),
        winnerSide: Side.bottom,
        game: _game(),
        seats: seats,
      );
      expect(m.hand, isNull);
      expect(m.hasFlag(MergeIssue.invalidHand), isTrue);
    });
  });

  test('HandReading·CenterReading toJson → fromJson 왕복', () {
    final h = HandReading.fromJson({
      'tiles': _tiles('3m 0m'),
      'melds': [
        {'type': 'kan_closed', 'tiles': ['1z', '1z', '1z', '1z'], 'conf': 0.9},
      ],
      'win_tile': {'tile': '7s', 'conf': 0.4},
      'notes': 'n',
      'model': 'm',
      'latency_ms': 7,
    });
    final h2 = HandReading.fromJson(h.toJson());
    expect(h2.toJson(), h.toJson());
    expect(h2.tiles[1].red, isTrue);
    expect(h2.melds.single.isOpen, isFalse);

    final c = CenterReading.fromJson(_center(dora: '3p', riichi: {'left': true}, last: {'bottom': '0s'}));
    final c2 = CenterReading.fromJson(c.toJson());
    expect(c2.toJson(), c.toJson());
    expect(c2.lastDiscardAt(Side.bottom)!.red, isTrue);
  });

  test('GameSettings.bottomSeat JSON 왕복과 기본값', () {
    const s = GameSettings(bottomSeat: 3);
    expect(GameSettings.fromJson(s.toJson()).bottomSeat, 3);
    final old = const GameSettings().toJson()..remove('bottomSeat');
    expect(GameSettings.fromJson(old).bottomSeat, 0);
  });

  group('관찰 JSON', () {
    ReadTile t(String c) => ReadTile.fromCode(c, 0.9)!;
    ObservedMeld meld(String codes, {List<int> down = const []}) =>
        ObservedMeld([for (final c in codes.split(' ')) t(c)], faceDown: down, conf: 0.9);

    test('울기 종류는 패 구성으로: 퐁·치·명깡·안깡, 어긋나면 확신 0', () {
      expect(meld('6z 6z 6z').type, ReadMeldType.pon);
      expect(meld('4p 3p 5p').type, ReadMeldType.chi);
      expect(meld('8s 9s 1m').consistent, isFalse);
      expect(meld('8s 9s 1m').toReadMeld().conf, 0);
      expect(meld('1s 1s 1s 1s').type, ReadMeldType.kanOpen);
      expect(meld('1s 1s 1s 1s', down: [0, 3]).type, ReadMeldType.kanClosed);
      expect(meld('0p 5p 5p').type, ReadMeldType.pon);
    });

    test('리치는 리치봉 또는 강의 가로 패, 강 끝 패는 마지막 원소, 도라는 표시패 전부', () {
      final obs = TableObservation(players: {
        Side.top: SeatObservation(
          faceUp: true,
          handTiles: [for (final c in '3s 4s 5p 5p 7z 7z 7z 5z 5z 5z'.split(' ')) t(c)],
          melds: [meld('6z 6z 6z')],
        ),
        Side.right: SeatObservation(river: [RiverTile(t('8s')), RiverTile(t('2s'))], riichiStick: true),
        Side.left: SeatObservation(river: [RiverTile(t('1m'), sideways: true), RiverTile(t('2m'))]),
        Side.bottom: SeatObservation(river: [RiverTile(t('2z'))]),
      }, doraIndicators: [t('9s'), t('5s')]);
      final c = obs.toCenterReading();
      expect([for (final s in Side.values) c.riichiAt(s)], [false, true, false, true]);
      expect(c.lastDiscardAt(Side.right)!.code, '2s');
      expect(c.lastDiscardAt(Side.top), isNull);

      // 대삼원: 10장 + 발 퐁 = 한 장 모자람 → 오른쪽 강 끝 2삭으로 론
      final m = mergeReading(
        hand: obs.toHandReading(Side.top),
        center: c,
        winnerSide: Side.top,
        game: _game(),
        seats: const SeatMap(0),
      );
      expect(m.hand, isNotNull);
      expect(m.loser, 1);
      expect(m.isTsumo, isFalse);
      expect(m.situation.doraIndicators, [Tiles.parse('9s'), Tiles.parse('5s')]);
      expect(obs.toJson()['players']['top']['melds'][0]['tiles'], ['6z', '6z', '6z']);
    });
  });
}
