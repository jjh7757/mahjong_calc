// 거치 점검(`lib/table/mount_check.dart`)을 테스트 세트 원본과 그 변형(회귀 세트 `experiments/speed/robust/`)에 돌린다(2026-11-13, API 없음).
// 전체 테스트에는 안 들어간다. 사진 자체를 촬영 사진으로 본다(촬영 긴 변 = 그 사진 긴 변).
//   python -I -X utf8 experiments/speed/robust_suite.py make        → robust/meta.json {변형: {사진: {src}}}
//   flutter test tool/mount_check_measure_test.dart                 → experiments/speed/results/mount_check.json {변형: {사진: MountCheck.toJson}}
//   MOUNT_VARIANTS=orig,sq 로 변형을 고른다(있던 결과에 덮어 더함).
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/mount_check.dart';

const _default = 'orig,sq,sqfit,sqfit2992,scale08,scale06,rot_p3,rot_m3,rot_p10,rot_m10,rot_p25,rot_m25';

void main() {
  test('거치 점검 재기', () {
    final meta = jsonDecode(File('experiments/speed/robust/meta.json').readAsStringSync()) as Map<String, dynamic>;
    final outFile = File('experiments/speed/results/mount_check.json');
    final out = outFile.existsSync() ? jsonDecode(outFile.readAsStringSync()) as Map<String, dynamic> : <String, dynamic>{};
    for (final v in (Platform.environment['MOUNT_VARIANTS'] ?? _default).split(',')) {
      final scenes = meta[v] as Map<String, dynamic>?;
      if (scenes == null) continue;
      final rows = <String, dynamic>{};
      final count = <String, int>{};
      for (final MapEntry(key: name, value: info) in scenes.entries) {
        final im = img.decodeJpg(File((info as Map<String, dynamic>)['src'] as String).readAsBytesSync())!;
        final sw = Stopwatch()..start();
        final c = checkMount(im, captureLongSide: math.max(im.width, im.height));
        rows[name] = {...c.toJson(), 'size': [im.width, im.height], 'ms': sw.elapsedMilliseconds};
        count[c.level.name] = (count[c.level.name] ?? 0) + 1;
        // ignore: avoid_print
        print('$v/$name ${c.level.name} ${c.items.map((i) => '${i.key}=${i.level.name}(${i.value})').join(' ')}');
      }
      out[v] = rows;
      // ignore: avoid_print
      print('== $v $count');
      outFile.writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
    }
  }, timeout: const Timeout(Duration(minutes: 60)));
}
