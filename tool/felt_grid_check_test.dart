// 실제 사진·추적 프레임에 lib/table/felt_grid.dart 를 돌려 결과를 JSON 으로 남긴다(2026-11-02, API 없음). 전체 테스트에는 안 들어간다.
//   flutter test tool/felt_grid_check_test.dart   → experiments/tile_classifier/data/zone_points/dart_felt.json, 대조는 experiments/zone_points/dart_check.py
import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/rectify.dart' show FeltQuad;
import 'dart:math' as math;

void main() {
  // 앞 테스트 결과(dart_felt.json)를 시각 순서로 FeltWatch 에 넣어 카메라 이동 판정을 본다. FELT_STEP 장마다 한 번 읽는 것을 흉내 낸다.
  test('프레임 순서대로 이동 감지', () {
    const dir = 'experiments/tile_classifier/data/zone_points';
    final rows = jsonDecode(File('$dir/proposals.json').readAsStringSync()) as Map<String, dynamic>;
    final file = File('$dir/dart_felt.json');
    if (!file.existsSync()) return;
    final dart = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final names = [for (final e in rows.entries) if ((e.value as Map)['kind'] == 'frame') e.key]
      ..sort((a, b) => ((rows[a] as Map)['at'] as String).compareTo((rows[b] as Map)['at'] as String));
    for (final step in [1, 2]) {
      final watch = FeltWatch();
      final events = <String>[];
      for (var i = 0; i < names.length; i += step) {
        final d = dart[names[i]] as Map<String, dynamic>?;
        FeltQuad? q;
        if (d != null && d['ok'] == true) {
          final f = [for (final p in d['felt'] as List) math.Point<double>((p as List)[0] as double, p[1] as double)];
          q = FeltQuad(f[0], f[1], f[2], f[3]);
        }
        final hadBasis = watch.basis != null;
        final moved = watch.add(q);
        if (moved != null || (!hadBasis && watch.basis != null)) {
          final g = gridFromFelt(watch.basis!);
          events.add('${(rows[names[i]] as Map)['at']} ${names[i]} ${g?.x1},${g?.x2},${g?.y1},${g?.y2}');
        }
      }
      // ignore: avoid_print
      print('step=$step 판정 ${events.length}회\n  ${events.join('\n  ')}');
    }
  }, timeout: const Timeout(Duration(minutes: 2)));

  test('사진·프레임 전부', () {
    const dir = 'experiments/tile_classifier/data/zone_points';
    final rows = jsonDecode(File('$dir/proposals.json').readAsStringSync()) as Map<String, dynamic>;
    final zips = <String, Archive>{};
    final out = <String, Object?>{};
    final sw = Stopwatch();
    var ms = 0, frames = 0;
    for (final e in rows.entries) {
      final src = (e.value as Map<String, dynamic>)['src'];
      final List<int> bytes;
      if (src is List) {
        final a = zips.putIfAbsent(src[0] as String, () => ZipDecoder().decodeBytes(File(src[0] as String).readAsBytesSync()));
        bytes = a.findFile(src[1] as String)!.content;
      } else {
        bytes = File(src as String).readAsBytesSync();
      }
      final im = img.decodeJpg(bytes as dynamic)!;
      sw
        ..reset()
        ..start();
      final r = readFelt(im);
      sw.stop();
      if (src is List) {
        ms += sw.elapsedMilliseconds;
        frames++;
      }
      final g = r == null ? null : gridFromFelt(r.quad);
      out[e.key] = r == null
          ? null
          : {
              'felt': [for (final p in r.quad.corners) [p.x, p.y]],
              'span': r.minSpan,
              'device': r.deviceShare,
              'edge': r.deviceEdge,
              'outside': r.outsideMax,
              'inside': r.insideMin,
              'off': r.offImage,
              'ratio': r.sideRatio,
              'ok': r.ok,
              'grid': g?.toJson(),
            };
    }
    File('$dir/dart_felt.json').writeAsStringSync(jsonEncode(out));
    // ignore: avoid_print
    print('프레임 $frames장 평균 ${(ms / frames).toStringAsFixed(1)}ms (읽기만, 노트북)');
  }, timeout: const Timeout(Duration(minutes: 30)));
}
