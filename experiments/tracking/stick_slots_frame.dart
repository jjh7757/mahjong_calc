// ignore_for_file: avoid_print
// 추적 프레임 한 장의 리치봉 픽셀 판정과 긴 덩어리를 찍는다(헛 잡음 점검용).
//   dart run experiments/tracking/stick_slots_frame.dart <frames.json> <hh:mm:ss>...
import 'dart:convert';
import 'dart:io';

import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/stick_slots.dart';

void main(List<String> a) {
  final j = jsonDecode(File(a[0]).readAsStringSync()) as Map<String, dynamic>;
  final g = GridZones.fromJson(j['grid'] as Map<String, dynamic>)!;
  final dir = File(a[0]).parent.path;
  for (final t in a.skip(1)) {
    for (final f in j['frames'] as List) {
      if (!(f['at'] as String).contains('T$t')) continue;
      final im = img.decodeJpg(File('$dir/${f['file']}').readAsBytesSync())!;
      final tr = <String>[];
      final got = stickSlotsIn(im, g.sticksZone, trace: tr);
      print('$t ${im.width}x${im.height} 구역 ${g.sticksZone.toList()} → ${[for (final e in got.entries) if (e.value) e.key.name]} $tr');
    }
  }
}
