import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// `readGrid(trackedDora:)` 가 바깥 TableReading 까지 전달되는지(2026-11-03: 겉 TableReading 이 빠뜨려 측정에서 효과가 0 이었다).
void main() {
  const grid = GridZones(x1: 250, x2: 750, y1: 200, y2: 800);

  Uint8List table() {
    final im = img.Image(width: 1000, height: 1000);
    img.fill(im, color: img.ColorRgb8(30, 120, 60));
    // 아래 자리 손패 줄만 앞면(흰 면) 띠, 나머지는 뒷면.
    img.fillRect(im, x1: 350, y1: 870, x2: 650, y2: 930, color: img.ColorRgb8(245, 245, 240));
    final back = img.ColorRgb8(180, 170, 230);
    img.fillRect(im, x1: 350, y1: 70, x2: 650, y2: 130, color: back);
    img.fillRect(im, x1: 70, y1: 350, x2: 130, y2: 650, color: back);
    img.fillRect(im, x1: 870, y1: 350, x2: 930, y2: 650, color: back);
    return Uint8List.fromList(img.encodeJpg(im, quality: 95));
  }

  http.Response json(Object body) => http.Response(jsonEncode(body), 200);

  test('trackedDora 가 판독 결과(바깥 TableReading)에 실린다', () async {
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async => switch (r.url.path) {
            '/v2/localseat' || '/v2/seat' || '/v2/handonly' => json({
                'face_up': true,
                'tiles': [for (final c in ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2p', '3p']) {'tile': c, 'conf': 0.9}],
                'separate_tile': {'tile': '4p', 'conf': 0.9},
                'melds': [],
                'loose': [],
              }),
            '/v2/locallast3' || '/v2/last3' => json({'rivers': []}),
            '/v2/sticks' => json({'riichi_sticks': {}}),
            '/v2/localdora' || '/v2/dora' => json({'indicators': [], 'box': null, 'pairs': []}),
            _ => http.Response('nope', 404),
          }),
    );
    final r = await TableReader(client).readGrid(table(), grid, localOnly: true, winnerSide: Side.bottom, trackedDora: ReadTile.fromCode('7m', 0.9));
    expect(r.trackedDora?.code, '7m');
    expect(r.winnerSide, Side.bottom);
  });
}
