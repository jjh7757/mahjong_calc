// 0단계 A(지금 규칙): 저장된 서버 read_wall 응답에 앱 localPairIndicators 를 그대로 적용해 답을 JSON 으로 낸다(2026-11-16,
// docs/role_pair_plan_1116.md 4-1 — 규칙을 Python 으로 옮기지 않으려고). 전체 테스트에는 안 들어간다. API 없음.
//   python -X utf8 experiments/tile_classifier/role_pair_eval.py run     → data/role/pair/step0/wall_responses.json
//   flutter test tool/role_pair_rule_test.dart                           → data/role/pair/step0/rule_answers.json
// 입력 장면마다 {winner, grid(seat_grow 격자 그대로 — sticks 가 있으면 포함), wall(read_wall 응답)}. trackedDora 는 주지 않는다.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/observation.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main() {
  test('read_wall 응답 → localPairIndicators', () {
    // 2단계(11-16): ROLE_PAIR_DIR 로 입력·출력 폴더만 바꾼다(role_pair_eval2.py rule). 없으면 0단계 경로 그대로.
    final dir = Platform.environment['ROLE_PAIR_DIR'] ?? 'experiments/tile_classifier/data/role/pair/step0';
    final inFile = File('$dir/wall_responses.json');
    if (!inFile.existsSync()) {
      // ignore: avoid_print
      print('입력 없음: ${inFile.path}');
      return;
    }
    final rows = jsonDecode(inFile.readAsStringSync()) as Map<String, dynamic>;
    final out = <String, Object?>{};
    for (final e in (rows['scenes'] as Map<String, dynamic>).entries) {
      final r = e.value as Map<String, dynamic>;
      final wall = r['wall'] as Map<String, dynamic>?;
      final grid = GridZones.fromJson(r['grid'] as Map<String, dynamic>);
      final winner = SideX.parse(r['winner'] as String?);
      final ans = localPairIndicators(wall, grid: grid, winner: winner);
      final centers = localPairCenters(wall);
      out[e.key] = {
        'tiles': [for (final t in ans) t.toJson()],
        'grid_ok': grid != null,
        'has_sticks': grid?.sticks != null,
        'pairs': [
          for (final (i, p) in parseLocalPairs(wall).indexed)
            {
              'tiles': [for (final t in p) t.toJson()],
              'at': i < centers.length && centers[i] != null ? [centers[i]!.$1, centers[i]!.$2] : null,
              'zone': grid != null && winner != null && i < centers.length && centers[i] != null
                  ? pairZoneOf(grid, winner, centers[i]!).name
                  : null,
              'conf_ok': p.every((t) => t.conf >= localPairMinConf),
            },
        ],
      };
    }
    File('$dir/rule_answers.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert({
      'made': DateTime.now().toIso8601String(),
      'source': inFile.path,
      'scenes': out,
    }));
    // ignore: avoid_print
    print('rule_answers ${out.length}장면 → $dir/rule_answers.json');
  });
}
