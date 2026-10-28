import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/fixed_layout.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';

/// 1024×768 합성 테이블: 흰 테두리 안 초록 펠트, 아래 손패는 뒷면([back], 기본 연보라), 위 손패는 앞면(흰 면 + 무늬 10장),
/// 펠트 위 왼쪽 위에 흰 패 두 장(도라 표시패). [shift] 만큼 펠트를 옮기면 카메라가 움직인 것.
Uint8List table({int shift = 0, bool topFaceUp = true, img.Color? back}) {
  final im = img.Image(width: 1024, height: 768);
  final b = back ?? img.ColorRgb8(180, 170, 230);
  img.fill(im, color: img.ColorRgb8(235, 235, 235));
  img.fillRect(im, x1: 40 + shift, y1: 40, x2: 984 + shift, y2: 728, color: img.ColorRgb8(30, 120, 60));
  img.fillRect(im, x1: 200, y1: 650, x2: 700, y2: 720, color: b);
  if (topFaceUp) {
    for (var i = 0; i < 10; i++) {
      final x = 352 + i * 30;
      img.fillRect(im, x1: x, y1: 60, x2: x + 26, y2: 110, color: img.ColorRgb8(240, 240, 240));
      img.fillRect(im, x1: x + 9, y1: 68, x2: x + 17, y2: 78, color: img.ColorRgb8(20, 20, 20));
      img.fillRect(im, x1: x + 9, y1: 90, x2: x + 17, y2: 100, color: img.ColorRgb8(200, 30, 30));
    }
  } else {
    img.fillRect(im, x1: 350, y1: 60, x2: 650, y2: 110, color: b);
  }
  img.fillRect(im, x1: 205, y1: 230, x2: 246, y2: 261, color: img.ColorRgb8(240, 240, 240));
  return Uint8List.fromList(img.encodeJpg(im, quality: 95));
}

final layout = TableLayout(
  hands: const [
    HandZone(Side.bottom, NormBox(846, 195, 937, 684), faceUp: false),
    HandZone(Side.top, NormBox(78, 342, 143, 635), faceUp: true),
  ],
  rivers: const [
    SidedZone(Side.top, NormBox(350, 400, 420, 600)),
    SidedZone(Side.bottom, NormBox(580, 400, 650, 600)),
    SidedZone(Side.left, NormBox(420, 300, 580, 380)),
    SidedZone(Side.right, NormBox(420, 620, 580, 700)),
  ],
  center: const NormBox(350, 300, 650, 700),
);

http.Response _json(Object body) => http.Response(jsonEncode(body), 200);

img.Image _jpegIn(http.Request r) {
  final b = r.bodyBytes;
  for (var i = 0; i < b.length - 1; i++) {
    if (b[i] == 0xFF && b[i + 1] == 0xD8) return img.decodeJpg(b.sublist(i))!;
  }
  throw StateError('no jpeg');
}

Map<String, dynamic> handBody(int n) => {
      'tiles': [for (var i = 0; i < n; i++) {'tile': '1m', 'conf': 0.9}],
      'separate_tile': null,
      'melds': [],
    };

void main() {
  group('픽셀 판정', () {
    final fixed = calibrateFixed((table(), layout));

    test('같은 구도면 움직이지 않았고, 앞면 무늬가 있는 위 손패가 앞면, 펠트 위 흰 덩어리가 도라', () {
      final a = analyzeShot((table(), fixed));
      expect(a.iou, greaterThan(0.99));
      expect(a.moved, isFalse);
      expect(a.faceUp, [Side.top]);
      expect(a.handColors[Side.bottom]!.$1, greaterThan(0.3));
      final d = a.doraBox!;
      expect((d.ymin - 300).abs() < 10 && (d.xmin - 200).abs() < 10, isTrue, reason: '$d');
      expect((d.ymax - 340).abs() < 10 && (d.xmax - 240).abs() < 10, isTrue, reason: '$d');
    });

    test('펠트가 옮겨지면(카메라 움직임) moved', () {
      final a = analyzeShot((table(shift: 120), fixed));
      expect(a.moved, isTrue);
    });

    test('눕힌 손패가 없으면 앞면 자리도 없다', () {
      expect(analyzeShot((table(topFaceUp: false), fixed)).faceUp, isEmpty);
    });

    test('뒷면 색과 상관없다(파랑 뒷면)', () {
      final blue = img.ColorRgb8(40, 90, 200);
      expect(analyzeShot((table(back: blue), fixed)).faceUp, [Side.top]);
      expect(analyzeShot((table(back: blue, topFaceUp: false), fixed)).faceUp, isEmpty);
    });

    test('layoutFor 는 앞면·도라만 바꾸고 울기 상자는 비운다', () {
      final l = fixed.layoutFor(analyzeShot((table(), fixed)));
      expect(l.faceUpSides, [Side.top]);
      expect(l.deadWall, isNotNull);
      expect(l.melds, isEmpty);
      expect(l.rivers.length, 4);
    });
  });

  test('meldCorner: 손패 끝에서 그 사람 오른쪽(울기 놓는 쪽)과 가장자리 쪽 모서리', () {
    // 2026-10-24 위 자리: 손패 [105,464,212,642], 발 퐁 [37,318,83,380] 이 들어가야 한다.
    final top = meldCorner(const NormBox(105, 464, 212, 642), Side.top);
    expect(top, const NormBox(30, 304, 212, 464));
    expect(meldCorner(const NormBox(800, 200, 900, 500), Side.bottom), const NormBox(800, 500, 970, 770));
    expect(meldCorner(const NormBox(300, 800, 700, 900), Side.right), const NormBox(0, 800, 300, 970));
    expect(meldCorner(const NormBox(300, 100, 700, 200), Side.left), const NormBox(700, 30, 1000, 200));
  });

  group('TableReader 고정 구역', () {
    final fixed = calibrateFixed((table(), layout));

    RecognizerClient client(List<String> paths, Map<String, http.Request> seen, int handTiles) => RecognizerClient(
          baseUrl: 'https://x.test',
          apiKey: 'k',
          httpClient: MockClient((r) async {
            paths.add(r.url.path);
            seen[r.url.path] = r;
            return switch (r.url.path) {
              '/v1/locate' => _json({
                  ...layout.toJson(),
                  'hands': [
                    {'side': 'top', 'box': [78, 342, 143, 635], 'face_up': true},
                  ],
                }),
              '/v2/hand' => _json(handBody(paths.contains('/v1/locate') ? 13 : handTiles)),
              '/v2/meld' => _json({'tiles': ['6z', '6z', '6z'], 'sideways': [1], 'face_down': []}),
              '/v2/river' => _json({'tiles': [], 'riichi_stick': false}),
              '/v2/center' => _json({'indicators': [], 'riichi_sticks': {}}),
              _ => http.Response('nope', 404),
            };
          }),
        );

    test('locate 없이 고정 구역으로 읽고, 울기 모서리는 따로 잘라 /v2/meld 로 읽는다', () async {
      final paths = <String>[];
      final seen = <String, http.Request>{};
      final trace = TableReadTrace();
      final r = await TableReader(client(paths, seen, 10)).read(table(), fixed: fixed, trace: trace);
      expect(paths, isNot(contains('/v1/locate')));
      expect(trace.layoutMode, 'fixed');
      expect(trace.timingsMs.keys, containsAll(['analyze', 'crop', 'read']));
      expect(r.winnerSide, Side.top);
      // 손패 10장 + 모서리 퐁 = 13장
      expect(r.hand!.tiles.length, 10);
      expect(r.hand!.melds.single.tiles.map((t) => t.code), ['6z', '6z', '6z']);
      // 손패 크롭은 원래 크기(위 손패 [78,342,143,635] → 1024px 에서 약 300px + 4% 패딩), 모서리는 손패 왼쪽.
      expect(_jpegIn(seen['/v2/hand']!).width, lessThan(330));
      expect(trace.meldCrops.length, 1);
      // 도라 덩어리를 왕패로 따로 읽었다(가운데 1 + 왕패 1).
      expect(paths.where((p) => p == '/v2/center').length, 2);
    });

    test('고정 구역으로 읽은 장수가 안 맞으면 locate 로 다시 읽는다', () async {
      final paths = <String>[];
      final trace = TableReadTrace();
      final r = await TableReader(client(paths, {}, 8)).read(table(), fixed: fixed, trace: trace);
      expect(paths.where((p) => p == '/v1/locate').length, 1);
      expect(trace.layoutMode, 'fixed→locate');
      expect(r.hand!.tiles.length, 13);
    });

    test('카메라가 움직였으면 고정 구역을 쓰지 않고 locate', () async {
      final paths = <String>[];
      final trace = TableReadTrace();
      await TableReader(client(paths, {}, 13)).read(table(shift: 120), fixed: fixed, trace: trace);
      expect(paths.first, '/v1/locate');
      expect(trace.analysis!.moved, isTrue);
    });
  });
}
