import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 동시 론(더블 론)에서 탁자 위 표시패 짝을 리치한 화료자끼리 같이 쓰는지.
/// 2026-11-14 매장 r05: 짝(8통·동)이 첫 화료자 손패 옆에 있었고, 더블 론 기록에는 뒷도라 표시패가 빠졌다 —
/// 화료자를 읽고 나서야 아는 흐름이라 짝 찾기([localPairIndicators])가 아예 안 불렸다.
void main() {
  const grid = GridZones(x1: 250, x2: 750, y1: 200, y2: 800);
  // 왼쪽 자리 띠 안(아래 자리에서 보면 다른 자리)
  const at = (150, 300);

  Uint8List table() {
    final im = img.Image(width: 1000, height: 1000);
    img.fill(im, color: img.ColorRgb8(30, 120, 60));
    final face = img.ColorRgb8(245, 245, 240), back = img.ColorRgb8(180, 170, 230);
    img.fillRect(im, x1: 350, y1: 870, x2: 650, y2: 930, color: face); // 아래: 앞면
    img.fillRect(im, x1: 70, y1: 350, x2: 130, y2: 650, color: face); // 왼쪽: 앞면
    img.fillRect(im, x1: 350, y1: 70, x2: 650, y2: 130, color: back);
    img.fillRect(im, x1: 870, y1: 350, x2: 930, y2: 650, color: back);
    return Uint8List.fromList(img.encodeJpg(im, quality: 95));
  }

  http.Response json(Object body) => http.Response(jsonEncode(body), 200);
  const hand = ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2p', '3p'];

  RecognizerClient client() => RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: MockClient((r) async {
          switch (r.url.path) {
            case '/v2/localseat':
              final name = RegExp(r'filename="([^"]+)\.jpg"').firstMatch(latin1.decode(r.bodyBytes))!.group(1)!;
              final open = name == 'seat_bottom' || name == 'seat_left';
              return json({
                'face_up': open,
                'tiles': [if (open) for (final c in hand) {'tile': c, 'conf': 0.9}],
                'separate_tile': null,
                'melds': [],
                'loose': [],
              });
            case '/v2/locallast3':
              return json({'rivers': []});
            case '/v2/localdora':
              return json({
                'indicators': [],
                'box': null,
                'size': [1000, 1000],
                'pairs': [
                  [
                    {'tile': '8p', 'conf': 0.9, 'box': [at.$1 - 12, at.$2 - 16, 24, 32]},
                    {'tile': '1z', 'conf': 0.9, 'box': [at.$1 + 14, at.$2 - 16, 24, 32]},
                  ],
                ],
              });
            default:
              return http.Response('nope', 404);
          }
        }),
      );

  List<String> side(TableReading r) => [for (final t in r.center!.handSideIndicators) t.code];

  test('짝이 왼쪽 자리 띠에 있다(아래 화료자 혼자면 다른 자리라 안 씀)', () {
    expect(pairZoneOf(grid, Side.left, at), PairZone.winnerSeat);
    expect(pairZoneOf(grid, Side.bottom, at), PairZone.otherSeat);
  });

  test('더블 론: 둘 다 리치면 같은 짝을 둘 다 받는다', () async {
    final r = await TableReader(client()).readGrid(table(), grid,
        localOnly: true, trackedRiichi: {Side.bottom, Side.left}, acceptAll: (_) => true);
    expect({r.winnerSide, for (final o in r.others) o.winnerSide}, {Side.bottom, Side.left});
    expect(side(r), ['8p', '1z']);
    expect(side(r.others.single), ['8p', '1z']);
  });

  test('더블 론: 리치가 아닌 화료자에게는 주지 않는다(뒷도라는 리치한 사람만)', () async {
    final r = await TableReader(client())
        .readGrid(table(), grid, localOnly: true, trackedRiichi: {Side.left}, acceptAll: (_) => true);
    final by = {r.winnerSide: r, for (final o in r.others) o.winnerSide: o};
    expect(side(by[Side.left]!), ['8p', '1z']);
    expect(side(by[Side.bottom]!), isEmpty);
  });
}
