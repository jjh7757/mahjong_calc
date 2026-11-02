import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

Game _game() => Game(
      id: 'g',
      startedAt: DateTime(2026, 11, 2),
      settings: const GameSettings(),
      names: const ['A', 'B', 'C', 'D'],
    );

Map<String, dynamic> _pair(double a, double b) => {
      'pairs': [
        [
          {'tile': '3p', 'conf': a},
          {'tile': '6z', 'conf': b},
        ],
      ],
    };

/// `/v2/localseat` 응답 모양 → 병합. 손패 끝은 쯔모패.
TableMerge _merge(List<(String, double)> tiles, {List<(String, double)> melds = const []}) {
  final seat = parseSeatV2({
    'face_up': true,
    'tiles': [
      for (final (t, c) in tiles) {'tile': t, 'conf': c},
    ],
    'melds': [
      for (final (t, c) in melds) {'tiles': t.split(' '), 'sideways': <int>[], 'face_down': <int>[], 'conf': c},
    ],
  });
  return mergeReading(
    hand: HandReading(
      tiles: seat.tiles.sublist(0, seat.tiles.length - 1),
      winTile: seat.tiles.last,
      melds: [for (final m in seat.melds) m.toReadMeld()],
    ),
    center: CenterReading.fromJson(const {}),
    winnerSide: Side.bottom,
    game: _game(),
    seats: const SeatMap(0),
  );
}

String? _blocker(TableMerge m) => autoRecordBlocker(
      warnings: const [],
      issues: [for (final f in m.flags) f.issue],
      otherWinners: 0,
      isTsumo: true,
      loser: null,
      resultValid: true,
      paoBase: 0,
      gameOver: false,
      doraIndicators: 1,
      riichi: false,
    );

void main() {
  group('자체 모델 표시패 짝', () {
    test('딱 하나이고 둘 다 확신이 높으면 그 둘', () {
      expect([for (final t in localPairIndicators(_pair(0.81, 0.9))) t.code], ['3p', '6z']);
    });

    test('한 장이라도 확신이 낮으면 고르지 않는다(돌아가 겹친 패 0.33·0.58, 170105)', () {
      expect(localPairIndicators(_pair(0.33, 0.58)), isEmpty);
      expect(localPairIndicators(_pair(0.9, 0.58)), isEmpty);
    });

    test('짝이 여럿이거나 없으면 고르지 않는다', () {
      final two = {
        'pairs': [..._pair(0.9, 0.9)['pairs'] as List, ..._pair(0.9, 0.9)['pairs'] as List],
      };
      expect(localPairIndicators(two), isEmpty);
      expect(localPairIndicators(const {'pairs': []}), isEmpty);
      expect(localPairIndicators(null), isEmpty);
    });
  });

  group('자체 모델 확신도가 자동 반영을 막는다', () {
    const hand = '1m 2m 3m 4p 5p 6p 7s 8s 9s 2m 3m 5p 5p 4m';
    List<(String, double)> tiles(double Function(int i) conf) => [
          for (final (i, t) in hand.split(' ').indexed) (t, conf(i)),
        ];

    test('분류기 답이 다 높으면 막지 않는다', () {
      final m = _merge(tiles((_) => 0.9));
      expect(m.uncertain, isEmpty);
      expect(_blocker(m), isNull);
    });

    test('확신이 낮은 패는 노란 테두리 + 자동 반영 막힘', () {
      final m = _merge(tiles((i) => i == 3 ? 0.65 : 0.9));
      expect(m.uncertain, {3});
      expect(_blocker(m), contains('uncertainTiles'));
    });

    test('코드로 채운 白 (확신도 0.5): 손패', () {
      final m = _merge([
        for (final t in '1m 2m 3m 4p 5p 6p 7s 8s 9s 5z 5z 7z 7z 7z'.split(' ')) (t, t == '5z' ? 0.5 : 0.9),
      ]);
      expect(m.uncertain, hasLength(2));
      expect(_blocker(m), contains('uncertainTiles'));
    });

    test('코드로 채운 白 퐁(확신도 0.5): 울기', () {
      final m = _merge(
        [for (final t in '1m 2m 3m 4p 5p 6p 7s 8s 9s 2m 2m'.split(' ')) (t, 0.9)],
        melds: const [('5z 5z 5z', 0.5)],
      );
      expect(m.hasFlag(MergeIssue.meldUncertain), isTrue);
      expect(_blocker(m), contains('meldUncertain'));
    });
  });
}
