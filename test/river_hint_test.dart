import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 병합: 강 끝 패가 여럿 화료될 때 게임 중 추적이 본 "마지막으로 버린 자리"(loserHint)를 방총자로 고른다.
void main() {
  List<Map<String, dynamic>> tiles(String s) => [for (final t in s.split(' ')) {'tile': t, 'conf': 0.9}];

  final g = Game(id: 'g', startedAt: DateTime(2026, 10, 28), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D']);
  const seats = SeatMap(0);

  // 13장 손패, 화료패 없음 → 강 끝에서 찾는다. 4m 대기(1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 2p 3p → 1p/4p 대기).
  HandReading hand() => HandReading.fromJson({'tiles': tiles('1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 2p 3p')});
  CenterReading center() => CenterReading.fromJson({
        'last_discards': {'right': '4p', 'left': '4p', 'top': '9s'},
        'last_discards_conf': {'right': 0.9, 'left': 0.9, 'top': 0.9},
      });

  test('힌트가 없으면 동순 후리텐 규칙(화료자 다음 차례에 가까운 쪽)', () {
    final m = mergeReading(hand: hand(), center: center(), winnerSide: Side.bottom, game: g, seats: seats);
    expect(m.loser, seats.seatOf(Side.right));
    expect(m.flags.map((f) => f.message).join(), contains('후리텐'));
  });

  test('힌트가 후보 안에 있으면 그 자리를 방총자로', () {
    final m = mergeReading(
      hand: hand(),
      center: center(),
      winnerSide: Side.bottom,
      game: g,
      seats: seats,
      loserHint: Side.left,
    );
    expect(m.loser, seats.seatOf(Side.left));
    expect(m.flags.map((f) => f.message).join(), contains('게임 중 마지막으로 버린'));
    expect(m.closed.length, 14); // 손패 13 + 왼쪽 강 끝 4p
  });

  test('힌트가 후보 밖이면 무시한다', () {
    final m = mergeReading(
      hand: hand(),
      center: center(),
      winnerSide: Side.bottom,
      game: g,
      seats: seats,
      loserHint: Side.top,
    );
    expect(m.loser, seats.seatOf(Side.right));
  });

  test('화료패를 손패 옆에 둔 론에서도 힌트로 방총자를 가른다', () {
    final h = HandReading.fromJson({
      'tiles': tiles('1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 1p 2p 3p'),
      'win_tile': {'tile': '4p', 'conf': 0.9},
    });
    final m = mergeReading(hand: h, center: center(), winnerSide: Side.bottom, game: g, seats: seats, loserHint: Side.left);
    expect(m.isTsumo, isFalse);
    expect(m.loser, seats.seatOf(Side.left));
  });
}
