import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' show Tiles;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/table/auto_record.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// 병합: 판 중 프레임 투표로 확정한 도라 표시패([TableReading.trackedDora])로 화료 사진의 표시패 답을 검증·보충(2026-11-03, metrics 표 1-53).
void main() {
  final g = Game(id: 'g', startedAt: DateTime(2026, 11, 3), settings: const GameSettings(), names: const ['A', 'B', 'C', 'D']);
  const seats = SeatMap(0);
  List<Map<String, dynamic>> tiles(String s) => [for (final c in s.split(' ')) {'tile': c, 'conf': 0.9}];
  // 멘젠 탕야오 손패(4m 론). 울기 없음.
  final hand = HandReading.fromJson({'tiles': tiles('2m 3m 5m 5m 6p 7p 8p 3s 4s 5s 6s 7s 8s'), 'win_tile': {'tile': '4m', 'conf': 0.9}});
  TableMerge merge({List<Map<String, dynamic>> center = const [], String from = 'local', List<Map<String, dynamic>> handSide = const [], bool riichi = false, String? tracked}) =>
      mergeReading(
        hand: hand,
        center: CenterReading.fromJson({
          'dora_indicators': center,
          'dora_from': from,
          'hand_side_indicators': handSide,
          'riichi': {'bottom': riichi, 'right': false, 'top': false, 'left': false},
          'riichi_conf': {'bottom': riichi ? 0.9 : 0.0, 'right': 0.0, 'top': 0.0, 'left': 0.0},
        }),
        winnerSide: Side.bottom,
        game: g,
        seats: seats,
        trackedDora: tracked == null ? null : ReadTile.fromCode(tracked, 0.9),
      );
  List<String> cautions(TableMerge m) => autoRecordCautions(issues: [for (final f in m.flags) f.issue], doraIndicators: m.situation.doraIndicators.length, riichi: m.situation.riichi);
  List<String> codes(TableMerge m) => [for (final t in m.situation.doraIndicators) Tiles.toCode(t)];

  test('확정값 없음: 예전 그대로(사진 답, 가운데 칸이면 doraFallback 경고)', () {
    final m = merge(center: tiles('5s'), from: 'center');
    expect(codes(m), ['5s']);
    expect(m.flags.map((f) => f.issue), contains(MergeIssue.doraFallback));
    expect(cautions(m), contains('도라'));
  });

  test('리치 아님: 사진 답에 확정값이 들어 있으면 사진 답을 쓰고 경고 없음(깡도라 2장도 그대로)', () {
    final m = merge(center: tiles('5s 7m'), from: 'center', tracked: '5s');
    expect(codes(m), ['5s', '7m']);
    expect(m.flags.map((f) => f.issue), isNot(contains(MergeIssue.doraFallback)), reason: '확정값으로 검증됐으니 빠진 표시패 경고 안 함');
    expect(cautions(m), isEmpty);
  });

  test('리치 아님: 사진에서 못 읽었으면 확정값을 채우고 경고 없음', () {
    final m = merge(tracked: '5s');
    expect(codes(m), ['5s']);
    expect(cautions(m), isEmpty);
    expect(autoRecordBlocker(warnings: const [], issues: [for (final f in m.flags) f.issue], otherWinners: 0, isTsumo: false, loser: 1, resultValid: true, paoBase: 0, gameOver: false), isNull);
  });

  test('리치 아님: 사진 답이 확정값과 다르면 확정값을 쓰고 "도라" 경고(막지는 않음)', () {
    final m = merge(center: tiles('8p'), tracked: '5p');
    expect(codes(m), ['5p']);
    expect(m.flags.map((f) => f.issue), contains(MergeIssue.doraTrackedMismatch));
    expect(cautions(m), contains('도라'));
    expect(autoRecordBlocker(warnings: const [], issues: [for (final f in m.flags) f.issue], otherWinners: 0, isTsumo: false, loser: 1, resultValid: true, paoBase: 0, gameOver: false), isNull);
  });

  test('리치: 탁자 위 짝에 확정한 도라가 들어 있으면 짝 그대로(도라 + 뒷도라)', () {
    final m = merge(handSide: tiles('1z 5z'), riichi: true, tracked: '1z');
    expect(codes(m), ['1z', '5z']);
    expect(cautions(m), isEmpty);
  });

  test('리치: 짝을 다른 패로 잡았으면(165614 류) 확정값 한 장 + "도라"·"표시패" 경고', () {
    final m = merge(handSide: tiles('4m'), riichi: true, tracked: '1z');
    expect(codes(m), ['1z']);
    expect(m.flags.map((f) => f.issue), contains(MergeIssue.doraTrackedMismatch));
    expect(cautions(m), containsAll(['도라', '표시패']));
  });

  test('리치: 짝을 못 찾았으면(170105 류) 확정값 한 장 + "표시패" 경고(뒷도라 모름)', () {
    final m = merge(riichi: true, tracked: '5s');
    expect(codes(m), ['5s']);
    expect(m.flags.map((f) => f.issue), isNot(contains(MergeIssue.doraTrackedMismatch)));
    expect(cautions(m), ['표시패']);
  });
}
