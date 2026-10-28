import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/table/cropper.dart';
import 'package:mahjong_calc/table/shot_image.dart';
import 'package:mahjong_calc/table/table_layout.dart';

/// 긴 변이 축소 기준(1024)보다 큰 무늬 있는 사진.
Uint8List _photo() {
  final im = img.Image(width: 1600, height: 1200);
  for (var y = 0; y < im.height; y++) {
    for (var x = 0; x < im.width; x++) {
      im.setPixelRgb(x, y, (x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256);
    }
  }
  return Uint8List.fromList(img.encodeJpg(im, quality: 90));
}

final _specs = [
  CropSpec(const NormBox(800, 250, 1000, 1000), side: Side.bottom),
  CropSpec(const NormBox(0, 750, 800, 1000), side: Side.right),
  CropSpec(const NormBox(250, 300, 450, 700), side: Side.top),
  CropSpec(const NormBox(300, 300, 700, 700), side: Side.left, pad: 0.1),
];

void main() {
  final photo = _photo();

  test('같은 스레드: 예전 함수와 바이트까지 같은 축소본·크롭', () async {
    final shot = DirectShotImage(photo);
    expect(await shot.shrink(), shrinkForLocate(photo));
    expect(await shot.crop(_specs), cropMany((photo, _specs)));
    await shot.close();
  });

  test('isolate: 한 번 디코딩으로 축소본과 크롭 두 번, 예전 함수와 같은 바이트', () async {
    final shot = await IsolateShotImage.open(photo);
    try {
      expect(await shot.shrink(), shrinkForLocate(photo));
      // 자리 먼저, 나머지 나중 — 나눠 잘라도 같은 바이트
      final first = await shot.crop(_specs.sublist(0, 1));
      final rest = await shot.crop(_specs.sublist(1));
      expect([...first, ...rest], cropMany((photo, _specs)));
    } finally {
      await shot.close();
    }
    await shot.close(); // 두 번 닫아도 된다
    expect(shot.shrink, throwsStateError);
  });

  test('isolate: 디코딩할 수 없는 사진이면 요청이 오류로 끝난다', () async {
    final shot = await IsolateShotImage.open(Uint8List.fromList([1, 2, 3]));
    try {
      await expectLater(shot.shrink(), throwsFormatException);
    } finally {
      await shot.close();
    }
  });
}
