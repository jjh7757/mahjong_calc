import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/fixed_layout.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';
import 'package:mahjong_calc/table/table_reading.dart';

const grid = GridZones(x1: 250, x2: 750, y1: 200, y2: 800);

/// 1000×1000 합성 테이블: 초록 펠트, 위·왼쪽·오른쪽 손패는 뒷면([back], 기본 연보라), 아래 손패는 앞면(흰 면 + 무늬 10장).
Uint8List table({bool bottomFaceUp = true, img.Color? back}) {
  final im = img.Image(width: 1000, height: 1000);
  img.fill(im, color: img.ColorRgb8(30, 120, 60));
  final b = back ?? img.ColorRgb8(180, 170, 230), white = img.ColorRgb8(240, 240, 240);
  if (bottomFaceUp) {
    for (var i = 0; i < 10; i++) {
      final x = 350 + i * 30;
      img.fillRect(im, x1: x, y1: 870, x2: x + 26, y2: 930, color: white);
      img.fillRect(im, x1: x + 9, y1: 882, x2: x + 17, y2: 892, color: img.ColorRgb8(20, 20, 20));
      img.fillRect(im, x1: x + 9, y1: 905, x2: x + 17, y2: 915, color: img.ColorRgb8(200, 30, 30));
    }
  } else {
    img.fillRect(im, x1: 350, y1: 870, x2: 650, y2: 930, color: b);
  }
  img.fillRect(im, x1: 350, y1: 70, x2: 650, y2: 130, color: b);
  img.fillRect(im, x1: 70, y1: 350, x2: 130, y2: 650, color: b);
  img.fillRect(im, x1: 870, y1: 350, x2: 930, y2: 650, color: b);
  return Uint8List.fromList(img.encodeJpg(im, quality: 95));
}

http.Response _json(Object body) => http.Response(jsonEncode(body), 200);

/// 요청 본문 [from] 위치 뒤의 첫 JPEG.
img.Image _jpegAt(Uint8List b, int from) {
  for (var i = from; i < b.length - 1; i++) {
    if (b[i] == 0xFF && b[i + 1] == 0xD8) return img.decodeJpg(b.sublist(i))!;
  }
  throw StateError('no jpeg');
}

void main() {
  group('5구역', () {
    test('자리 = 앞 손패 변 + 그 사람 오른쪽 모서리(바람개비)', () {
      expect(grid.seat(Side.bottom), const NormBox(800, 250, 1000, 1000));
      expect(grid.seat(Side.right), const NormBox(0, 750, 800, 1000));
      expect(grid.seat(Side.top), const NormBox(0, 0, 200, 750));
      expect(grid.seat(Side.left), const NormBox(200, 0, 1000, 250));
      expect(grid.center, const NormBox(200, 250, 800, 750));
    });

    test('다섯 구역이 겹치지 않고 사진 전체를 덮는다', () {
      final zones = [for (final s in Side.values) grid.seat(s), grid.center];
      var area = 0;
      for (final z in zones) {
        area += z.width * z.height;
      }
      expect(area, 1000 * 1000);
      for (var y = 5; y < 1000; y += 10) {
        for (var x = 5; x < 1000; x += 10) {
          final p = NormBox(y, x, y + 1, x + 1);
          expect(zones.where((z) => z.containsCenterOf(p)), hasLength(1), reason: '($x, $y)');
        }
      }
    });

    test('강 끝은 가운데 칸 한가운데부터 그 자리 쪽, 옆으로는 가운데 60%', () {
      expect(grid.lastZone(Side.bottom), const NormBox(500, 350, 800, 650));
      expect(grid.lastZone(Side.top), const NormBox(200, 350, 500, 650));
      expect(grid.lastZone(Side.left), const NormBox(320, 250, 680, 500));
      expect(grid.lastZone(Side.right), const NormBox(320, 500, 680, 750));
      expect(grid.sticksZone, const NormBox(290, 325, 710, 675));
    });

    test('JSON 왕복, 선 순서가 틀리면 버림, 예전 panel 은 무시', () {
      expect(GridZones.fromJson(grid.toJson()), grid);
      expect(GridZones.fromJson({...grid.toJson(), 'x1': 800}), isNull);
      expect(
        GridZones.fromJson({
          ...grid.toJson(),
          'panel': [1, 2, 3, 4],
        }),
        grid,
      );
      expect(GridZones.initial.valid, isTrue);
    });
  });

  group('픽셀 판정', () {
    test('앞면 무늬가 있는 아래 자리만 앞면', () {
      final a = analyzeGridShot((table(), grid));
      expect(a.faceUp, [Side.bottom]);
      expect(a.handColors[Side.top]!.$1, greaterThan(0.05)); // 뒷면 비율은 기록용으로 남아 있다
    });

    test('뒷면 색과 상관없다(파랑·초록·노랑·주황·검정)', () {
      for (final c in [
        img.ColorRgb8(40, 90, 200),
        img.ColorRgb8(40, 150, 70),
        img.ColorRgb8(230, 200, 40),
        img.ColorRgb8(230, 110, 30),
        img.ColorRgb8(25, 25, 30),
      ]) {
        expect(analyzeGridShot((table(back: c), grid)).faceUp, [Side.bottom], reason: '$c');
        expect(analyzeGridShot((table(back: c, bottomFaceUp: false), grid)).faceUp, isEmpty, reason: '$c');
      }
    });

    test('눕힌 손패가 없으면 앞면 자리도 없다', () {
      expect(analyzeGridShot((table(bottomFaceUp: false), grid)).faceUp, isEmpty);
    });

    /// 뒷면 비율로는 못 정하는 사진: 아래 자리는 앞면 패(흰 면 + 무늬)지만 연보라 패산이 같이 들어가 있고,
    /// 위 자리에는 무늬 없는 흰 막대(테이블 테두리)만 있어 뒷면 0·흰 면 비율로는 위가 앞면처럼 보인다.
    Uint8List tricky({bool marks = true}) {
      final im = img.Image(width: 1000, height: 1000);
      img.fill(im, color: img.ColorRgb8(30, 120, 60));
      final back = img.ColorRgb8(180, 170, 230), white = img.ColorRgb8(240, 240, 240);
      // 아래 손패 13장: 패마다 흰 면 + 가운데 검은 무늬 둘
      for (var i = 0; i < 13; i++) {
        final x = 300 + i * 30;
        img.fillRect(im, x1: x, y1: 870, x2: x + 26, y2: 930, color: white);
        if (marks) {
          img.fillRect(im, x1: x + 9, y1: 882, x2: x + 17, y2: 892, color: img.ColorRgb8(20, 20, 20));
          img.fillRect(im, x1: x + 9, y1: 905, x2: x + 17, y2: 915, color: img.ColorRgb8(200, 30, 30));
        }
      }
      img.fillRect(im, x1: 780, y1: 820, x2: 990, y2: 860, color: back); // 아래 구역의 패산
      img.fillRect(im, x1: 0, y1: 0, x2: 740, y2: 40, color: white); // 위 구역: 무늬 없는 흰 테두리
      img.fillRect(im, x1: 70, y1: 350, x2: 130, y2: 650, color: back);
      img.fillRect(im, x1: 870, y1: 350, x2: 930, y2: 650, color: back);
      return Uint8List.fromList(img.encodeJpg(im, quality: 95));
    }

    test('패산이 같이 들어가도 앞면 패 무늬가 있는 자리(흰 테두리는 무늬가 없다)', () {
      final a = analyzeGridShot((tricky(), grid));
      expect(a.faceUp, [Side.bottom]);
      expect(a.tilePatterns[Side.bottom]!, greaterThan(1000));
      expect(a.tilePatterns[Side.top], 0);
      expect(a.toJson()['tile_patterns'], isA<Map<String, dynamic>>());
    });

    test('무늬 없는 흰 면(테두리·白 만 든 자리)은 앞면으로 보지 않는다 → 네 자리를 다 읽게 비운다', () {
      final a = analyzeGridShot((tricky(marks: false), grid));
      expect(a.faceUp, isEmpty);
    });

    test('두 자리가 비슷하게 앞면이면 둘 다(더블론), 무늬 많은 순', () {
      expect(faceUpByPattern({Side.bottom: 2000, Side.right: 1200, Side.top: 0, Side.left: 50}, 1), [Side.bottom, Side.right]);
      expect(faceUpByPattern({Side.bottom: 2000, Side.right: 900, Side.top: 0, Side.left: 50}, 1), [Side.bottom]);
      expect(faceUpByPattern({Side.bottom: 250, Side.right: 0, Side.top: 0, Side.left: 0}, 1), isEmpty);
    });
  });

  group('readGrid', () {
    const hand13 = ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2p', '3p'];

    /// [faceUp] 자리만 손패를 앞면으로 답한다. [dora] 는 가운데 도라 판독 답, [loose] 는 자리 판독의 따로 놓인 패.
    MockClient server(
      List<String> names,
      Map<String, img.Image> images, {
      Set<String> faceUp = const {'bottom'},
      List<String> dora = const ['5s'],
      List<String> loose = const [],
      Map<String, Object>? agreement,
      List<String>? handonlyTiles,
      bool handonlySeparate = true,
      String trackedLastTile = '4p',
    }) => MockClient((r) async {
      // 강 끝(/v2/last3)은 한 요청에 사진 여러 장이다. 사진마다 이름·그림을 남긴다.
      final files = RegExp(r'filename="([^"]+)\.jpg"').allMatches(latin1.decode(r.bodyBytes)).toList();
      final name = files.isEmpty ? '' : files.first.group(1)!;
      for (final m in files) {
        names.add(m.group(1)!);
        images[m.group(1)!] = _jpegAt(r.bodyBytes, m.end);
      }
      return switch (r.url.path) {
        // 손패 전용(울기는 추적이 안다): 손패 줄 + 떨어진 한 장. 기본은 울기 하나에 맞는 10 + 1 장.
        '/v2/handonly' => _json({
          'face_up': true,
          'tiles': [
            for (final c in handonlyTiles ?? hand13.take(10)) {'tile': c, 'conf': 0.9},
          ],
          'separate_tile': handonlySeparate ? {'tile': '4p', 'conf': 0.9} : null,
          'melds': [],
          'loose': [],
          'agreement': {'reads': 3, 'agree': 3, 'unanimous': true, 'alternatives': []},
        }),
        '/v2/seat' => _json({
          'face_up': faceUp.contains(name.substring(5)),
          'tiles': faceUp.contains(name.substring(5))
              ? [
                  for (final c in hand13) {'tile': c, 'conf': 0.9},
                ]
              : [],
          'separate_tile': null,
          'melds': [],
          'loose': [
            for (final c in loose) {'tile': c, 'conf': 0.9},
          ],
          'agreement': ?agreement,
        }),
        // 오른쪽 강 끝 4통 → 1p 2p 3p 와 1p 머리로 론. 위는 9삭, 아래는 7만, 왼쪽은 강 없음.
        '/v2/corner' => _json({
          'melds': [
            {
              'tiles': ['6z', '6z', '6z'],
              'sideways': [1],
              'face_down': [],
              'conf': 0.9,
            },
          ],
          'loose': [
            {'tile': '9s', 'conf': 0.9},
          ],
        }),
        // 추적이 본 마지막 버림패 한 장만 잘라 읽는 호출.
        '/v2/last' => _json({
          'last_tile': {'tile': trackedLastTile, 'conf': 0.9},
          'tile_count': 1,
        }),
        '/v2/last3' => _json({
          'rivers': [
            for (final m in files)
              {
                'last_tile': switch (m.group(1)) {
                  'last_right' => {'tile': '4p', 'conf': 0.9},
                  'last_top' => {'tile': '9s', 'conf': 0.9},
                  'last_bottom' => {'tile': '7m', 'conf': 0.9},
                  _ => null,
                },
                'tile_count': 7,
              },
          ],
        }),
        '/v2/sticks' => _json({
          'riichi_sticks': {'bottom': false, 'right': false, 'top': true, 'left': false},
        }),
        '/v2/dora' => _json({
          'indicators': [
            for (final c in dora) {'tile': c, 'conf': 0.9},
          ],
        }),
        _ => http.Response('nope', 404),
      };
    });

    test('추적한 마지막 버림패: 그 패만 따로 잘라 읽어 강 끝 판독이 빈 자리를 채우고, 자리를 방총자 힌트로 넘긴다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images));
      // 왼쪽 강 끝은 /v2/last3 가 "강 없음" 으로 답하는 자리. 추적이 그 자리의 마지막 버림 위치를 안다고 치자.
      final discard = Discard(
        side: Side.left,
        box: const NormBox(480, 300, 520, 330),
        seq: 3,
        at: DateTime(2026, 10, 28),
        tiles: 1,
      );
      final reading = await TableReader(client).readGrid(table(), grid, trackedDiscard: discard, trackedRiichi: {Side.left});
      expect(names, contains('last_tracked'));
      // 패 한 장 크기 상자(여백 60%)만 잘라 보낸다 — 강 끝 크롭(수백 px)보다 훨씬 작다.
      expect(images['last_tracked']!.width, lessThan(150));
      expect(images['last_tracked']!.height, lessThan(150));
      expect(reading.center!.lastDiscardAt(Side.left)?.code, '4p');
      expect(reading.center!.lastDiscardAt(Side.right)?.code, '4p'); // 촬영 판독 그대로
      expect(reading.trackedDiscardSide, Side.left);
      // 리치봉: 촬영 판독(위)에 추적(왼쪽)을 더한다.
      expect(reading.center!.riichiAt(Side.left), isTrue);
      expect(reading.center!.riichiAt(Side.top), isTrue);
      expect(reading.center!.riichiAt(Side.right), isFalse);
      expect(reading.warnings.where((w) => w.contains('다릅니다')), isEmpty);
    });

    test('추적한 마지막 버림패가 촬영 판독과 다르면 촬영 판독을 쓰고 경고를 남긴다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, trackedLastTile: '6s'),
      );
      final discard = Discard(
        side: Side.right,
        box: const NormBox(480, 680, 520, 710),
        seq: 1,
        at: DateTime(2026, 10, 28),
        tiles: 1,
      );
      final reading = await TableReader(client).readGrid(table(), grid, trackedDiscard: discard);
      expect(reading.center!.lastDiscardAt(Side.right)?.code, '4p');
      expect(reading.warnings.join(), contains('6s'));
      expect(reading.warnings.join(), contains('다릅니다'));
    });

    test('추적한 버림이 화료자 자리면 따로 읽지 않는다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images));
      final discard = Discard(
        side: Side.bottom,
        box: const NormBox(700, 480, 740, 510),
        seq: 1,
        at: DateTime(2026, 10, 28),
        tiles: 1,
      );
      await TableReader(client).readGrid(table(), grid, trackedDiscard: discard);
      expect(names, isNot(contains('last_tracked')));
    });

    test('픽셀로 화료자를 정하면 그 자리 하나만 읽고, 강은 마지막 패만·리치는 리치봉만 본다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images));
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, trace: trace);

      expect(names.toSet(), {'seat_bottom', 'last_right', 'last_top', 'last_left', 'sticks', 'dora'});
      // 장면 시간을 정하는 자리 판독을 먼저 보낸다(나머지 구역은 그 뒤에 잘라 보냄).
      expect(names.first, 'seat_bottom');
      // 아래 자리 = 750×200 그대로, 오른쪽 강 끝은 오른쪽 자리 방향으로 세워 가로·세로가 바뀐다.
      expect(images['seat_bottom']!.width, 750);
      expect(images['seat_bottom']!.height, 200);
      expect(images['last_right']!.width, 360);
      expect(images['last_right']!.height, 250);
      expect(images['dora']!.width, 500, reason: '도라는 가운데 칸 전체에서');

      expect(reading.winnerSide, Side.bottom);
      expect(trace.layoutMode, 'grid');
      expect(reading.hand!.tiles, hasLength(13));
      final c = reading.center!;
      expect(c.lastDiscards[Side.right]!.code, '4p');
      expect(c.lastDiscards[Side.top]!.code, '9s');
      expect(c.lastDiscards[Side.left], isNull);
      expect(c.riichiAt(Side.top), isTrue);
      expect(c.riichiAt(Side.right), isFalse);
      expect(c.doraIndicators.single.code, '5s');
    });

    test('픽셀로 못 정하면 네 자리를 다 읽어 모델이 앞면이라 한 자리를 화료자로', () async {
      final names = <String>[];
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, {}, faceUp: {'left'}),
      );
      var asked = false;
      final reading = await TableReader(client).readGrid(
        table(bottomFaceUp: false),
        grid,
        pickWinners: (_) async {
          asked = true;
          return null;
        },
      );
      expect(asked, isFalse);
      expect(reading.winnerSide, Side.left);
      expect(names.where((n) => n.startsWith('seat_')), hasLength(4));
      expect(names.where((n) => n.startsWith('last_')), hasLength(4));
      // 화료자 자신의 강 끝은 버린다.
      expect(reading.center!.lastDiscards[Side.left], isNull);
      expect(reading.center!.lastDiscards[Side.bottom]!.code, '7m');
    });

    test('모델도 앞면 자리를 못 찾으면 네 자리 중에서 묻는다', () async {
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server([], {}, faceUp: {}),
      );
      List<Side>? asked;
      final reading = await TableReader(client).readGrid(
        table(bottomFaceUp: false),
        grid,
        pickWinners: (c) async {
          asked = c;
          return [Side.bottom];
        },
      );
      expect(asked, Side.values);
      expect(reading.winnerSide, Side.bottom);
      expect(reading.others, isEmpty);
    });

    test('앞면 자리가 둘이고 둘 다 고르면(더블론) 각자 판독, 서로의 강 끝은 남긴다', () async {
      final names = <String>[];
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, {}, faceUp: {'left', 'top'}),
      );
      List<Side>? asked;
      final reading = await TableReader(client).readGrid(
        table(bottomFaceUp: false),
        grid,
        pickWinners: (c) async {
          asked = c;
          return [Side.top, Side.left];
        },
      );
      expect(asked, [Side.top, Side.left]);
      expect(reading.winnerSide, Side.top);
      expect(reading.hand!.tiles, hasLength(13));
      final other = reading.others.single;
      expect(other.winnerSide, Side.left);
      expect(other.hand!.tiles, hasLength(13));
      // 각자 자기 강 끝은 버리고, 상대 화료자의 강 끝은 그대로(방총자 후보에서 빼는 건 merge).
      expect(reading.center!.lastDiscards[Side.top], isNull);
      expect(other.center!.lastDiscards[Side.left], isNull);
      expect(other.center!.lastDiscards[Side.top]!.code, '9s');
      expect(names.where((n) => n.startsWith('seat_')), hasLength(4), reason: '네 자리를 한 번씩만 읽는다');
    });

    /// 판 상태 추적이 확정한 아래 자리 울기(퐁 6z).
    final trackedPon = {
      Side.bottom: [ObservedMeld([for (var i = 0; i < 3; i++) ReadTile.fromCode('6z', 1)!], sideways: const [1])],
    };

    test('추적으로 울기를 아는 자리는 손패 칸만 /v2/handonly 로 읽고, 울기를 채워 돌려준다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images));
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, tracked: trackedPon, trace: trace);

      expect(names, contains('handonly_bottom'));
      expect(names, isNot(contains('seat_bottom')));
      // 손패 칸(선 사이)만: 500×200. 자리 전체(750×200)가 아니다.
      expect(images['handonly_bottom']!.width, 500);
      expect(images['handonly_bottom']!.height, 200);
      expect(reading.hand!.tiles, hasLength(10));
      expect(reading.hand!.winTile!.code, '4p');
      expect(reading.hand!.melds, hasLength(1));
      expect(reading.hand!.melds.single.tiles.map((t) => t.code), everyElement('6z'));
      expect(reading.meldsTracked, isTrue);
      expect(trace.trackedMode[Side.bottom], 'handonly');
      expect(trace.callMs, contains('handonly_bottom'));
      expect(trace.shadow, isEmpty);
    });

    test('그림자 모드면 같은 사진으로 /v2/seat 도 같이 보내 두 답을 trace 에 남기고, 결과는 손패 전용 쪽', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images));
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, tracked: trackedPon, shadow: true, trace: trace);

      expect(names, containsAll(['handonly_bottom', 'seat_bottom']));
      expect(images['seat_bottom']!.width, 750, reason: '그림자 쪽은 자리 전체');
      final sh = trace.shadow[Side.bottom]!;
      expect(sh.handonly['tiles'], hasLength(10));
      expect(sh.seat['tiles'], hasLength(13));
      expect(sh.toJson().keys, containsAll(['handonly', 'seat', 'handonly_ms', 'seat_ms']));
      expect(reading.hand!.tiles, hasLength(10), reason: '결과는 손패 전용');
      expect(reading.meldsTracked, isTrue);
    });

    test('론 패가 아직 방총자 강에 있어 손패가 10장뿐이어도(울기 1) 장수 검사를 통과한다 — 노트북 흐름 확인에서 발견', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, handonlySeparate: false),
      );
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, tracked: trackedPon, trace: trace);
      expect(names, isNot(contains('seat_bottom')));
      expect(trace.trackedMode[Side.bottom], 'handonly');
      expect(reading.hand!.tiles, hasLength(10));
      expect(reading.hand!.melds, hasLength(1));
      expect(reading.meldsTracked, isTrue);
    });

    test('손패 장수가 미리 읽은 울기와 맞지 않으면 자리 전체를 /v2/seat 로 다시 읽는다(지금 방식으로 복귀)', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      // 손패 전용이 13 + 1 = 14장을 답함 → 울기 1 과 안 맞음(11 이어야 함).
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, handonlyTiles: hand13),
      );
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, tracked: trackedPon, trace: trace);

      expect(names.indexOf('handonly_bottom'), lessThan(names.indexOf('seat_bottom')), reason: '손패 전용 뒤에 다시 읽음');
      expect(reading.hand!.tiles, hasLength(13), reason: '자리 전체 판독의 답');
      expect(reading.hand!.melds, isEmpty, reason: '추적 울기를 쓰지 않는다');
      expect(reading.meldsTracked, isFalse);
      expect(trace.trackedMode[Side.bottom], 'fallback_seat');
      expect(reading.warnings.join(), contains('다시 읽었습니다'));
    });

    test('화료자 자리에 따로 놓인 앞면 패는 가운데 도라와 따로 넘긴다(어느 쪽을 쓸지는 merge 가 리치로)', () async {
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server([], {}, dora: [], loose: ['7m', '6s']),
      );
      final reading = await TableReader(client).readGrid(table(), grid);
      expect(reading.center!.doraIndicators, isEmpty);
      expect([for (final t in reading.center!.handSideIndicators) t.code], ['7m', '6s']);
    });

    test('서버가 여러 번 읽은 답이 엇갈렸으면 경고를 남긴다(만장일치면 없음)', () async {
      Future<List<String>> warnings(Map<String, Object> agreement) async {
        final client = RecognizerClient(
          baseUrl: 'https://x.test',
          apiKey: 'k',
          httpClient: server([], {}, agreement: agreement),
        );
        return (await TableReader(client).readGrid(table(), grid)).warnings;
      }

      expect(await warnings({'reads': 3, 'agree': 3, 'unanimous': true, 'alternatives': []}), isEmpty);
      final w = await warnings({
        'reads': 3,
        'agree': 2,
        'unanimous': false,
        'alternatives': ['1m 2m 2m'],
      });
      expect(w.single, contains('3번 읽어 2번만 같았습니다'));
      expect(w.single, contains('1m 2m 2m'));
    });

    test('나눠 읽기: 손패 칸은 /v2/seat, 모서리 칸은 /v2/corner 로 따로 보내 울기·따로 놓인 패를 합친다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, dora: [], loose: ['7m']),
      );
      final reading = await TableReader(client).readGrid(table(), grid, splitSeat: true);
      expect(names.toSet(), {'seat_bottom', 'corner_bottom', 'last_right', 'last_top', 'last_left', 'sticks', 'dora'});
      // 아래 손패 칸 500×200, 오른쪽 아래 모서리 칸 250×200.
      expect(images['seat_bottom']!.width, 500);
      expect(images['corner_bottom']!.width, 250);
      expect(reading.hand!.melds.single.tiles.map((t) => t.code), ['6z', '6z', '6z']);
      expect([for (final t in reading.center!.handSideIndicators) t.code], ['7m', '9s']);
    });
  });
}
