import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';

/// 400×200 원본. 아래 절반이 손패, 위 절반 가운데가 중앙이라고 치자.
final Uint8List original = Uint8List.fromList(img.encodeJpg(img.Image(width: 400, height: 200)));

Map<String, dynamic> locateBody({List<String> faceUp = const ['bottom'], bool center = true}) => {
      'hands': [
        {'side': 'bottom', 'box': [500, 0, 1000, 1000], 'face_up': faceUp.contains('bottom'), 'conf': 0.9},
        {'side': 'top', 'box': [0, 0, 250, 1000], 'face_up': faceUp.contains('top'), 'conf': 0.9},
      ],
      'rivers': [
        {'side': 'bottom', 'box': [300, 300, 450, 700], 'conf': 0.9},
      ],
      'dead_wall': null,
      'center': center ? {'box': [0, 250, 500, 750]} : null,
      'notes': 'n',
    };

const handBody = {
  'tiles': [
    {'tile': '1m', 'conf': 0.9},
  ],
  'separate_tile': {'tile': '2m', 'conf': 0.8},
  'melds': [],
  'notes': '',
  'usage': {'input_tokens': 10, 'output_tokens': 5},
};

/// 아래 자리 강: 마지막 패가 가로 → 리치.
const riverBody = {
  'tiles': [
    {'tile': '9m', 'conf': 0.9, 'sideways': false},
    {'tile': '2m', 'conf': 0.9, 'sideways': true},
  ],
  'riichi_stick': false,
};

const centerBody = {
  'indicators': [
    {'tile': '3p', 'conf': 0.9},
  ],
  'riichi_sticks': {'bottom': false},
};

http.Response _json(Object body, {int status = 200}) => http.Response(jsonEncode(body), status);

/// multipart 본문에서 JPEG 를 꺼내 디코딩한다.
img.Image _jpegIn(http.Request r) {
  final b = r.bodyBytes;
  for (var i = 0; i < b.length - 1; i++) {
    if (b[i] == 0xFF && b[i + 1] == 0xD8) return img.decodeJpg(b.sublist(i))!;
  }
  throw StateError('no jpeg');
}

void main() {
  test('locate → 손패·중앙 크롭 → 병렬 읽기. 크롭 크기와 호출 순서', () async {
    final seen = <String, http.Request>{};
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        seen[r.url.path] = r;
        return switch (r.url.path) {
          '/v1/locate' => _json(locateBody()),
          '/v2/hand' => _json(handBody),
          '/v2/river' => _json(riverBody),
          '/v2/center' => _json(centerBody),
          _ => http.Response('nope', 404),
        };
      }),
    );
    final stages = <ReadStage>[];
    final reading = await TableReader(client).read(original, onStage: stages.add);

    expect(stages, ReadStage.values);
    expect(seen.keys, containsAll(['/v1/locate', '/v2/hand', '/v2/river', '/v2/center']));
    expect(reading.winnerSide, Side.bottom);
    expect(reading.hand!.tiles.single.code, '1m');
    expect(reading.hand!.winTile!.code, '2m');
    // 리치·강 끝 패는 코드가 정한다: 아래 강의 가로 패 → 리치, 마지막 패 2m.
    expect(reading.center!.riichiAt(Side.bottom), isTrue);
    expect(reading.center!.lastDiscardAt(Side.bottom)!.code, '2m');
    expect(reading.center!.doraIndicators.single.code, '3p');
    expect(reading.warnings, isEmpty);

    // locate 입력은 원본 그대로(400px 는 1024 이하라 줄지 않음)
    expect(_jpegIn(seen['/v1/locate']!).width, 400);
    // 손패 크롭: 아래 절반(400×100)에 4% 패딩(20/1000 → 4px). 아래쪽은 이미지 끝이라 위로만 늘어 104
    final hand = _jpegIn(seen['/v2/hand']!);
    expect(hand.width, 400);
    expect(hand.height, 104);
    // 중앙 크롭: 200×100 에 5% 패딩(25/1000). 위쪽은 이미지 끝이라 아래로만 늘어 220×105
    final center = _jpegIn(seen['/v2/center']!);
    expect((center.width, center.height), (220, 105));
  });

  test('눕힌 자리가 둘이면 pickWinner 로 묻고, 그 자리를 회전해 보낸다', () async {
    String? handFile;
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        if (r.url.path == '/v2/hand') handFile = latin1.decode(r.bodyBytes);
        return switch (r.url.path) {
          '/v1/locate' => _json(locateBody(faceUp: ['bottom', 'top'])),
          '/v2/hand' => _json(handBody),
          '/v2/river' => _json(riverBody),
          '/v2/center' => _json(centerBody),
          _ => http.Response('nope', 404),
        };
      }),
    );
    List<Side>? asked;
    final reading = await TableReader(client).read(
      original,
      pickWinner: (c) async {
        asked = c;
        return Side.top;
      },
    );
    expect(asked, [Side.bottom, Side.top]);
    expect(reading.winnerSide, Side.top);
    expect(handFile, contains('filename="hand_top.jpg"'));
  });

  test('눕힌 자리가 없으면 TableReadException (layout 포함)', () async {
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async => _json(locateBody(faceUp: []))),
    );
    await expectLater(
      TableReader(client).read(original),
      throwsA(isA<TableReadException>()
          .having((e) => e.message, 'message', contains('눕힌 손패가 없습니다'))
          .having((e) => e.layout?.notes, 'layout', 'n')),
    );
  });

  test('pickWinner 가 취소하면 예외', () async {
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async => _json(locateBody(faceUp: ['bottom', 'top']))),
    );
    await expectLater(
      TableReader(client).read(original, pickWinner: (_) async => null),
      throwsA(isA<TableReadException>()),
    );
  });

  test('가운데·강 읽기가 실패해도 손패는 돌려주고 warnings 에 남긴다', () async {
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async => switch (r.url.path) {
            '/v1/locate' => _json(locateBody()),
            '/v2/hand' => _json(handBody),
            _ => http.Response('boom', 502),
          }),
    );
    final reading = await TableReader(client).read(original);
    expect(reading.hand, isNotNull);
    expect(reading.center!.doraIndicators, isEmpty);
    expect(reading.warnings, hasLength(2)); // river_bottom, center
    expect(reading.warnings.join(), contains('center'));
  });

  test('center 가 없으면 /v1/table 을 부르지 않고 warnings', () async {
    final paths = <String>[];
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        paths.add(r.url.path);
        return switch (r.url.path) {
          '/v1/locate' => _json({...locateBody(center: false), 'rivers': []}),
          '/v2/hand' => _json(handBody),
          _ => http.Response('nope', 404),
        };
      }),
    );
    final reading = await TableReader(client).read(original, winnerSide: Side.bottom);
    expect(paths, ['/v1/locate', '/v2/hand']);
    expect(reading.center!.doraIndicators, isEmpty);
    expect(reading.warnings.single, contains('중앙 구역'));
  });

  test('trace 에 축소본·크롭·응답·단계별 시간이 남는다', () async {
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async => switch (r.url.path) {
            '/v1/locate' => _json(locateBody()),
            '/v2/hand' => _json(handBody),
            '/v2/river' => _json(riverBody),
          '/v2/center' => _json(centerBody),
            _ => http.Response('nope', 404),
          }),
    );
    final trace = TableReadTrace();
    final reading = await TableReader(client).read(original, trace: trace);
    expect(trace.small, isNotNull);
    expect(img.decodeJpg(trace.handCrop!)!.width, 400);
    expect(img.decodeJpg(trace.centerCrop!)!.width, 220);
    expect(trace.layout!.faceUpSides, [Side.bottom]);
    expect(trace.hand!.tiles.single.code, reading.hand!.tiles.single.code);
    expect(trace.center!.riichiAt(Side.bottom), isTrue);
    expect(trace.winnerSide, Side.bottom);
    expect(trace.riverCrops.keys, [Side.bottom]);
    final obs = trace.observation!.toJson();
    expect(obs['players']['bottom']['hand']['separate_tile'], '2m');
    expect(obs['players']['bottom']['river'].last, {'tile': '2m', 'sideways': true, 'conf': 0.9});
    expect(obs['dora_indicators'], ['3p']);
    expect(obs['usage']['hand'], {'input_tokens': 10, 'output_tokens': 5});
    expect(trace.timingsMs.keys, containsAll(['shrink', 'locate', 'crop', 'read']));
  });

  test('울기 상자가 있으면 묶음마다 /v2/meld 로 읽고, 손패 크롭에서 같은 묶음을 읽었으면 한 번만 센다', () async {
    final paths = <String>[];
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        paths.add(r.url.path);
        return switch (r.url.path) {
          '/v1/locate' => _json({
              ...locateBody(),
              'melds': [
                {'side': 'bottom', 'box': [900, 850, 1000, 1000], 'conf': 0.9},
                {'side': 'top', 'box': [0, 0, 100, 100], 'conf': 0.9}, // 화료자 아님: 안 읽음
              ],
            }),
          '/v2/hand' => _json({
              ...handBody,
              'melds': [
                {'tiles': ['6z', '6z', '6z'], 'sideways': [], 'face_down': [], 'conf': 0.9},
              ],
            }),
          '/v2/meld' => _json({'tiles': ['6z', '6z', '6z'], 'sideways': [1], 'face_down': [], 'conf': 0.9}),
          '/v2/river' => _json(riverBody),
          '/v2/center' => _json(centerBody),
          _ => http.Response('nope', 404),
        };
      }),
    );
    final trace = TableReadTrace();
    final reading = await TableReader(client).read(original, trace: trace);
    expect(paths.where((p) => p == '/v2/meld'), hasLength(1));
    expect(reading.hand!.melds.single.tiles.map((t) => t.code), ['6z', '6z', '6z']);
    expect(trace.meldCrops, hasLength(1));
    expect(trace.observation!.toJson()['players']['bottom']['melds'].single['sideways'], [1]);
  });

  test('화료자 왼쪽의 울기 상자는 읽지 않고, 울기 모양이 아닌 묶음은 빼서 도라 표시패 후보로 쓴다', () async {
    final meldFiles = <String>[];
    final client = RecognizerClient(
      baseUrl: 'https://x.test',
      apiKey: 'k',
      httpClient: MockClient((r) async {
        final body = String.fromCharCodes(r.bodyBytes.take(400));
        if (r.url.path == '/v2/meld') meldFiles.add(RegExp(r'filename="([^"]+)"').firstMatch(body)!.group(1)!);
        return switch (r.url.path) {
          '/v1/locate' => _json({
              ...locateBody(),
              'hands': [
                {'side': 'bottom', 'box': [700, 300, 900, 700], 'face_up': true, 'conf': 0.9},
              ],
              'melds': [
                {'side': 'bottom', 'box': [750, 0, 850, 100], 'conf': 0.9}, // 아래 자리 왼쪽: 다른 사람 것
                {'side': 'bottom', 'box': [750, 800, 850, 900], 'conf': 0.9}, // 오른쪽: 읽는다
              ],
            }),
          '/v2/hand' => _json(handBody),
          '/v2/meld' => _json({'tiles': ['4p', '4p', '7m'], 'sideways': [], 'face_down': [], 'conf': 0.9}),
          '/v2/river' => _json(riverBody),
          '/v2/center' => _json({'indicators': [], 'riichi_sticks': {}}),
          _ => http.Response('nope', 404),
        };
      }),
    );
    final reading = await TableReader(client).read(original);
    // 오른쪽 상자는 모서리([700,700,900,1000]) 안 → 모서리 크롭 하나로 읽는다. 왼쪽 상자는 안 읽는다.
    expect(meldFiles, ['meld_0.jpg']);
    expect(reading.hand!.melds, isEmpty);
    expect(reading.center!.doraIndicators.map((t) => t.code), ['4p', '4p', '7m']);
    expect(reading.warnings.single, contains('4p 4p 7m'));
  });
}
