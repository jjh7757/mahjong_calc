// 사진을 미리 그은 격자([GridZones])로 읽어 본다: 칸 크롭 → /v2 동시 호출(손패·모서리·강 끝 3·리치봉·도라) → 병합 → 점수.
// locate 를 부르지 않는다. 실제 서버를 부르므로 비용이 든다. 대국 정보는 동1국 친 = 아래 자리로 둔다.
//
// PHOTOS="a.jpg;b.jpg" OUT=experiments/field_20261024/grid URL=http://127.0.0.1:8010 \
//   flutter test experiments/field_20261024/read_grid_test.dart [--dart-define=RECOGNIZER_API_KEY=...]
// 격자는 GRID='{"x1":..,"x2":..,"y1":..,"y2":..,"panel":[..]}' 로 바꿀 수 있다(기본 GridZones.initial).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' as engine;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/table/table_reader.dart';

void main() {
  final env = Platform.environment;
  final photos = (env['PHOTOS'] ?? '').split(';').where((p) => p.isNotEmpty).toList();
  final out = env['OUT'] ?? 'experiments/field_20261024/grid';
  final url = env['URL'];
  final gridJ = env['GRID'];
  final grid = gridJ == null ? GridZones.initial : GridZones.fromJson(jsonDecode(gridJ) as Map<String, dynamic>)!;
  // 같은 사진을 REPEAT 번 읽어 호출마다 흔들리는지 본다. 운영 서버는 분당 호출 수를 막으므로 SLEEP_S 초씩 쉰다.
  final repeat = int.tryParse(env['REPEAT'] ?? '') ?? 1;
  final pause = Duration(seconds: int.tryParse(env['SLEEP_S'] ?? '') ?? 0);
  var first = true;

  for (final path in photos) {
    for (var run = 1; run <= repeat; run++) {
    test('$path #$run', () async {
      if (!first) await Future<void>.delayed(pause);
      first = false;
      final base = path.split(RegExp(r'[\\/]')).last.replaceAll(RegExp(r'\.\w+$'), '');
      final name = repeat == 1 ? base : '${base}_$run';
      final dir = Directory('$out/$name')..createSync(recursive: true);
      final client = url == null ? RecognizerClient() : RecognizerClient(baseUrl: url);
      final trace = TableReadTrace();
      final game = Game(
        id: 'photo',
        startedAt: DateTime(2026, 10, 24),
        settings: const GameSettings(),
        names: const ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4'],
      );
      final seats = SeatMap(game.settings.bottomSeat);
      final result = <String, Object?>{'photo': path, 'grid': grid.toJson()};
      final sw = Stopwatch()..start();
      try {
        final reading = await TableReader(client).readGrid(
          File(path).readAsBytesSync(),
          grid,
          // SPLIT=1 이면 자리 구역을 손패 칸·모서리 칸으로 나눠 보낸다.
          splitSeat: env['SPLIT'] == '1',
          // 앞면 칸을 못 정하면 앱은 고르기 창을 띄운다. WINNER=left 처럼 주면 사용자가 그 자리를 고른 것으로 친다.
          // WINNER=left,bottom 처럼 둘 이상이면 동시 론(둘 다 론)을 고른 것이다.
          pickWinners: (c) async {
            result['face_up_candidates'] = [for (final s in c) s.name];
            final picked = [
              for (final w in (env['WINNER'] ?? '').split(',')) ?SideX.parse(w.trim()),
            ];
            return picked.isEmpty ? [c.first] : picked;
          },
          trace: trace,
        );
        // 동시 론이면 앱(mount_screen)과 같이 화료자마다 병합하고 규칙에 맞춰 고른다.
        final readings = [reading, ...reading.others];
        final winnerSides = {for (final r in readings) r.winnerSide!};
        final picked = pickRonWinners(
          [
            for (final r in readings)
              mergeReading(
                hand: r.hand!,
                center: r.center,
                winnerSide: r.winnerSide!,
                game: game,
                seats: seats,
                otherWinners: winnerSides.difference({r.winnerSide!}),
              ),
          ],
          game.settings,
          game.names,
        );
        final merge = picked.kept.first;
        result['winner_side'] = reading.winnerSide!.name;
        if (readings.length > 1) {
          result['other_winner_sides'] = [for (final r in reading.others) r.winnerSide!.name];
          result['pick_loser'] = picked.loser;
          result['pick_flags'] = [for (final f in picked.flags) f.message];
          result['others'] = [
            for (final m in picked.kept.skip(1))
              {
                'winner': m.winner,
                'merge': CaptureLog.mergeJson(m),
                'flags': [for (final f in m.flags) f.message],
                'score': m.hand == null ? null : engine.calculate(m.hand!, m.situation).toString(),
              },
          ];
        }
        result['warnings'] = reading.warnings;
        result['merge'] = CaptureLog.mergeJson(merge);
        result['flags'] = [for (final f in merge.flags) f.message];
        if (merge.hand != null) {
          final r = engine.calculate(merge.hand!, merge.situation);
          result['score'] = r.toString();
        }
      } catch (e) {
        result['error'] = '$e';
      } finally {
        client.close();
      }
      result['total_ms'] = sw.elapsedMilliseconds;
      result['timings_ms'] = trace.timingsMs;
      result['analysis'] = trace.analysis?.toJson();
      result['observation'] = trace.observation?.toJson();
      void save(String n, List<int>? b) {
        if (b != null) File('${dir.path}/$n').writeAsBytesSync(b);
      }

      save('hand_${trace.winnerSide?.name}.jpg', trace.handCrop);
      save('sticks.jpg', trace.centerCrop);
      save('wall.jpg', trace.wallCrop);
      for (final (i, m) in trace.meldCrops.indexed) {
        save('corner_$i.jpg', m);
      }
      for (final e in trace.riverCrops.entries) {
        save('last_${e.key.name}.jpg', e.value);
      }
      File('${dir.path}/result.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert(result));
      // ignore: avoid_print
      print('$name ${result['winner_side']} ${result['error'] ?? ''} '
          '${(result['merge'] as Map?)?['closed']} ${(result['merge'] as Map?)?['melds']} '
          'loser=${(result['merge'] as Map?)?['loser']} dora=${(result['merge'] as Map?)?['dora_indicators']} '
          '| ${result['score'] ?? result['flags']} | ${result['total_ms']}ms ${trace.timingsMs}');
      for (final o in (result['others'] as List?) ?? const []) {
        final m = o as Map;
        // ignore: avoid_print
        print('  +함께 론 winner=${m['winner']} ${(m['merge'] as Map)['closed']} ${(m['merge'] as Map)['melds']} '
            '| ${m['score'] ?? m['flags']} | loser=${result['pick_loser']} ${result['pick_flags']}');
      }
    }, timeout: const Timeout(Duration(minutes: 4)));
    }
  }
}
