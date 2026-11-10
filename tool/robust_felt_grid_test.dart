// 흔들기 회귀 세트(개선 계획 3단계, experiments/speed/ROBUST.md)의 회전 변형 격자를 앱 갤러리 경로와 같게 잡는다(2026-11-05, API 없음).
// 전체 테스트에는 안 들어간다. 앱 갤러리: feltQuadOfJpeg → gridFromFelt(mount_screen.dart _readFeltOf, keep 은 도라 구역 모양만 바꿔 여기선 안 씀).
//   python -I -X utf8 experiments/speed/robust_suite.py make   → experiments/speed/robust/felt_in.json [{key, path}]
//   flutter test tool/robust_felt_grid_test.dart              → experiments/speed/robust/felt_out.json {key: {felt, grid} | null}
//   FELT_DIR=<폴더> 를 주면 그 폴더의 felt_in.json → felt_out.json(2026-11-10, 11-07 원본 격자: experiments/visit_20261107/make_grids.py)
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/table/felt_grid.dart';

void main() {
  test('흔들기 회귀 세트 펠트 격자', () {
    final dir = Platform.environment['FELT_DIR'] ?? 'experiments/speed/robust';
    final inFile = File('$dir/felt_in.json');
    if (!inFile.existsSync()) return;
    final rows = jsonDecode(inFile.readAsStringSync()) as List<dynamic>;
    final outFile = File('$dir/felt_out.json');
    final out = outFile.existsSync() ? jsonDecode(outFile.readAsStringSync()) as Map<String, dynamic> : <String, dynamic>{};
    var found = 0;
    for (final r in rows) {
      final key = (r as Map<String, dynamic>)['key'] as String;
      final q = feltQuadOfJpeg(File(r['path'] as String).readAsBytesSync());
      final g = q == null ? null : gridFromFelt(q);
      out[key] = g == null
          ? null
          : {
              'felt': [for (final p in q!.corners) [p.x, p.y]],
              'grid': g.toJson(),
            };
      if (g != null) found++;
      // ignore: avoid_print
      print('$key ${g?.toJson()}');
    }
    outFile.writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
    // ignore: avoid_print
    print('펠트 격자 $found/${rows.length}');
  }, timeout: const Timeout(Duration(minutes: 30)));
}
