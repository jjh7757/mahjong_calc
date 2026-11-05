import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/frame_recorder.dart';
import 'package:mahjong_calc/table/river_tracker.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/tracker.dart';

final _t0 = DateTime(2026, 10, 29, 20, 0, 0);
Uint8List _jpg(int i) => Uint8List.fromList([0xFF, 0xD8, i, 0xFF, 0xD9]);

/// [whys] 의 i 번째가 비어 있지 않으면 변화 프레임. 남은 프레임 번호.
List<int> _keep(FrameRecorder r, List<List<String>> whys) {
  for (var i = 0; i < whys.length; i++) {
    r.add(_jpg(i), _t0.add(Duration(seconds: 3 * i)), why: whys[i]);
  }
  return [for (final f in r.take()) f.index];
}

void main() {
  group('배경 프레임 모으기', () {
    test('변화 프레임과 앞 2장·뒤 2장만', () {
      final r = FrameRecorder(every: 0);
      final whys = List.generate(12, (_) => <String>[]);
      whys[5] = ['corner_left_moving'];
      expect(_keep(r, whys), [4, 5, 6, 7, 8]);
    });

    test('변화가 이어지면 겹치지 않고 이어 붙는다', () {
      final r = FrameRecorder(every: 0);
      final whys = List.generate(12, (_) => <String>[]);
      whys[3] = ['a'];
      whys[5] = ['b'];
      // 5 는 a 의 뒤이자 b 의 앞, 7·8 은 b 의 뒤.
      expect(_keep(r, whys), [2, 3, 4, 5, 6, 7, 8]);
    });

    test('아무 일 없어도 10장마다 한 장', () {
      final r = FrameRecorder();
      expect(_keep(r, List.generate(25, (_) => <String>[])), [10, 20]);
    });

    test('전부 남기기: 모든 프레임, 변화 프레임은 까닭 그대로', () {
      final r = FrameRecorder(keepAll: true);
      final whys = List.generate(6, (_) => <String>[]);
      whys[2] = ['corner_left_moving'];
      for (var i = 0; i < whys.length; i++) {
        r.add(_jpg(i), _t0.add(Duration(seconds: 3 * i)), why: whys[i]);
      }
      final kept = r.take();
      expect([for (final f in kept) f.index], [1, 2, 3, 4, 5, 6]);
      expect([for (final f in kept) f.why.single], ['all', 'all', 'corner_left_moving', 'all', 'all', 'all']);
    });

    test('추적 안 거친 프레임은 전부 남기기일 때만', () {
      final r = FrameRecorder();
      expect(r.addUntracked(_jpg(0), _t0), isFalse);
      expect(r.seen, 0);
      r.keepAll = true;
      expect(r.addUntracked(_jpg(1), _t0), isTrue);
      r.add(_jpg(2), _t0);
      final kept = r.take();
      expect([for (final f in kept) f.index], [1, 2]);
      expect(kept.first.why, ['untracked']);
    });

    test('전부 남기기를 끄면 다시 변화 주변만', () {
      final r = FrameRecorder(every: 0, keepAll: true);
      r.add(_jpg(0), _t0);
      r.keepAll = false;
      final whys = List.generate(8, (_) => <String>[]);
      whys[5] = ['sticks_moving'];
      for (var i = 0; i < whys.length; i++) {
        r.add(_jpg(i + 1), _t0, why: whys[i]);
      }
      // 1 은 켜져 있을 때, 그 뒤는 변화(7번째)와 앞 2장·뒤 2장(뒤는 9 하나만 있음).
      expect([for (final f in r.take()) f.index], [1, 5, 6, 7, 8, 9]);
    });

    test('꽉 차면 isFull, take 뒤에도 번호는 이어진다', () {
      final r = FrameRecorder(every: 1, maxFrames: 3);
      for (var i = 0; i < 3; i++) {
        r.add(_jpg(i), _t0);
      }
      expect(r.isFull, isTrue);
      expect(r.take(), hasLength(3));
      expect(r.isFull, isFalse);
      r.add(_jpg(9), _t0);
      expect(r.take().single.index, 4);
      r.reset();
      r.add(_jpg(9), _t0);
      expect(r.take().single.index, 1);
    });

    test('zip: 프레임 그대로 + frames.json', () {
      final r = FrameRecorder(every: 0);
      final whys = List.generate(4, (_) => <String>[]);
      whys[2] = ['sticks_changed'];
      for (var i = 0; i < whys.length; i++) {
        r.add(_jpg(i), _t0.add(Duration(seconds: 3 * i)), why: whys[i]);
      }
      final frames = r.take();
      final zip = encodeFramesZip((frames, {'round_key': 'g/동1국/0/0'}));
      final a = ZipDecoder().decodeBytes(zip);
      expect(a.files.map((f) => f.name), ['f0001_200000.jpg', 'f0002_200003.jpg', 'f0003_200006.jpg', 'f0004_200009.jpg', 'frames.json']);
      expect(a.findFile('f0003_200006.jpg')!.content, _jpg(2));
      final j = jsonDecode(utf8.decode(a.findFile('frames.json')!.content)) as Map<String, dynamic>;
      expect(j['round_key'], 'g/동1국/0/0');
      expect([for (final f in j['frames'] as List) f['why']], [
        ['before'],
        ['before'],
        ['sticks_changed'],
        ['after'],
      ]);
    });
  });

  group('프레임의 추적 변화', () {
    test('움직이는 모서리·리치봉, 새 기록(버림패 빼고), 장면 이동', () {
      final melds = MeldTracker(tileFrac: const {});
      final river = RiverTracker(tileFrac: const {});
      expect(frameChanges(melds: melds, river: river, meldEventsFrom: 0, riverEventsFrom: 0), isEmpty);

      melds.seat(Side.left).status = TrackStatus.moving;
      river.sticks.status = StickStatus.changed;
      melds.events.add(TrackerEvent(_t0, Side.top, 'confirmed', ''));
      river.events
        ..add(TrackerEvent(_t0, Side.right, 'discard', ''))
        ..add(TrackerEvent(_t0, Side.right, 'taken', ''));
      expect(
        frameChanges(melds: melds, river: river, meldEventsFrom: 0, riverEventsFrom: 0, sceneShift: true),
        ['scene_shift', 'corner_left_moving', 'sticks_changed', 'corner_top_confirmed', 'river_right_taken'],
      );
      // 이미 본 기록은 다시 안 센다. 버림패만 새로 생기면 변화 없음.
      melds.seat(Side.left).status = TrackStatus.idle;
      river.sticks.status = StickStatus.idle;
      river.events.add(TrackerEvent(_t0, Side.bottom, 'discard', ''));
      expect(frameChanges(melds: melds, river: river, meldEventsFrom: 1, riverEventsFrom: 2), isEmpty);
      // 추적기를 새로 만들어 기록이 줄었으면 처음부터.
      expect(frameChanges(melds: melds, river: river, meldEventsFrom: 9, riverEventsFrom: 0), ['corner_top_confirmed', 'river_right_taken']);
    });
  });
}
