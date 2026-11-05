// [테스트 세트] 10/24 매장 삼각대 15장(+ 색 바꾼 사본)을 앱과 같은 규칙으로 펴서 저장한다(개선 계획 1단계, 2026-11-05, API 없음).
// 펴기는 측정 테스트 `integration_test/read_grid_timing_test.dart` `_rectifyJob` 과 같다: 긴 변 1000 축소본에서 findFeltQuad →
// 원본을 rectify(size 3200) → JPEG q92. 서버 단독 벤치(`field_bench.py --rectify`)가 이 파일을 표준 격자로 읽는다.
// 펠트 격자(`felt_grid.dart`)도 원본·편 사진 양쪽에 돌려 기록만 한다(편 사진은 표준 격자라 필요 없을 수 있음).
// **이 결과로 펴기 비율·표준 격자·펠트 규칙을 고치지 않는다**(테스트 세트).
//   flutter test tool/rectify_field_test.dart
//   → experiments/field_20261024/captures{,_recolor}/20261024_<사진>/rectified.jpg, experiments/rectify/results/field_rectify.json
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/rectify.dart';

// read_grid_timing_test.dart `_field` 와 같은 15장(131823 은 EXIF 회전이 달라 뺌).
const _photos = [
  '122922', '124007', //
  '125053', '130533', '131210', '132647', '133011', '133620', '134323', '135148',
  '135912', '140302', '140750', '140918', '143443',
];

Map<String, Object?> _gridJson(dynamic g) => g == null ? {} : {'x1': g.x1, 'x2': g.x2, 'y1': g.y1, 'y2': g.y2};

void main() {
  final out = <String, Object?>{};
  for (final set in ['captures', 'captures_recolor']) {
    for (final p in _photos) {
      test('$set $p', () {
        final dir = 'experiments/field_20261024/$set/20261024_$p';
        final bytes = File('$dir/original.jpg').readAsBytesSync();
        final im = img.decodeJpg(bytes)!;
        final q = findFeltQuad(img.copyResize(im, width: 1000));
        final row = <String, Object?>{'w': im.width, 'h': im.height, 'quad': q?.toJson(), 'area': q?.area};
        // 펠트 격자: 원본에서
        final fq = feltQuadOfJpeg(bytes);
        row['felt_grid_original'] = fq == null ? null : _gridJson(gridFromFelt(fq));
        final rectFile = File('$dir/rectified.jpg');
        if (q == null) {
          if (rectFile.existsSync()) rectFile.deleteSync();
        } else {
          final jpg = img.encodeJpg(rectify(im, q, size: 3200), quality: 92);
          rectFile.writeAsBytesSync(jpg);
          final rq = feltQuadOfJpeg(jpg);
          row['felt_quad_rectified'] = rq?.toJson();
          row['felt_grid_rectified'] = rq == null ? null : _gridJson(gridFromFelt(rq));
        }
        (out[set] ??= <String, Object?>{}) as Map<String, Object?>;
        (out[set] as Map<String, Object?>)[p] = row;
        // ignore: avoid_print
        print('RECT $set $p quad=${q != null} felt(원본)=${row['felt_grid_original']} felt(편)=${row['felt_grid_rectified']}');
      }, timeout: const Timeout(Duration(minutes: 2)));
    }
  }
  tearDownAll(() {
    final f = File('experiments/rectify/results/field_rectify.json')..createSync(recursive: true);
    f.writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
  });
}
