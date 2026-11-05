import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/corner_change.dart';
import 'package:mahjong_calc/table/frame_vote.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 프레임 투표 규칙(개선 계획 6단계). 명세 `test/fixtures/frame_vote.json` 은 Python `experiments/speed/frame_vote.py test` 도 돌린다.
void main() {
  group('명세 예제(Python 과 같은 답)', () {
    final spec = jsonDecode(File('test/fixtures/frame_vote.json').readAsStringSync()) as Map<String, dynamic>;
    for (final c in (spec['cases'] as List).cast<Map<String, dynamic>>()) {
      test(c['name'] as String, () {
        final a = VoteRead.fromJson(c['a'] as Map<String, dynamic>);
        final b = c['b'] == null ? null : VoteRead.fromJson(c['b'] as Map<String, dynamic>);
        expect(frameVote(a, b).name, c['want']);
      });
    }
  });

  test('서버 응답(/v2/localroles)에서 읽기: 적5·떼어 둔 패·안깡', () {
    final r = VoteRead.fromSeatJson({
      'face_up': true,
      'tiles': [
        {'tile': '4m', 'conf': 0.9},
        {'tile': '0m', 'conf': 0.9},
        {'tile': '6m', 'conf': 0.9},
      ],
      'separate_tile': {'tile': '3p', 'conf': 0.8},
      'melds': [
        {'tiles': ['4s', '4s', '4s', '4s'], 'face_down': [0, 3], 'conf': 0.9},
        {'tiles': ['6z', '6z', '6z'], 'sideways': [1], 'conf': 0.9},
      ],
    });
    expect(r.tiles, ['4m', '0m', '6m']);
    expect(r.separate, '3p');
    expect([for (final m in r.melds) m.closed], [true, false]);
    // 기록 모양으로 갔다가 돌아와도 같은 열쇠.
    expect(VoteRead.fromJson(jsonDecode(jsonEncode(r.toJson())) as Map<String, dynamic>).key, r.key);
  });

  test('불일치만 막는다(일치·투표 못 함은 지금 규칙대로)', () {
    const a = VoteRead(tiles: ['1m']);
    FrameVoteRecord rec(FrameVoteResult r) => FrameVoteRecord(result: r, first: a, totalMs: 0);
    expect(rec(FrameVoteResult.mismatch).blocker, frameMismatchWarning);
    expect(rec(FrameVoteResult.agree).blocker, isNull);
    expect(rec(FrameVoteResult.none).blocker, isNull);
  });

  group('정지 판정', () {
    const still = CornerStats(white: 0.4, pattern: 0.2, cx: 0.5, cy: 0.5);
    const moved = CornerStats(white: 0.2, pattern: 0.1, cx: 0.4, cy: 0.5);
    ZoneSnapshot zone(int g) => ZoneSnapshot(
          box: const NormBox(0, 0, 100, 100),
          cols: 4,
          rows: 2,
          gray: Uint8List.fromList(List.filled(8, g)),
          white: Uint8List(8),
          whiteFrac: 0,
        );
    TableFrameStats frame({Map<Side, CornerStats>? corners, int river = 100}) => TableFrameStats(
          corners: corners ?? {for (final s in Side.values) s: still},
          rivers: {for (final s in Side.values) s: zone(river)},
          strips: {for (final s in Side.values) s: zone(river)},
        );

    test('그대로면 정지', () {
      final r = judgeStill(before: frame(), after: frame(), winner: Side.left, winnerFaceUp: true);
      expect(r.still, isTrue);
      expect(r.changedZones, 0);
    });

    test('다른 자리 모서리 하나가 바뀌어도(손이 지나감) 화료자 모서리가 그대로면 정지', () {
      final after = frame(corners: {for (final s in Side.values) s: s == Side.top ? moved : still});
      expect(judgeStill(before: frame(), after: after, winner: Side.left, winnerFaceUp: true).still, isTrue);
    });

    test('화료자 모서리가 바뀌면 정지 아님', () {
      final after = frame(corners: {for (final s in Side.values) s: s == Side.left ? moved : still});
      final r = judgeStill(before: frame(), after: after, winner: Side.left, winnerFaceUp: true);
      expect(r.still, isFalse);
      expect(r.reason, '화료자 모서리 바뀜');
    });

    test('조명·노출이 한꺼번에 바뀌면 정지 아님', () {
      final r = judgeStill(before: frame(), after: frame(river: 120), winner: Side.left, winnerFaceUp: true);
      expect(r.still, isFalse);
      expect(r.reason, startsWith('장면 전체 변화'));
    });

    test('화료자 손패가 앞면이 아니면(정리 시작) 정지 아님', () {
      final r = judgeStill(before: frame(), after: frame(), winner: Side.left, winnerFaceUp: false);
      expect(r.still, isFalse);
      expect(r.reason, '화료자 손패가 앞면이 아님');
    });
  });
}
