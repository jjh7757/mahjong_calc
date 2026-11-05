import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/fixed_layout.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/shot_image.dart';
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

/// 자른 구역을 세는 [ShotImage].
class _CountingShot implements ShotImage {
  final ShotImage inner;
  final List<CropSpec> specs;
  _CountingShot(this.inner, this.specs);
  @override
  Future<Uint8List> shrink() => inner.shrink();
  @override
  Future<List<Uint8List>> crop(List<CropSpec> s) {
    specs.addAll(s);
    return inner.crop(s);
  }

  @override
  Future<FeltQuad?> rectify() => inner.rectify();
  @override
  Future<void> close() => inner.close();
}

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

    test('손패 판독 크롭은 가운데 쪽 변만 넓힌다(앞으로 내민 손패가 선에 안 잘리게)', () {
      expect(grid.seatForRead(Side.bottom), const NormBox(760, 250, 1000, 1000));
      expect(grid.seatForRead(Side.right), const NormBox(0, 710, 800, 1000));
      expect(grid.seatForRead(Side.top), const NormBox(0, 0, 240, 750));
      expect(grid.seatForRead(Side.left), const NormBox(200, 0, 1000, 290));
      expect(grid.handCellForRead(Side.bottom), const NormBox(760, 250, 1000, 750));
      expect(grid.handCellForRead(Side.right), const NormBox(200, 710, 800, 1000));
      expect(grid.handCellForRead(Side.top), const NormBox(0, 250, 240, 750));
      expect(grid.handCellForRead(Side.left), const NormBox(200, 0, 800, 290));
    });

    test('손패 칸 폭 비율 = 세운 자리 크롭에서 왼쪽부터 손패 칸이 차지하는 몫', () {
      expect(grid.handFrac(Side.bottom), closeTo(500 / 750, 1e-9));
      expect(grid.handFrac(Side.right), closeTo(600 / 800, 1e-9));
      expect(grid.handFrac(Side.top), closeTo(500 / 750, 1e-9));
      expect(grid.handFrac(Side.left), closeTo(600 / 800, 1e-9));
      // 장면 D 격자(초기값): 아래 (745−280)/(1000−280), 실험 seat_zones.py HAND_FRAC 과 같은 식.
      expect(GridZones.initial.handFrac(Side.bottom), closeTo((745 - 280) / (1000 - 280), 1e-9));
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
      // 도라 구역도 왕복하고, 예전 저장값(dora 없음)은 기본 도라 구역.
      final custom = grid.copyWith(doraRel: (u0: -100, v0: 800, u1: 400, v1: 1300));
      expect(GridZones.fromJson(custom.toJson()), custom);
      expect(GridZones.fromJson({'x1': 250, 'x2': 750, 'y1': 200, 'y2': 800})!.doraRel, doraRelDefault);
    });

    test('처음 설정 틀 → 손패+울기 바깥 띠 선(안쪽 끝 − 1.5u)과 리치봉 상자(기기 + 0.5u), 펠트 위 패는 울기에서 뺌', () {
      // u = 손패 줄 길이 / 13 = 390 / 13 = 30
      final setup = <String, dynamic>{
        'seats': <String, dynamic>{
          'bottom': {'hand': [880, 300, 920, 690], 'melds': [890, 800, 930, 960]},
          'top': {'hand': [40, 310, 80, 700], 'melds': [150, 300, 190, 350]}, // 손패보다 패 1장 넘게 안쪽 → 울기 아님
          'left': {'hand': [300, 40, 690, 80], 'melds': null},
          'right': {'hand': [310, 920, 700, 960], 'melds': [20, 900, 120, 960]},
        },
        'device': [420, 430, 580, 570],
      };
      final g = proposeGrid(setup, keep: grid)!;
      expect([g.x1, g.x2, g.y1, g.y2], [125, 855, 125, 835]);
      expect(g.sticks!.toList(), [405, 415, 595, 585]);
      expect(g.doraRel, grid.doraRel);
      // 손패 틀이 하나라도 없으면 제안하지 않는다
      final seats = Map<String, dynamic>.from(setup['seats'] as Map)..['left'] = {'hand': null, 'melds': null};
      expect(proposeGrid({...setup, 'seats': seats}), isNull);
    });

    test('리치봉 상자를 돌리면 자를 때 돌린 상자를 감싸는 상자, 각도도 JSON 왕복', () {
      final g = grid.copyWith(sticks: const NormBox(400, 450, 600, 550), sticksAngle: 30);
      final b = g.sticksZone;
      expect(b.ymin, lessThan(400));
      expect(b.xmin, lessThan(450));
      expect(GridZones.fromJson(g.toJson()), g);
      expect(grid.copyWith(sticks: const NormBox(400, 450, 600, 550)).sticksZone.toList(), [400, 450, 600, 550]);
    });

    test('도라 크롭: 가운데 칸을 화료자 아닌 쪽으로만 넓힌다', () {
      expect(grid.doraSearchZone().toList(), [160, 210, 840, 790]);
      expect(grid.doraSearchZone(except: {Side.bottom}).toList(), [160, 210, 800, 790]);
      expect(grid.doraSearchZone(except: Side.values.toSet()).toList(), grid.center.toList());
    });

    test('리치봉 상자: 있으면 그 상자로 자르고 추적 띠도 그 안, JSON 왕복, 없으면 가운데 칸 비율', () {
      final g = grid.copyWith(sticks: const NormBox(420, 430, 580, 570));
      expect(g.sticksZone.toList(), [420, 430, 580, 570]);
      expect(GridZones.fromJson(g.toJson()), g);
      final strip = g.stickStrip(Side.bottom);
      expect(strip.ymax, 580);
      expect(strip.ymin, greaterThan(500));
      expect(grid.sticksZone.toList(), isNot([420, 430, 580, 570]));
      expect(GridZones.fromJson(grid.toJson())!.sticks, isNull);
    });

    test('선 기준 도라 구역: 선 앞 패산 오른쪽 끝(자리·가운데 경계에 걸침), 선이 바뀌면 그 자리 쪽으로 돈다', () {
      // 아래가 선: 아래 선(y2=800) 위아래, 가운데 칸 오른쪽 절반부터 오른쪽 모서리 쪽까지.
      expect(grid.doraZone(Side.bottom).toList(), [650, 500, 950, 875]);
      // 오른쪽이 선: 오른쪽 선(x2) 양옆, 그 사람의 오른쪽(사진 위쪽) 끝.
      expect(grid.doraZone(Side.right).toList(), [50, 625, 500, 875]);
      // 위가 선: 위 선(y1) 위아래, 그 사람의 오른쪽(사진 왼쪽) 끝.
      expect(grid.doraZone(Side.top).toList(), [50, 125, 350, 500]);
      // 왼쪽이 선: 왼쪽 선(x1) 양옆, 그 사람의 오른쪽(사진 아래쪽) 끝.
      expect(grid.doraZone(Side.left).toList(), [500, 125, 950, 375]);
    });

    test('도라 상자를 옮기면 아래 기준으로 저장해 다른 선 자리에도 같은 모양으로 돈다', () {
      const box = NormBox(550, 150, 900, 300);
      final moved = grid.withDoraZone(Side.left, box);
      expect(moved.doraZone(Side.left).toList(), box.toList());
      // 왼쪽에서 맞춘 상자를 아래 자리로 돌리면 아래 선 쪽에 온다.
      final b = moved.doraZone(Side.bottom);
      expect(b.ymin, lessThan(grid.y2));
      expect(b.ymax, greaterThan(grid.y2));
      // 선을 옮겨도 가운데 칸 기준이라 상자가 따라간다.
      final shifted = moved.copyWith(x1: 300);
      expect(shifted.doraZone(Side.left).xmin, greaterThan(box.xmin));
    });
  });

  group('왕패(도라 산) 응답', () {
    test('상자·자리를 읽고, 못 찾았거나 상자가 틀리면 null, 자리를 모르면 아래', () {
      final w = parseWallV2({'found': true, 'box': [455, 223, 709, 389], 'side': 'left'})!;
      expect(w.box.toList(), [455, 223, 709, 389]);
      expect(w.side, Side.left);
      expect(parseWallV2({'found': false, 'box': null}), isNull);
      expect(parseWallV2({'found': true, 'box': [500, 300, 400, 200]}), isNull);
      expect(parseWallV2({'found': true, 'box': [1, 2, 3, 4], 'side': null})!.side, Side.bottom);
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
      List<String>? dealerDora,
      List<String>? localDora,
      List<String> loose = const [],
      Map<String, Object>? agreement,
      List<String>? handonlyTiles,
      bool handonlySeparate = true,
      String trackedLastTile = '4p',
      List<Uri>? urls,
    }) => MockClient((r) async {
      urls?.add(r.url);
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
        '/v2/localdora' when localDora != null => _json({
          'indicators': [
            for (final c in localDora) {'tile': c, 'conf': 0.9},
          ],
        }),
        '/v2/dora' => _json({
          'indicators': [
            for (final c in (name == 'dora_dealer' ? dealerDora ?? dora : dora)) {'tile': c, 'conf': 0.9},
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

    group('자체 모델 표시패(/v2/localdora)', () {
      Future<TableReading> read(List<String>? local, {Set<Side> trackedRiichi = const {}, bool on = true, Side? dealer}) {
        final client = RecognizerClient(
          baseUrl: 'https://x.test',
          apiKey: 'k',
          httpClient: server(<String>[], <String, img.Image>{}, localDora: local),
        );
        return TableReader(client).readGrid(table(), grid, trackedRiichi: trackedRiichi, localDora: on, dealer: dealer);
      }

      test('답이 있으면 선 기준 구역·가운데 칸보다 먼저 쓰고 출처를 local 로 남긴다', () async {
        final r = await read(['7z'], dealer: Side.top);
        expect(r.center!.doraIndicators.map((t) => t.code), ['7z']);
        expect(r.center!.doraFrom, DoraFrom.local);
        expect(r.warnings, isEmpty);
      });

      test('답이 비면 Gemini 답으로 돌아간다', () async {
        final r = await read([]);
        expect(r.center!.doraIndicators.map((t) => t.code), ['5s']);
        expect(r.center!.doraFrom, DoraFrom.center);
      });

      test('서버에 없으면(404) 경고 없이 Gemini 답으로 돌아간다', () async {
        final r = await read(null);
        expect(r.center!.doraIndicators.map((t) => t.code), ['5s']);
        expect(r.center!.doraFrom, DoraFrom.center);
        expect(r.warnings, isEmpty);
      });

      test('화료자에 리치 증거가 있으면 표시패 짝을 못 다루므로 쓰지 않는다', () async {
        final r = await read(['7z'], trackedRiichi: {Side.bottom});
        expect(r.center!.doraIndicators.map((t) => t.code), ['5s']);
        expect(r.center!.doraFrom, DoraFrom.center);
      });

      test('끄면 부르지 않는다', () async {
        final r = await read(['7z'], on: false);
        expect(r.center!.doraIndicators.map((t) => t.code), ['5s']);
      });
    });

    group('자체 모델만(readGrid(localOnly:))', () {
      MockClient localServer(List<Uri> urls, {List<int> bottomSideways = const [], List<List<String>> pairs = const [], List<String> wallTile = const ['7z'], bool geminiSticks = false}) =>
          MockClient((r) async {
            urls.add(r.url);
            final files = RegExp(r'filename="([^"]+)\.jpg"').allMatches(latin1.decode(r.bodyBytes)).map((m) => m.group(1)!).toList();
            final name = files.isEmpty ? '' : files.first;
            return switch (r.url.path) {
              '/v2/localseat' => _json({
                'face_up': name == 'seat_bottom',
                'tiles': name == 'seat_bottom' ? [for (final c in hand13) {'tile': c, 'conf': 0.9}] : [],
                'separate_tile': null,
                'melds': [],
                'loose': [],
              }),
              '/v2/localroles' => _json({
                'face_up': r.url.queryParameters['side'] == 'bottom',
                'tiles': r.url.queryParameters['side'] == 'bottom' ? [for (final c in hand13) {'tile': c, 'conf': 0.9}] : [],
                'separate_tile': null,
                'melds': [],
                'loose': [],
              }),
              '/v2/locallast3' => _json({
                'method': 'frame',
                'rivers': [
                  for (final f in files)
                    {
                      'last_tile': f == 'last_right' ? {'tile': '4p', 'conf': 0.9} : {'tile': '9s', 'conf': 0.9},
                      'tile_count': 8,
                      'sideways': f == 'last_bottom' ? bottomSideways : <int>[],
                    },
                ],
              }),
              '/v2/localdora' => _json({
                'indicators': [for (final c in wallTile) {'tile': c, 'conf': 0.9}],
                'pairs': [
                  for (final p in pairs) [for (final c in p) {'tile': c, 'conf': 0.9}],
                ],
              }),
              '/v2/sticks' when geminiSticks => _json({'riichi_sticks': {'bottom': true}}),
              _ => http.Response('Gemini 를 부르면 안 됨: ${r.url.path}', 500),
            };
          });

      Future<TableReading> read(List<Uri> urls, {List<int> bottomSideways = const [], List<List<String>> pairs = const [], List<String> wallTile = const ['7z'], bool geminiSticks = false}) {
        final client = RecognizerClient(
          baseUrl: 'https://x.test',
          apiKey: 'k',
          httpClient: localServer(urls, bottomSideways: bottomSideways, pairs: pairs, wallTile: wallTile, geminiSticks: geminiSticks),
        );
        return TableReader(client).readGrid(table(), grid, localOnly: true, geminiSticks: geminiSticks);
      }

      test('geminiSticks 면 강에 눕힌 패가 없어도 리치봉으로 리치를 본다', () async {
        final urls = <Uri>[];
        final r = await read(urls, geminiSticks: true);
        expect(urls.map((u) => u.path), contains('/v2/sticks'));
        expect(r.center!.riichiAt(Side.bottom), isTrue);
        expect(r.warnings, isEmpty);
      });

      test('자체 모델 API 세 개만 부르고 경고가 없다', () async {
        final urls = <Uri>[];
        final r = await read(urls);
        expect(urls.map((u) => u.path).toSet(), {'/v2/localseat', '/v2/locallast3', '/v2/localdora'});
        expect(r.warnings, isEmpty);
        expect(r.hand!.tiles.length, 13);
        expect(r.center!.doraIndicators.map((t) => t.code), ['7z']);
        expect(r.center!.doraFrom, DoraFrom.local);
        expect(r.center!.lastDiscardAt(Side.right)?.code, '4p');
      });

      test('화료자 강의 눕힌 패로 리치를 보고, 2장 묶음이 하나면 표시패로 쓴다', () async {
        final r = await read(<Uri>[], bottomSideways: [3], pairs: [['1p', '8m']]);
        expect(r.center!.riichiAt(Side.bottom), isTrue);
        expect([for (final t in r.center!.handSideIndicators) t.code], ['1p', '8m']);
      });

      test('역할 경로(useRoles)는 원본을 보내고 강 끝만 자른다 — 자리·리치봉·도라 크롭 없음', () async {
        final urls = <Uri>[];
        final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: localServer(urls));
        final specs = <CropSpec>[];
        Future<ShotImage> open(Uint8List o) async => _CountingShot(DirectShotImage(o), specs);
        final trace = TableReadTrace();
        final r = await TableReader(
          client,
          ops: ImageOps(shrink: (o) async => shrinkForLocate(o), cropMany: (o, s) async => cropMany((o, s)), openShot: open),
        ).readGrid(table(), grid, localOnly: true, useRoles: true, trace: trace);
        expect(urls.map((u) => u.path).toSet(), {'/v2/localroles', '/v2/locallast3', '/v2/localdora'});
        expect(urls.where((u) => u.path == '/v2/localroles').map((u) => u.queryParameters['side']), ['bottom']);
        expect(specs.length, 4); // 네 자리 강 끝만
        expect(trace.handCrop, isNull);
        expect(trace.centerCrop, isNull);
        expect(trace.wallCrop, isNull);
        expect(trace.riverCrops.length, 4);
        expect(r.warnings, isEmpty);
        expect(r.hand!.tiles.length, 13);
        expect(r.center!.lastDiscardAt(Side.right)?.code, '4p');
        expect(r.center!.doraIndicators.map((t) => t.code), ['7z']);
      });

      test('2장 묶음이 둘이면 고르지 않는다', () async {
        final r = await read(<Uri>[], bottomSideways: [3], pairs: [['1p', '8m'], ['0s', '5s']]);
        expect(r.center!.handSideIndicators, isEmpty);
      });

      test('눕힌 패가 없으면 2장 묶음을 쓰지 않는다', () async {
        final r = await read(<Uri>[], pairs: [['1p', '8m']]);
        expect(r.center!.riichiAt(Side.bottom), isFalse);
        expect(r.center!.handSideIndicators, isEmpty);
      });
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
      final urls = <Uri>[];
      final client =
          RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images, urls: urls));
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, trace: trace);

      // seatwide 는 화료자를 알면 자리 판독과 같은 순간에 미리 보낸다(2026-11-01, 답은 필요할 때만 씀).
      expect(names.toSet(), {'seat_bottom', 'seatwide_bottom', 'last_right', 'last_top', 'last_left', 'sticks', 'dora', 'local_dora'});
      // 자리 판독에는 손패 칸 폭 비율을 같이 보낸다(서버가 틀을 못 잡으면 손패 칸·모서리 칸으로 나눠 다시 잡음).
      expect(urls.singleWhere((u) => u.path == '/v2/seat').queryParameters, {'hand_frac': '0.667'});
      // 장면 시간을 정하는 자리 판독을 먼저 보낸다(나머지 구역은 그 뒤에 잘라 보냄).
      expect(names.first, 'seat_bottom');
      // 아래 자리 = 750×200 + 가운데 쪽 40, 오른쪽 강 끝은 오른쪽 자리 방향으로 세워 가로·세로가 바뀐다.
      expect(images['seat_bottom']!.width, 750);
      expect(images['seat_bottom']!.height, 240);
      expect(images['last_right']!.width, 360);
      expect(images['last_right']!.height, 250);
      // 도라는 가운데 칸을 화료자(아래) 아닌 쪽으로 넓혀서: 폭 500 + 왼쪽·오른쪽 40, 높이 600 + 위 40(아래는 그대로).
      expect(images['dora']!.width, 580, reason: '도라는 가운데 칸을 넓혀서');
      expect(images['dora']!.height, 640);

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

    test('rectify: 펠트를 찾으면 사진을 펴서(3200 정사각) 표준 격자로 자르고, 손패 칸 비율도 표준 격자 것', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final urls = <Uri>[];
      final client =
          RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images, urls: urls));
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, rectify: true, trace: trace);

      expect(trace.feltQuad, isNotNull);
      expect(trace.timingsMs, contains('rectify'));
      expect(reading.winnerSide, Side.bottom);
      // 표준 격자(200/800)의 아래 자리 = 편 사진(3200) 아래 20% + 가운데 쪽 4%, 전체 폭.
      expect(images['seat_bottom']!.width, 2560);
      expect(images['seat_bottom']!.height, 768);
      expect(urls.singleWhere((u) => u.path == '/v2/seat').queryParameters, {'hand_frac': '0.750'});
    });

    test('rectify: 펠트가 없으면 맞춘 격자 그대로', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, images));
      final trace = TableReadTrace();
      final gray = img.Image(width: 1000, height: 1000);
      img.fill(gray, color: img.ColorRgb8(128, 128, 128));
      await TableReader(client)
          .readGrid(Uint8List.fromList(img.encodeJpg(gray)), grid, rectify: true, trace: trace, pickWinners: (c) async => [c.first])
          .catchError((Object _) => TableReading(layout: grid.toLayout(faceUp: const [])));
      expect(trace.feltQuad, isNull);
      expect(images['seat_bottom']!.width, 750, reason: '원본 1000px 의 맞춘 격자(아래 자리 750×200)로 자름');
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
      final urls = <Uri>[];
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, urls: urls),
      );
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, tracked: trackedPon, trace: trace);

      expect(names, contains('handonly_bottom'));
      // 확정한 울기 수를 같이 보낸다(서버 손패 틀의 장수 검사용).
      expect(urls.singleWhere((u) => u.path == '/v2/handonly').queryParameters, {'melds': '1'});
      expect(names, isNot(contains('seat_bottom')));
      // 손패 칸(선 사이)만: 500×200 + 가운데 쪽 40. 자리 전체(폭 750)가 아니다.
      expect(images['handonly_bottom']!.width, 500);
      expect(images['handonly_bottom']!.height, 240);
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

    test('선을 알면 선 기준 도라 구역을 따로 잘라 같이 읽고, 거기서 찾으면 그것을 쓴다', () async {
      final names = <String>[];
      final images = <String, img.Image>{};
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, dora: ['5s'], dealerDora: ['7m', '6s']),
      );
      final trace = TableReadTrace();
      final reading = await TableReader(client).readGrid(table(), grid, dealer: Side.left, trace: trace);
      expect(names, containsAll(['dora', 'dora_dealer']));
      expect([for (final t in reading.center!.doraIndicators) t.code], ['7m', '6s']);
      // 왼쪽 선 쪽으로 세운 크롭: 도라 구역 [500,125,950,375] 는 세로로 길고, 왼쪽으로 세우면 가로가 길다.
      expect(images['dora_dealer']!.width, greaterThan(images['dora_dealer']!.height));
      expect(trace.dealerDoraCrop, isNotNull);
    });

    test('선 기준 도라 구역에서 못 찾으면 가운데 칸 도라를 쓴다, 선을 모르면 부르지 않는다', () async {
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server([], {}, dora: ['5s'], dealerDora: []),
      );
      final reading = await TableReader(client).readGrid(table(), grid, dealer: Side.bottom);
      expect([for (final t in reading.center!.doraIndicators) t.code], ['5s']);

      final names = <String>[];
      await TableReader(RecognizerClient(baseUrl: 'https://x.test', apiKey: 'k', httpClient: server(names, {})))
          .readGrid(table(), grid);
      expect(names, isNot(contains('dora_dealer')));
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
      final urls = <Uri>[];
      final client = RecognizerClient(
        baseUrl: 'https://x.test',
        apiKey: 'k',
        httpClient: server(names, images, dora: [], loose: ['7m'], urls: urls),
      );
      final reading = await TableReader(client).readGrid(table(), grid, splitSeat: true);
      expect(names.toSet(), {'seat_bottom', 'corner_bottom', 'last_right', 'last_top', 'last_left', 'sticks', 'dora', 'local_dora'});
      expect(urls.singleWhere((u) => u.path == '/v2/seat').queryParameters, isEmpty, reason: '손패 칸만 보내면 비율 없음');
      // 아래 손패 칸 500×200, 오른쪽 아래 모서리 칸 250×200.
      expect(images['seat_bottom']!.width, 500);
      expect(images['corner_bottom']!.width, 250);
      expect(reading.hand!.melds.single.tiles.map((t) => t.code), ['6z', '6z', '6z']);
      expect([for (final t in reading.center!.handSideIndicators) t.code], ['7m', '9s']);
    });
  });
}
