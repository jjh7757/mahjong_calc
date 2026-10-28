import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mahjong_calc/engine/calculator.dart' show Tiles;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/table_layout.dart';

final Uint8List _bytes = Uint8List.fromList(List<int>.generate(64, (i) => i));

RecognizerClient _client(Future<http.Response> Function(http.Request) handler,
        {Duration timeout = const Duration(seconds: 5)}) =>
    RecognizerClient(
      baseUrl: 'https://example.test',
      apiKey: 'k123',
      timeout: timeout,
      httpClient: MockClient(handler),
    );

http.Response _json(Map<String, dynamic> body, {int status = 200}) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  group('RecognizerClient', () {
    test('recognizeBytes: multipart·키 헤더를 보내고 tiles·melds·win_tile 을 파싱한다', () async {
      http.Request? seen;
      final c = _client((req) async {
        seen = req;
        return _json({
          'tiles': [
            {'tile': '3m', 'conf': 0.95},
            {'tile': '0m', 'conf': 0.9},
          ],
          'count': 2,
          'melds': [
            {'type': 'pon', 'tiles': ['7z', '7z', '7z'], 'conf': 0.8},
          ],
          'win_tile': {'tile': '4m', 'conf': 0.6},
          'notes': 'ok',
          'model': 'gemini-3.8-flash',
          'latency_ms': 5000,
        });
      });
      final r = await c.recognizeBytes(_bytes, filename: 'hand_bottom.jpg');

      expect(seen!.method, 'POST');
      expect(seen!.url.toString(), 'https://example.test/v1/recognize');
      expect(seen!.headers['X-Api-Key'], 'k123');
      expect(seen!.headers['content-type'], startsWith('multipart/form-data'));
      final body = latin1.decode(seen!.bodyBytes);
      expect(body, contains('name="image"'));
      expect(body, contains('filename="hand_bottom.jpg"'));

      expect(r.tiles.map((t) => t.code), ['3m', '0m']);
      expect(r.tiles[1].confidence, 0.9);
      expect(r.notes, 'ok');
      expect(r.model, 'gemini-3.8-flash');
      expect(r.latencyMs, 5000);
      expect(r.reading.tiles[1].red, isTrue);
      expect(r.reading.melds.single.tiles.first.tile, Tiles.red);
      expect(r.reading.winTile!.code, '4m');
      c.close();
    });

    test('옛 응답(melds·win_tile 없음)도 읽는다', () async {
      final c = _client((_) async => _json({
            'tiles': [
              {'tile': '1z', 'conf': 0.9}
            ],
            'count': 1,
            'notes': '',
            'model': 'm',
            'latency_ms': 1,
          }));
      final r = await c.recognizeBytes(_bytes);
      expect(r.tiles.single.code, '1z');
      expect(r.reading.melds, isEmpty);
      expect(r.reading.winTile, isNull);
    });

    test('locate → TableLayout', () async {
      http.Request? seen;
      final c = _client((req) async {
        seen = req;
        return _json({
          'hands': [
            {'side': 'bottom', 'box': [855, 185, 995, 870], 'face_up': true, 'conf': 0.98},
          ],
          'rivers': [
            {'side': 'bottom', 'box': [500, 415, 640, 580], 'conf': 0.9},
          ],
          'dead_wall': {'box': [100, 50, 200, 300], 'conf': 0.7},
          'center': {'box': [200, 200, 800, 800]},
          'face_up_sides': ['bottom'],
          'notes': '',
          'model': 'm',
          'latency_ms': 6000,
        });
      });
      final l = await c.locate(_bytes);
      expect(seen!.url.path, '/v1/locate');
      expect(l.singleFaceUp, Side.bottom);
      expect(l.center, const NormBox(200, 200, 800, 800));
      expect(l.deadWall!.conf, 0.7);
      expect(l.latencyMs, 6000);
    });

    test('readTable → CenterReading', () async {
      http.Request? seen;
      final c = _client((req) async {
        seen = req;
        return _json({
          'dora_indicators': [
            {'tile': '3p', 'conf': 0.9}
          ],
          'riichi': {'bottom': true, 'right': false, 'top': false, 'left': false},
          'riichi_conf': {'bottom': 0.9, 'right': 0.5, 'top': 0.5, 'left': 0.5},
          'last_discards': {'bottom': '7s', 'right': null, 'top': null, 'left': '1z'},
          'last_discards_conf': {'bottom': 0.8, 'right': 0, 'top': 0, 'left': 0.7},
          'notes': '',
          'model': 'm',
          'latency_ms': 4000,
        });
      });
      final t = await c.readTable(_bytes);
      expect(seen!.url.path, '/v1/table');
      expect(t.doraIndicators.single.tile, Tiles.parse('3p'));
      expect(t.riichiAt(Side.bottom), isTrue);
      expect(t.lastDiscardAt(Side.left)!.code, '1z');
      expect(t.lastDiscardAt(Side.top), isNull);
    });

    test('HTTP 상태 → 메시지', () async {
      const cases = {
        400: '사진 파일을 읽을 수 없습니다.',
        401: 'API 키가 맞지 않습니다.',
        413: '사진이 너무 큽니다(4MB 초과).',
        429: '요청이 너무 잦습니다. 잠시 후 다시 시도하세요.',
        502: '인식 모델 호출이 실패했습니다. 다시 시도하세요.',
        503: '서버에 인식 설정이 없습니다.',
        500: '인식 실패 (HTTP 500)',
      };
      for (final e in cases.entries) {
        final c = _client((_) async => http.Response('{"detail":"x"}', e.key));
        await expectLater(
          c.locate(_bytes),
          throwsA(isA<RecognizerException>().having((x) => x.message, 'message', e.value)),
        );
      }
    });

    test('JSON 이 아니면 RecognizerException', () async {
      final c = _client((_) async => http.Response('<html>', 200));
      await expectLater(c.readTable(_bytes), throwsA(isA<RecognizerException>()));
    });

    test('응답이 늦으면 타임아웃 메시지', () async {
      final c = _client(
        (_) async {
          await Future<void>.delayed(const Duration(milliseconds: 200));
          return _json({'tiles': []});
        },
        timeout: const Duration(milliseconds: 20),
      );
      await expectLater(
        c.recognizeBytes(_bytes),
        throwsA(isA<RecognizerException>()
            .having((x) => x.message, 'message', contains('응답이 없습니다'))),
      );
    });
  });
}
