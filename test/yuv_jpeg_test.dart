import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/yuv_jpeg.dart';

/// 카메라 헤드 미리보기 프레임(YUV420) → 작은 JPEG.
void main() {
  /// 단색 프레임. [semi] 면 U·V 를 한 평면에 섞은 반평면(Android 흔한 꼴, pixelStride 2).
  YuvFrame solid(int w, int h, int y, int u, int v, {bool semi = false, bool nv21 = false}) {
    final yp = Uint8List(w * h)..fillRange(0, w * h, y);
    if (nv21) {
      final vu = Uint8List(w * h ~/ 2);
      for (var i = 0; i < vu.length; i += 2) {
        vu[i] = v;
        vu[i + 1] = u;
      }
      return YuvFrame(width: w, height: h, planes: [yp, vu], rowStrides: [w, w], pixelStrides: [1, 2]);
    }
    if (semi) {
      final uv = Uint8List(w * h ~/ 2);
      final vv = Uint8List(w * h ~/ 2);
      for (var i = 0; i < uv.length; i += 2) {
        uv[i] = u;
        uv[i + 1] = v;
        vv[i] = v;
        vv[i + 1] = u;
      }
      return YuvFrame(width: w, height: h, planes: [yp, uv, vv], rowStrides: [w, w, w], pixelStrides: [1, 2, 2]);
    }
    final up = Uint8List(w * h ~/ 4)..fillRange(0, w * h ~/ 4, u);
    final vp = Uint8List(w * h ~/ 4)..fillRange(0, w * h ~/ 4, v);
    return YuvFrame(width: w, height: h, planes: [yp, up, vp], rowStrides: [w, w ~/ 2, w ~/ 2], pixelStrides: [1, 1, 1]);
  }

  img.Pixel center(Uint8List jpeg) {
    final im = img.decodeJpg(jpeg)!;
    return im.getPixel(im.width ~/ 2, im.height ~/ 2);
  }

  test('회색 프레임은 회색 JPEG 가 되고 크기는 그대로', () {
    final jpeg = yuvFrameToJpeg(solid(64, 48, 150, 128, 128));
    final im = img.decodeJpg(jpeg)!;
    expect(im.width, 64);
    expect(im.height, 48);
    final p = center(jpeg);
    expect(p.r, closeTo(150, 6));
    expect(p.g, closeTo(150, 6));
    expect(p.b, closeTo(150, 6));
  });

  test('긴 변이 maxSide 를 넘으면 건너뛰어 줄인다', () {
    final im = img.decodeJpg(yuvFrameToJpeg(solid(640, 480, 100, 128, 128), maxSide: 320))!;
    expect(im.width, 320);
    expect(im.height, 240);
  });

  test('빨강(V 큼)은 빨갛게 — 평면 3개·반평면·NV21 모두', () {
    for (final f in [
      solid(32, 32, 100, 90, 240),
      solid(32, 32, 100, 90, 240, semi: true),
      solid(32, 32, 100, 90, 240, nv21: true),
    ]) {
      final p = center(yuvFrameToJpeg(f));
      expect(p.r, greaterThan(200));
      expect(p.g, lessThan(60));
      expect(p.b, lessThan(60));
    }
  });
}
