import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/engine/calculator.dart' show Tiles;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';

/// 격자 경로의 넓은 구역 판독(`/v2/seatwide`)을 자리 판독과 같은 순간에 미리 보내기(`readGrid(wideEarly:)`).
void main() {
  const grid = GridZones(x1: 250, x2: 750, y1: 200, y2: 800);
  const hand13 = ['5s', '6s', '6p', '7p', '8p', '2m', '3m', '4m', '7m', '8m', '9m', '6z', '6z']; // 143104, 떼어 둔 7s

  Uint8List table() {
    final im = img.Image(width: 1000, height: 1000);
    img.fill(im, color: img.ColorRgb8(30, 120, 60));
    return Uint8List.fromList(img.encodeJpg(im, quality: 95));
  }

  http.Response json(Object body) => http.Response(jsonEncode(body), 200);

  /// 가짜 서버. [separate] 가 있으면 자리 판독이 14장 화료형(넓은 판독 불필요), 없으면 13장 노텐(필요).
  /// [wideStatus] 가 200 이 아니면 넓은 판독은 그 상태로 실패.
  (RecognizerClient, List<String>) server({String? separate, int wideStatus = 200, bool riichi = false, String grouped = ''}) {
    final names = <String>[];
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        final body = latin1.decode(r.bodyBytes);
        names.addAll([for (final m in RegExp(r'filename="([^"]+)\.jpg"').allMatches(body)) m.group(1)!]);
        return switch (r.url.path) {
          '/v2/seat' => json({
              'face_up': true,
              'tiles': [for (final c in hand13) {'tile': c, 'conf': 0.9}],
              'separate_tile': separate == null ? null : {'tile': separate, 'conf': 0.9},
              'melds': [],
              'loose': [],
            }),
          '/v2/seatwide' => wideStatus != 200
              ? http.Response('boom', wideStatus)
              : json({
                  'method': 'frame',
                  'row': [for (final c in hand13) {'tile': c, 'conf': 0.9}],
                  'singles': [
                    {'tile': '7s', 'conf': 0.9, 'lone': true},
                    for (final c in grouped.split(' ')) if (c.isNotEmpty) {'tile': c, 'conf': 0.9, 'lone': false, 'pair': true},
                  ],
                  'melds': [],
                  'agreement': {'reads': 3, 'agree': 3, 'unanimous': true},
                }),
          '/v2/last3' => json({'rivers': []}),
          '/v2/sticks' => json({'riichi_sticks': riichi ? {'bottom': true} : {}}),
          '/v2/dora' => json({'indicators': []}),
          _ => http.Response('nope', 404),
        };
      }),
    );
    return (client, names);
  }

  test('미리 보내기(기본)는 넓은 판독이 강 끝보다 먼저 나가고, 필요한 장면에서는 그 답을 쓴다', () async {
    final (client, names) = server();
    final trace = TableReadTrace();
    final reading = await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, trace: trace);
    expect(names.indexOf('seatwide_bottom'), lessThan(names.indexOf('last_right')), reason: '자리 판독과 같은 순간에 보낸다');
    expect(names.where((n) => n == 'seatwide_bottom').length, 1, reason: '한 번만 보낸다');
    expect(trace.wideEarly, isTrue);
    expect(trace.wide, isNotNull);
    expect(trace.callMs, contains('seatwide_bottom'));
    expect(reading.hand!.winTile?.tile, Tiles.parse('7s'));
  });

  test('뒤늦게 보내기(wideEarly: false)는 넓은 판독이 강 끝 뒤에 나간다', () async {
    final (client, names) = server();
    final trace = TableReadTrace();
    await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, wideEarly: false, trace: trace);
    expect(names.indexOf('seatwide_bottom'), greaterThan(names.indexOf('last_right')));
    expect(trace.wideEarly, isFalse);
    expect(trace.wide, isNotNull);
  });

  test('미리 보냈는데 안 필요한 장면은 답을 버린다(기록에는 시간만)', () async {
    final (client, names) = server(separate: '7s');
    final trace = TableReadTrace();
    final reading = await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, wideEarly: true, trace: trace);
    expect(names, contains('seatwide_bottom'));
    expect(trace.wideEarly, isTrue);
    expect(trace.wide, isNull);
    expect(trace.callMs, contains('seatwide_bottom'), reason: '시간은 남긴다(버린 호출 비용)');
    expect(reading.hand!.winTile?.tile, Tiles.parse('7s'), reason: '자리 판독 답 그대로');
    expect(reading.warnings, isEmpty);
  });

  test('미리 보낸 넓은 판독이 실패해도 안 필요한 장면이면 경고가 없다', () async {
    final (client, _) = server(separate: '7s', wideStatus: 500);
    final reading = await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, wideEarly: true);
    expect(reading.warnings, isEmpty, reason: '경고가 있으면 자동 반영이 막힌다');
  });

  test('미리 보낸 넓은 판독이 실패했는데 필요한 장면이면 경고를 남긴다', () async {
    final (client, _) = server(wideStatus: 500);
    final trace = TableReadTrace();
    final reading = await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, wideEarly: true, trace: trace);
    expect(trace.wide, isNull);
    expect(reading.warnings.join(), contains('seatwide_bottom'));
  });

  test('리치 화료자의 손패 옆이 비면 미리 보낸 넓은 판독의 표시패 짝 2~4장을 표시패로 넘긴다', () async {
    final (client, _) = server(separate: '7s', riichi: true, grouped: '6p 3s');
    final trace = TableReadTrace();
    final reading = await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, trace: trace);
    expect(trace.wide, isNull, reason: '손패는 자리 판독 그대로');
    expect(trace.wideForDora, isTrue);
    expect([for (final t in reading.center!.handSideIndicators) t.code], ['6p', '3s']);
    expect(reading.warnings, isEmpty);
  });

  test('리치를 모르면 기다리지 않는다(가짜 서버는 즉시 답해 이미 와 있으므로 짝은 넘긴다), 짝이 1장이거나 5장 넘어도 안 쓴다', () async {
    final (c1, _) = server(separate: '7s', grouped: '6p 3s');
    final t1 = TableReadTrace();
    final r1 = await TableReader(c1).readGrid(table(), grid, winnerSide: Side.bottom, trace: t1);
    expect(t1.wideForDora, isFalse, reason: '기다리지 않음');
    expect([for (final t in r1.center!.handSideIndicators) t.code], ['6p', '3s'], reason: '와 있는 답은 쓴다');
    final (c2, _) = server(separate: '7s', riichi: true, grouped: '6p');
    expect((await TableReader(c2).readGrid(table(), grid, winnerSide: Side.bottom)).center!.handSideIndicators, isEmpty);
    final (c3, _) = server(separate: '7s', riichi: true, grouped: '6p 3s 1m 2m 3m');
    expect((await TableReader(c3).readGrid(table(), grid, winnerSide: Side.bottom)).center!.handSideIndicators, isEmpty);
  });

  test('useWide 가 꺼져 있으면 미리 보내지 않는다', () async {
    final (client, names) = server();
    final trace = TableReadTrace();
    await TableReader(client).readGrid(table(), grid, winnerSide: Side.bottom, useWide: false, wideEarly: true, trace: trace);
    expect(names, isNot(contains('seatwide_bottom')));
    expect(trace.wideEarly, isFalse);
  });
}
