// 기기(태블릿·폰) 위에서 판 상태 추적의 프레임 분석 시간을 잰다. 거치 화면은 3초마다 헤드 미리보기 한 장을
// compute(analyzeTableFrame) 로 분석한다(모서리 통계·강 띠·리치봉 띠) — 3초 안에 여유 있게 끝나야 추적이 밀리지 않는다.
// B·C·D 6장을 PC 에서 받아 미리보기 크기(긴 변 SIZES)로 줄여 두고(시간에 안 들어감), 크기마다 REPEAT 번 잰다.
//
// PC: launch.json "photos"(127.0.0.1:8040) + adb reverse tcp:8040 tcp:8040
// flutter drive --profile -d <기기> --driver=test_driver/integration_test.dart \
//   --target=integration_test/track_frame_timing_test.dart --dart-define=PHOTO_URL=http://127.0.0.1:8040
// 결과는 TRACKTIME {...} 줄(JSON)과 크기별 요약 줄.
import 'dart:convert';

import 'package:flutter/foundation.dart' show compute;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';

const _photoUrl = String.fromEnvironment('PHOTO_URL', defaultValue: 'http://127.0.0.1:8040');
const _repeat = int.fromEnvironment('REPEAT', defaultValue: 5);
const _sizes = String.fromEnvironment('SIZES', defaultValue: '960,1440,1920');
const _photos = ['k25', 'k28', 'k15', 'k26', 'k12', 'k16'];

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('추적 프레임 분석 시간(compute, 미리보기 크기별)', (tester) async {
    final originals = <String, img.Image>{};
    for (final p in _photos) {
      final r = await http.get(Uri.parse('$_photoUrl/$p.jpg'));
      expect(r.statusCode, 200, reason: '$p 사진을 못 받음');
      originals[p] = img.decodeJpg(r.bodyBytes)!;
    }
    final sizes = _sizes.split(',').map(int.parse).toList();
    for (final long in sizes) {
      final ms = <int>[];
      for (final p in _photos) {
        final o = originals[p]!;
        final small = o.width >= o.height ? img.copyResize(o, width: long) : img.copyResize(o, height: long);
        final jpeg = img.encodeJpg(small, quality: 80);
        // 첫 번은 isolate·JIT 준비가 섞일 수 있어 따로 적는다(warm).
        for (var i = 0; i <= _repeat; i++) {
          final sw = Stopwatch()..start();
          await compute(analyzeTableFrame, (jpeg, GridZones.initial));
          final t = sw.elapsedMilliseconds;
          // ignore: avoid_print
          print('TRACKTIME ${jsonEncode({'long': long, 'photo': p, 'run': i, 'warm': i == 0, 'ms': t, 'bytes': jpeg.length})}');
          if (i > 0) ms.add(t);
        }
      }
      ms.sort();
      int q(double f) => ms[((ms.length - 1) * f).round()];
      // ignore: avoid_print
      print('TRACKSUM 긴 변 $long: ${ms.length}회 중앙 ${q(0.5)}ms / p90 ${q(0.9)}ms / 최대 ${ms.last}ms');
    }
  });
}
