// ignore_for_file: avoid_print
// 크롭 292장에서 판정을 통과한 덩어리의 길이/두께 비 분포(정답 자리 / 그 밖) — ratioMax 정하기용.
import 'dart:io';

import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/stick_slots.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main() {
  final files = Directory('experiments/visit_20261107/captures')
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => RegExp(r'_track[\\/]sticks_\d+\.json$').hasMatch(f.path));
  final ratios = <double>[];
  for (final js in files) {
    final jpg = File(js.path.replaceAll('.json', '.jpg'));
    if (!jpg.existsSync()) continue;
    final im = img.decodeJpg(jpg.readAsBytesSync())!;
    final tr = <String>[];
    stickSlotsIn(im, const NormBox(0, 0, 1000, 1000), trace: tr);
    for (final t in tr) {
      final m = RegExp(r'^(\d+)x(\d+)').firstMatch(t)!;
      final a = int.parse(m[1]!), b = int.parse(m[2]!);
      final l = a > b ? a : b, s = a > b ? b : a;
      ratios.add(l / s);
    }
  }
  ratios.sort();
  print('파일 ${files.length}');
  print('덩어리 ${ratios.length}개, 비 ≥ 3.5: ${[for (final r in ratios) if (r >= 3.5) r.toStringAsFixed(1)]}');
}
