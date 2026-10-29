// 펴기 전·후 구역 크롭을 같은 사진에서 뽑아 저장한다(펴서 읽을 때 C 도라·D 눕힌 6m 이 깨진 원인 보기, NOTES 37).
//   flutter test tool/rect_crops_test.dart   → experiments/rectify/results/crops/<사진>_<plain|rect>_<구역>.jpg
// 앱과 같은 코드: DirectShotImage(원본 한 번 디코딩) → rectify() → 같은 CropSpec. 격자는 read_grid_timing_test 와 같다.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:mahjong_calc/table/rectify.dart';
import 'package:mahjong_calc/table/shot_image.dart';
import 'package:mahjong_calc/table/table_layout.dart';

const _photos = 'experiments/field_20261024/kakao_photos';
const _out = 'experiments/rectify/results/crops';
const _cases = {
  'k15': (Side.left, GridZones(x1: 320, x2: 760, y1: 142, y2: 717)),
  'k26': (Side.left, GridZones(x1: 320, x2: 760, y1: 142, y2: 717)),
  'k12': (Side.bottom, GridZones(x1: 280, x2: 745, y1: 173, y2: 713)),
  'k16': (Side.bottom, GridZones(x1: 280, x2: 745, y1: 173, y2: 713)),
};

/// 축소본에 격자 선을 그린 전체 그림.
Uint8List _overview(Uint8List small, GridZones g) {
  final im = img.decodeJpg(small)!;
  final c = img.ColorRgb8(0, 140, 255);
  for (final x in [g.x1, g.x2]) {
    img.drawLine(im, x1: x * im.width ~/ 1000, y1: 0, x2: x * im.width ~/ 1000, y2: im.height, color: c, thickness: 3);
  }
  for (final y in [g.y1, g.y2]) {
    img.drawLine(im, x1: 0, y1: y * im.height ~/ 1000, x2: im.width, y2: y * im.height ~/ 1000, color: c, thickness: 3);
  }
  return Uint8List.fromList(img.encodeJpg(im, quality: 85));
}

void main() {
  test('crops', () async {
    Directory(_out).createSync(recursive: true);
    for (final MapEntry(key: photo, value: (side, grid)) in _cases.entries) {
      final bytes = File('$_photos/$photo.jpg').readAsBytesSync();
      for (final rect in [false, true]) {
        final shot = DirectShotImage(bytes);
        var g = grid;
        if (rect) {
          final q = await shot.rectify();
          expect(q, isNotNull, reason: '$photo 펠트');
          g = standardGrid;
        }
        final tag = '${photo}_${rect ? 'rect' : 'plain'}';
        File('$_out/${tag}_overview.jpg').writeAsBytesSync(_overview(await shot.shrink(), g));
        final crops = await shot.crop([CropSpec(g.seat(side), side: side), CropSpec(g.center), CropSpec(g.sticksZone)]);
        for (final (name, c) in [('seat', crops[0]), ('dora', crops[1]), ('sticks', crops[2])]) {
          File('$_out/${tag}_$name.jpg').writeAsBytesSync(c);
          final d = img.decodeJpg(c)!;
          // ignore: avoid_print
          print('$tag $name ${d.width}x${d.height}');
        }
      }
    }
  }, timeout: const Timeout(Duration(minutes: 5)));
}
