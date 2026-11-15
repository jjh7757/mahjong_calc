// ignore_for_file: avoid_print
// 유국 공탁을 홈이 아니라 가운데 주사위 창 위에 모아 둔 장면(2026-11-13, 사용자 "돌려 봐")에서 기기 리치봉 판정이 어떻게 나오나.
// 추적 폴더의 frames_*.zip 프레임 전부에 앱과 같은 stickSlotsIn(프레임, grid.sticksZone)을 돌려 결과를 JSON 으로 남긴다.
//   dart run experiments/tracking/stick_center_check.dart <추적 폴더>... → experiments/tracking/results/stick_center_<폴더>.json
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/stick_slots.dart';

void main(List<String> args) {
  Directory('experiments/tracking/results').createSync(recursive: true);
  for (final dir in args) {
    final zips = Directory(dir).listSync().whereType<File>().where((f) => RegExp(r'frames_\d+\.zip$').hasMatch(f.path)).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    final out = <Map<String, Object?>>[];
    for (final z in zips) {
      final a = ZipDecoder().decodeBytes(z.readAsBytesSync());
      final j = jsonDecode(utf8.decode(a.findFile('frames.json')!.content as List<int>)) as Map<String, dynamic>;
      final g = GridZones.fromJson(j['grid'] as Map<String, dynamic>)!;
      for (final f in j['frames'] as List) {
        final file = a.findFile(f['file'] as String);
        if (file == null) continue;
        final im = img.decodeJpg(Uint8List.fromList(file.content as List<int>))!;
        final tr = <String>[];
        final got = stickSlotsIn(im, g.sticksZone, trace: tr);
        out.add({
          'zip': z.uri.pathSegments.last,
          'file': f['file'],
          'at': f['at'],
          'seen': [for (final e in got.entries) if (e.value) e.key.name],
          'blobs': tr,
        });
      }
    }
    final name = Directory(dir).uri.pathSegments.where((s) => s.isNotEmpty).last;
    File('experiments/tracking/results/stick_center_$name.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert(out));
    print('$name 프레임 ${out.length}');
  }
}
