// ignore_for_file: avoid_print
// 시퀀스 프레임의 자리별 리치봉 띠 평균 차이(f0 기준/직전 기준)·크게 바뀐 블록 비율(f0 기준)과 강 장수를 찍는다. replay_riichi 디버그용.
//   dart run experiments/tracking/strip_diff.dart <프레임 폴더> [sticks=ymin,xmin,ymax,xmax]
import 'dart:io';

import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/table_layout.dart';

void main(List<String> args) {
  final grid = gridFrom(args);
  final re = RegExp(r'f(\d+)\.jpg$');
  final files = Directory(args[0]).listSync().whereType<File>().where((f) => re.hasMatch(f.path)).toList()
    ..sort((a, b) => int.parse(re.firstMatch(a.path)!.group(1)!).compareTo(int.parse(re.firstMatch(b.path)!.group(1)!)));
  final st = [for (final f in files) analyzeTableFrame((f.readAsBytesSync(), grid))];
  final frac = riverTileFracsOf(grid);
  for (var i = 0; i < st.length; i++) {
    String fmt(Side s) {
      final strip0 = st[i].strips[s]!.diff(st[0].strips[s]!).toStringAsFixed(3);
      final stripP = i == 0 ? '-' : st[i].strips[s]!.diff(st[i - 1].strips[s]!).toStringAsFixed(3);
      final ch0 = st[i].strips[s]!.changedFrac(st[0].strips[s]!).toStringAsFixed(2);
      final tiles = (st[i].rivers[s]!.whiteFrac / frac[s]!).toStringAsFixed(1);
      return '${s.name} 띠 $strip0/$stripP 바뀐칸 $ch0 강 $tiles';
    }

    print('f$i  ${Side.values.map(fmt).join(' | ')}');
  }
}

GridZones gridFrom(List<String> args) {
  final a = args.where((x) => x.startsWith('sticks=')).firstOrNull;
  if (a == null) return GridZones.initial;
  final v = a.substring(7).split(',').map(int.parse).toList();
  return GridZones.initial.copyWith(sticks: NormBox(v[0], v[1], v[2], v[3]));
}
