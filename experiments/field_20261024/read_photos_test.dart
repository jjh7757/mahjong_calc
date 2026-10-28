// 갤러리 사진(손으로 찍은 것)을 앱의 거치 판독 흐름 그대로 읽어 본다: locate → 크롭 → /v2 → 병합 → 점수.
// 실제 서버를 부르므로 비용이 든다. 대국 정보(친·장풍·본장)는 모르니 동1국 친 = 아래 자리로 둔다.
//
// PHOTOS="a.jpg;b.jpg" OUT=experiments/field_20261024/kakao \
//   flutter test experiments/field_20261024/read_photos_test.dart --dart-define=RECOGNIZER_API_KEY=...
// 서버는 분당 20호출로 막으므로(한 장 9~10호출) SLEEP_S 초씩 쉬며 읽는다(기본 45).
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/engine/calculator.dart' as engine;
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/table/merge.dart';
import 'package:mahjong_calc/table/seat_map.dart';
import 'package:mahjong_calc/table/table_reader.dart';

void main() {
  final photos = (Platform.environment['PHOTOS'] ?? '').split(';').where((p) => p.isNotEmpty).toList();
  final out = Platform.environment['OUT'] ?? 'experiments/field_20261024/kakao';
  final pause = Duration(seconds: int.tryParse(Platform.environment['SLEEP_S'] ?? '') ?? 45);
  var first = true;

  for (final path in photos) {
    test(path, () async {
      if (!first) await Future<void>.delayed(pause);
      first = false;
      final name = path.split(RegExp(r'[\\/]')).last.replaceAll('.jpg', '');
      final dir = Directory('$out/$name')..createSync(recursive: true);
      final client = RecognizerClient();
      final trace = TableReadTrace();
      final game = Game(
        id: 'photo',
        startedAt: DateTime(2026, 10, 24),
        settings: const GameSettings(),
        names: const ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4'],
      );
      final seats = SeatMap(game.settings.bottomSeat);
      final result = <String, Object?>{'photo': path};
      try {
        final reading = await TableReader(client).read(
          File(path).readAsBytesSync(),
          pickWinner: (c) async {
            result['face_up_candidates'] = [for (final s in c) s.name];
            return c.first;
          },
          trace: trace,
        );
        final merge = mergeReading(
          hand: reading.hand!,
          center: reading.center,
          winnerSide: reading.winnerSide!,
          game: game,
          seats: seats,
        );
        result['winner_side'] = reading.winnerSide!.name;
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
      result['timings_ms'] = trace.timingsMs;
      result['layout'] = trace.layout?.toJson();
      result['observation'] = trace.observation?.toJson();
      void save(String n, List<int>? b) {
        if (b != null) File('${dir.path}/$n').writeAsBytesSync(b);
      }

      save('hand_${trace.winnerSide?.name}.jpg', trace.handCrop);
      save('center.jpg', trace.centerCrop);
      save('wall.jpg', trace.wallCrop);
      for (final (i, m) in trace.meldCrops.indexed) {
        save('meld_$i.jpg', m);
      }
      for (final e in trace.riverCrops.entries) {
        save('river_${e.key.name}.jpg', e.value);
      }
      File('${dir.path}/result.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert(result));
      // ignore: avoid_print
      print('$name ${result['winner_side']} ${result['error'] ?? ''} '
          '${(result['merge'] as Map?)?['closed']} ${(result['merge'] as Map?)?['melds']} '
          'loser=${(result['merge'] as Map?)?['loser']} dora=${(result['merge'] as Map?)?['dora_indicators']} '
          '| ${result['score'] ?? result['flags']} | ${trace.timingsMs}');
    }, timeout: const Timeout(Duration(minutes: 4)));
  }
}
