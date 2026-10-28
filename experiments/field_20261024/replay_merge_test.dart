// 저장된 판독 결과(read_grid_test.dart 의 result.json 'observation')를 서버를 부르지 않고 지금 병합 코드로 다시 합쳐
// 점수를 낸다. 병합 규칙을 바꿨을 때 같은 판독으로 결과가 어떻게 바뀌는지 본다. 대국 정보는 read_grid_test 와 같다.
//
// DIR=experiments/field_20261024/seat3_scenes flutter test experiments/field_20261024/replay_merge_test.dart
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' as engine;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reading.dart';

/// result.json 의 관찰 JSON → [TableObservation]. 손패 확신도는 저장돼 있지 않아 병합이 확신 낮다고 본 자리(merge.uncertain)만 0.
TableObservation _observation(Map<String, dynamic> o, Set<int> uncertain, Side winner) {
  ReadTile tile(String c, double conf) => ReadTile.fromCode(c, conf)!;
  final players = <Side, SeatObservation>{};
  for (final s in Side.values) {
    final p = (o['players'] as Map<String, dynamic>)[s.name] as Map<String, dynamic>;
    final h = p['hand'] as Map<String, dynamic>;
    final tiles = [for (final (i, c) in (h['tiles'] as List<dynamic>).indexed) tile('$c', s == winner && uncertain.contains(i) ? 0 : 0.9)];
    players[s] = SeatObservation(
      faceUp: h['face_up'] == true,
      handTiles: tiles,
      separateTile: h['separate_tile'] == null ? null : tile('${h['separate_tile']}', 0.9),
      melds: [
        for (final m in (p['melds'] as List<dynamic>)) ?ObservedMeld.fromJson(m as Map<String, dynamic>),
      ],
      river: p['river'] == null
          ? null
          : [
              for (final t in p['river'] as List<dynamic>)
                RiverTile(tile('${t['tile']}', ((t['conf'] as num?) ?? 0.9).toDouble()), sideways: t['sideways'] == true),
            ],
      riichiStick: p['riichi_stick'] == true,
    );
  }
  return TableObservation(
    players: players,
    doraIndicators: [for (final c in (o['dora_indicators'] as List<dynamic>)) tile('$c', 0.9)],
  );
}

void main() {
  final dir = Directory(Platform.environment['DIR'] ?? 'experiments/field_20261024/seat3_scenes');
  final files = dir.listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('result.json')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  for (final f in files) {
    test(f.path, () {
      final r = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      final o = r['observation'] as Map<String, dynamic>?;
      final side = SideX.parse(r['winner_side'] as String?);
      if (o == null || side == null) return;
      final game = Game(
        id: 'photo',
        startedAt: DateTime(2026, 10, 24),
        settings: const GameSettings(),
        names: const ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4'],
      );
      final uncertain = {for (final i in ((r['merge'] as Map?)?['uncertain'] as List<dynamic>?) ?? const []) i as int};
      final obs = _observation(o, uncertain, side);
      final merge = mergeReading(
        hand: obs.toHandReading(side),
        center: obs.toCenterReading(),
        winnerSide: side,
        game: game,
        seats: SeatMap(game.settings.bottomSeat),
      );
      final score = merge.hand == null ? null : engine.calculate(merge.hand!, merge.situation).toString();
      // ignore: avoid_print
      print('REPLAY ${f.parent.path.split(RegExp(r'[\\/]')).reversed.take(2).toList().reversed.join('/')} '
          '| 전: ${r['score'] ?? '계산 안 됨'} | 후: ${score ?? '계산 안 됨'} | ${[for (final x in merge.flags) x.issue.name]}');
    });
  }
}
