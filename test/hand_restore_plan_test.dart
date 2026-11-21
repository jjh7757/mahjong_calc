import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/paifu/discard_recorder.dart';
import 'package:mahjong_calc/paifu/hand_restore/frames.dart';
import 'package:mahjong_calc/paifu/hand_restore/turns.dart';
import 'package:mahjong_calc/paifu/paifu.dart';

PaifuEvent _d(int seat, String tile, int at, {bool riichi = false}) =>
    PaifuEvent(type: PaifuEventType.discard, seat: seat, tile: PaifuTile.parse(tile), riichi: riichi, at: at);

void main() {
  group('형식(버전 1 그대로, 새 칸은 선택)', () {
    test('예시 11판: 읽고 다시 쓰면 같고, 사건 JSON 은 원본과 같음(guess 포함), 새 칸은 안 생김', () {
      final files = Directory('assets/paifu').listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList();
      expect(files, hasLength(11));
      for (final f in files) {
        final j = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
        final p = Paifu.fromJson(j);
        final once = p.toJson();
        expect(jsonEncode(Paifu.fromJson(jsonDecode(jsonEncode(once)) as Map<String, dynamic>).toJson()), jsonEncode(once), reason: f.path);
        expect(once.containsKey('frames') || once.containsKey('hand_source') || once.containsKey('restore'), isFalse);
        final evs = (j['events'] as List).cast<Map<String, dynamic>>();
        for (final (i, e) in evs.indexed) {
          expect(PaifuEvent.fromJson(e).toJson(), e, reason: '${f.path} 사건 $i');
        }
      }
    });

    test('at · frames · hand_source · restore 를 읽고 쓴다, 옛 촬영 기록의 "frames": 장수는 무시', () {
      final j = {
        'version': 1,
        'id': 'x',
        'hero': 0,
        'events': [
          {'type': 'discard', 'seat': 1, 'tile': '1m', 'tsumogiri': null, 'riichi': false, 'at': 123456},
        ],
        'frames': {'dir': '/a/rec_pull/rec_1', 'box': [280, 713, 1000, 1000], 'side': 'bottom', 'start_ms': 1, 'end_ms': 2},
        'hand_source': 'claude_api',
        'restore': [
          {'turn': 1, 'src': 'api'},
        ],
      };
      final p = Paifu.fromJson(j);
      expect(p.events.single.at, 123456);
      expect(p.frames!.box, [280, 713, 1000, 1000]);
      expect(p.frames!.side, 'bottom');
      expect(p.handSource, 'claude_api');
      expect(p.toJson()['frames'], j['frames']);
      expect(p.toJson()['restore'], j['restore']);
      expect(p.toJson()['events'], j['events']);
      final old = Paifu.fromJson({...j, 'frames': 37});
      expect(old.frames, isNull);
      expect(Paifu.fromJson({...j, 'frames': {'dir': 'd', 'box': [5, 5, 1, 1], 'side': 'bottom'}}).frames, isNull);
      expect(Paifu.fromJson({...j, 'frames': {'dir': 'd', 'box': [0, 0, 9, 9], 'side': 'up'}}).frames, isNull);
    });

    test('버림 기록기 toPaifu 가 버림 사건에 처음 본 시각(at)을 채운다', () {
      final rec = DiscardRecorder();
      final t0 = DateTime(2026, 11, 21, 13);
      const s = RiverSighting(dx: -77, dy: 120, w: 30, h: 40, tile: '5p', conf: 0.97);
      for (var i = 0; i < 4; i++) {
        rec.add(t0.add(Duration(seconds: 3 * i)), [s], hd: 100);
      }
      final p = rec.toPaifu(id: 'x', bottomSeat: 0, dealerSeat: 0, hero: 0);
      expect(p.events.single.at, t0.millisecondsSinceEpoch);
      expect(p.toJson()['events'][0]['at'], t0.millisecondsSinceEpoch);
    });
  });

  group('차례 나누기', () {
    Paifu game(List<PaifuEvent> ev) => Paifu(id: 'g', hero: 0, events: ev);

    test('창: 첫 차례 −20초, 다른 자리 버림 −1.5초, 끝 = 다음 창 시작, 마지막 +8초, 리치 다음은 규칙', () {
      final p = game([
        _d(0, '1z', 10000),
        _d(1, '2z', 14000),
        _d(2, '3z', 18000),
        _d(3, '4z', 22000),
        _d(0, '9m', 30000, riichi: true),
        _d(1, '1p', 34000),
        _d(2, '2p', 40000),
        _d(3, '3p', 46000),
        _d(0, '7s', 50000),
      ]);
      final t = planTurns(p);
      expect(t.map((x) => x.kind), [RestoreTurnKind.api, RestoreTurnKind.api, RestoreTurnKind.rule]);
      expect([for (final x in t) (x.startMs, x.endMs)], [(-10000, 20500), (20500, 44500), (44500, 58000)]);
      expect(t.map((x) => x.n), [13, 13, 13]);
      expect(t.map((x) => x.discardEvent), [0, 4, 8]);
    });

    test('다른 자리가 같은 장면에서 버려 시각이 같으면 시작을 hero 버림 3초 앞으로, 창은 60초까지', () {
      final p = game([
        _d(0, '1z', 10000),
        _d(3, '4z', 200000),
        _d(0, '9m', 200000),
        _d(3, '4p', 300000),
        _d(0, '8m', 400000),
      ]);
      final t = planTurns(p);
      // 둘째: 시작 = 200000 − 3000. 끝(다음 시작 298500)까지 101.5초라 hero 버림 + 8초 뒤 꼬리를 60초에 맞춰 자름.
      expect((t[1].startMs, t[1].endMs), (197000, 257000));
      // 셋째: 298500 ~ 408000(109.5초) — 꼬리는 hero 버림 + 8초라 못 자르고 앞쪽을 자름.
      expect((t[2].startMs, t[2].endMs), (348000, 408000));
      // 첫째: −20초 ~ 다음 시작(197000) → 꼬리를 잘라 60초.
      expect((t[0].startMs, t[0].endMs), (-10000, 50000));
    });

    test('퐁 뒤 버림은 짐작, 묶음을 모르는 울기 뒤 · 시각 없는 버림은 복원 못 함', () {
      final p = game([
        _d(0, '1z', 10000),
        _d(1, '5z', 14000),
        const PaifuEvent(
            type: PaifuEventType.call, seat: 0, callKind: 'pon', from: 1, callTiles: [PaifuTile(31), PaifuTile(31), PaifuTile(31)]),
        _d(0, '9m', 16000),
        _d(1, '6z', 20000),
        const PaifuEvent(type: PaifuEventType.call, seat: 0, callKind: 'call', from: 1, callTiles: [PaifuTile(32)]),
        _d(0, '8m', 22000),
        const PaifuEvent(type: PaifuEventType.discard, seat: 0, tile: PaifuTile(5)),
      ]);
      final t = planTurns(p);
      expect(t.map((x) => x.kind), [RestoreTurnKind.api, RestoreTurnKind.afterCall, RestoreTurnKind.unsupported, RestoreTurnKind.unsupported]);
      expect(t[1].callEvent, 2);
      expect(t[1].n, 13);
      expect(t[2].n, 10);
      expect(t[3].reason, contains('시각'));
    });
  });

  group('프레임', () {
    test('초당 5장: 10fps 에서 한 장 걸러, 창 밖은 뺌', () {
      final all = [for (var i = 0; i < 30; i++) 1000 + i * 100];
      expect(pickFrames(all, 1150, 2000), [1200, 1400, 1600, 1800, 2000]);
      expect(pickFrames(all, 5000, 6000), isEmpty);
      // 고르지 않은 간격: 200ms 에 가장 가까운 것.
      expect(pickFrames([0, 90, 230, 260, 410, 700], 0, 700), [0, 230, 410, 700]);
    });

    Uint8List edgeImage(String side) {
      // 100 × 60, 그 사람 쪽 변 20화소만 흰색(탁자 테두리), 나머지 검정.
      final im = img.Image(width: 100, height: 60);
      img.fill(im, color: img.ColorRgb8(0, 0, 0));
      final (x1, y1, x2, y2) = switch (side) {
        'bottom' => (0, 40, 99, 59),
        'top' => (0, 0, 99, 19),
        'right' => (80, 0, 99, 59),
        _ => (0, 0, 19, 59),
      };
      img.fillRect(im, x1: x1, y1: y1, x2: x2, y2: y2, color: img.ColorRgb8(255, 255, 255));
      return img.encodeJpg(im, quality: 100);
    }

    for (final side in PaifuFrames.sides) {
      test('자르기 · 돌리기: $side 자리는 그 사람 쪽 변이 아래로', () {
        final out = img.decodeJpg(cropOne(edgeImage(side), const [0, 0, 1000, 1000], side, quality: 100))!;
        final across = side == 'bottom' || side == 'top';
        expect((out.width, out.height), across ? (100, 60) : (60, 100));
        expect(out.getPixel(out.width ~/ 2, out.height - 3).r, greaterThan(200)); // 아래 = 흰 띠
        expect(out.getPixel(out.width ~/ 2, 3).r, lessThan(60)); // 위 = 검정
      });
    }

    test('상자로 자른다(0~1000 비율), 원천에서 창 안만 골라 읽음', () async {
      final src = MemoryFrameSource({for (final ms in [0, 100, 200, 300, 400, 5000]) ms: edgeImage('bottom')});
      final f = await loadTurnFrames(src, startMs: 0, endMs: 400, box: const [0, 500, 1000, 1000], side: 'bottom', runner: directRunner);
      expect(f!.ms, [0, 200, 400]);
      expect((f.width, f.height), (100, 30));
      expect(await loadTurnFrames(src, startMs: 4000, endMs: 6000, box: const [0, 0, 1000, 1000], side: 'bottom', runner: directRunner),
          isNull);
    });

    test('긴 변 2576 을 넘는 그림만 줄이고, zoom 은 3배 · strip 은 8줄씩', () {
      final big = img.encodeJpg(img.Image(width: 3000, height: 100), quality: 50);
      final fitted = img.decodeJpg(fitJpeg(big))!;
      expect(fitted.width, 2576);
      final small = img.encodeJpg(img.Image(width: 300, height: 100));
      expect(identical(fitJpeg(small), small), isTrue);
      final z = zoomFrame((jpeg: small, x0: 10, x1: 110, y0: null, y1: null));
      expect((z.x0, z.x1, z.y0, z.y1), (10, 110, 0, 100));
      expect(img.decodeJpg(z.jpeg)!.width, 300);
      final sheets = stripSheets((jpegs: List.filled(10, small), idx: [for (var i = 0; i < 10; i++) i], x0: 0, x1: 300, y0: 0, y1: 50, width: 300, height: 100));
      expect(sheets.map((s) => (s.from, s.to)), [(0, 7), (8, 9)]);
      final s0 = img.decodeJpg(sheets.first.jpeg)!;
      expect(s0.width, 300 * 3 + 70);
      expect(s0.height, 8 * (150 + 4));
    });
  });
}
