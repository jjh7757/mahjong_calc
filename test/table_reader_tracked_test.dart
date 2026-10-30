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

/// 격자 경로 화료 판독에서 "추적한 자리" 처리. 가짜 서버가 자리 이름(파일 이름)으로 답을 고른다.
void main() {
  const grid = GridZones(x1: 250, x2: 750, y1: 200, y2: 800);

  // 합성 탁자: 네 자리 손패 자리에 뒷면(보라) 띠. 픽셀로는 화료자를 정하지 못한다.
  Uint8List table() {
    final im = img.Image(width: 1000, height: 1000);
    img.fill(im, color: img.ColorRgb8(30, 120, 60));
    final back = img.ColorRgb8(180, 170, 230);
    img.fillRect(im, x1: 350, y1: 870, x2: 650, y2: 930, color: back);
    img.fillRect(im, x1: 350, y1: 70, x2: 650, y2: 130, color: back);
    img.fillRect(im, x1: 70, y1: 350, x2: 130, y2: 650, color: back);
    img.fillRect(im, x1: 870, y1: 350, x2: 930, y2: 650, color: back);
    return Uint8List.fromList(img.encodeJpg(im, quality: 95));
  }

  http.Response json(Object body) => http.Response(jsonEncode(body), 200);

  test('화료자를 픽셀로 못 정해도 뒷면인 추적 자리는 손패 전용 답을 그대로 쓰고 다시 읽지 않는다(경고 없음)', () async {
    final names = <String>[];
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        final m = RegExp(r'filename="([^"]+)\.jpg"').firstMatch(latin1.decode(r.bodyBytes));
        final name = m?.group(1) ?? '';
        names.add(name);
        final side = name.contains('_') ? name.substring(name.indexOf('_') + 1) : '';
        final up = side == 'top';
        return switch (r.url.path) {
          '/v2/handonly' || '/v2/seat' => json({
              'face_up': up,
              'tiles': up ? [for (final c in ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '1p', '2p', '3p']) {'tile': c, 'conf': 0.9}] : [],
              'separate_tile': null,
              'melds': [],
              'loose': [],
            }),
          '/v2/last3' => json({'rivers': []}),
          '/v2/sticks' => json({'riichi_sticks': {}}),
          '/v2/dora' => json({'indicators': []}),
          _ => http.Response('nope', 404),
        };
      }),
    );
    final tracked = {
      Side.right: [ObservedMeld([for (var i = 0; i < 3; i++) ReadTile.fromCode('6z', 1)!], sideways: const [1])],
    };
    final trace = TableReadTrace();
    final reading = await TableReader(client).readGrid(table(), grid, tracked: tracked, trace: trace);
    expect(reading.winnerSide, Side.top);
    expect(names, contains('handonly_right'));
    expect(names, isNot(contains('seat_right')), reason: '뒷면 자리를 자리 전체로 다시 읽지 않는다');
    expect(trace.trackedMode[Side.right], 'handonly');
    expect(reading.warnings, isEmpty, reason: '경고가 있으면 자동 반영이 막힌다');
  });
}
