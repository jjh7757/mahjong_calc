// ignore_for_file: avoid_print
// 장면 전체 변화 검사(lib/table/scene_shift.dart) 문턱 확인: 바뀐 칸 수(0~12) 분포를 낸다.
//
//   dart run experiments/tracking/shift_check.dart <정상 시퀀스 폴더>... --base <원본 사진>...
//
// 정상 시퀀스(연속 프레임 쌍) = 장면 변화가 아니어야 함: 실제 폰 헤드 고정 프레임, 합성 게임 시퀀스(seq2: 손·버림·리치봉).
// --base 사진마다 합성 장면 변화(이동 0.5~4%, 밝기 ±5~15%, 회전 1°)를 만들어 원본과 비교 = 장면 변화여야 함.
// 격자는 GridZones.initial(거치 화면 기본).
import 'dart:io';
import 'dart:typed_data';

import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/river_change.dart';
import 'package:mahjong_calc/table/scene_shift.dart';

TableFrameStats stats(Uint8List jpeg) => analyzeTableFrame((jpeg, GridZones.initial));

final gate = SceneShiftGate();

/// "칸/모서리/밝기 강" 과 판정.
(String, bool) judge(TableFrameStats a, TableFrameStats b) {
  final hit = gate.judge(a, b);
  return ('${gate.lastChanged}/${gate.lastCorners}/${gate.lastBright}', hit);
}

Uint8List jpg(img.Image im) => Uint8List.fromList(img.encodeJpg(im, quality: 85));

/// 내용을 (dx, dy) 비율만큼 옮긴다(빈 곳은 가장자리 픽셀).
img.Image shift(img.Image src, double fx, double fy) {
  final dx = (src.width * fx).round(), dy = (src.height * fy).round();
  final out = img.Image(width: src.width, height: src.height);
  for (var y = 0; y < src.height; y++) {
    final sy = (y - dy).clamp(0, src.height - 1);
    for (var x = 0; x < src.width; x++) {
      out.setPixel(x, y, src.getPixel((x - dx).clamp(0, src.width - 1), sy));
    }
  }
  return out;
}

img.Image bright(img.Image src, double k) {
  final out = src.clone();
  for (final p in out) {
    p
      ..r = (p.r * k).clamp(0, 255)
      ..g = (p.g * k).clamp(0, 255)
      ..b = (p.b * k).clamp(0, 255);
  }
  return out;
}

img.Image rotate(img.Image src, double deg) {
  final r = img.copyRotate(src, angle: deg);
  final x = (r.width - src.width) ~/ 2, y = (r.height - src.height) ~/ 2;
  return img.copyCrop(r, x: x, y: y, width: src.width, height: src.height);
}


void main(List<String> args) {
  final bi = args.indexOf('--base');
  final seqs = bi < 0 ? args : args.sublist(0, bi);
  final bases = bi < 0 ? <String>[] : args.sublist(bi + 1);

  print('== 정상 시퀀스(장면 변화 아님): 연속 프레임 쌍의 바뀐 칸 수');
  final normal = <int>[];
  for (final dir in seqs) {
    final files = Directory(dir)
        .listSync()
        .whereType<File>()
        .where((f) => RegExp(r'f\d+\.jpg$').hasMatch(f.path))
        .toList()
      ..sort((a, b) => int.parse(RegExp(r'f(\d+)\.jpg$').firstMatch(a.path)!.group(1)!)
          .compareTo(int.parse(RegExp(r'f(\d+)\.jpg$').firstMatch(b.path)!.group(1)!)));
    TableFrameStats? prev;
    final xs = <String>[];
    for (final f in files) {
      final s = stats(f.readAsBytesSync());
      if (prev != null) {
        final (t, hit) = judge(prev, s);
        xs.add(hit ? '[$t]' : t);
        normal.add(hit ? 1 : 0);
      }
      prev = s;
    }
    print('$dir (${files.length}장): ${xs.join(' ')}');
  }
  print('정상 쌍 ${normal.length}개 중 장면 변화로 판정(헛 판정) ${normal.where((x) => x == 1).length}개   ([ ] = 판정됨, 칸/모서리/밝기 강)');

  print('\n== 합성 장면 변화(장면 변화여야 함): 원본 대비 바뀐 칸 수');
  final shifted = <int>[];
  final named = <String, List<int>>{};
  for (final path in bases) {
    final src = img.decodeJpg(File(path).readAsBytesSync())!;
    final small = img.copyResize(src, width: 1024);
    final base = stats(jpg(small));
    final cases = <String, img.Image>{
      '이동 0.5%': shift(small, 0.005, 0),
      '이동 1%': shift(small, 0.01, 0),
      '이동 2%': shift(small, 0.02, 0.01),
      '이동 4%': shift(small, 0.04, 0.02),
      '세로 2%': shift(small, 0, 0.02),
      '밝기 -5%': bright(small, 0.95),
      '밝기 -10%': bright(small, 0.9),
      '밝기 +10%': bright(small, 1.1),
      '밝기 -15%': bright(small, 0.85),
      '회전 1°': rotate(small, 1),
    };
    final row = <String>[];
    for (final e in cases.entries) {
      final (t, hit) = judge(base, stats(jpg(e.value)));
      shifted.add(hit ? 1 : 0);
      (named[e.key] ??= []).add(hit ? 1 : 0);
      row.add(hit ? '${e.key} [$t]' : '${e.key} $t');
    }
    // 같은 사진을 다시 인코딩만(잡음 기준).
    row.add('재인코딩 ${judge(base, stats(jpg(img.decodeJpg(jpg(small))!))).$1}');
    print('$path: ${row.join(' · ')}');
  }
  for (final e in named.entries) {
    print('  ${e.key}: 판정 ${e.value.where((x) => x == 1).length}/${e.value.length}');
  }
  print('합성 ${shifted.length}개 중 장면 변화로 판정 ${shifted.where((x) => x == 1).length}개');
}
