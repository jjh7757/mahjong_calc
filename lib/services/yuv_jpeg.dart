import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// 카메라 미리보기 프레임(YUV420) 한 장. `compute()` 로 isolate 에 넘길 수 있게 바이트만 든다.
///
/// 평면 3개(Y·U·V, 반평면이면 U·V 의 pixelStride 가 2) 또는 2개(NV21: Y + VU 섞임)를 받는다.
class YuvFrame {
  final int width;
  final int height;
  final List<Uint8List> planes;
  final List<int> rowStrides;

  /// 평면마다 한 픽셀이 차지하는 바이트. 모르면 1.
  final List<int> pixelStrides;

  const YuvFrame({
    required this.width,
    required this.height,
    required this.planes,
    required this.rowStrides,
    required this.pixelStrides,
  });
}

/// `compute()` 용: (프레임, 긴 변) → JPEG.
Uint8List yuvFrameToJpegSized((YuvFrame, int) args) => yuvFrameToJpeg(args.$1, maxSide: args.$2);

/// 미리보기 프레임 → 긴 변 [maxSide] 이하의 작은 JPEG. 변환하면서 바로 건너뛰어(step) 줄이므로 빠르다.
/// 카메라 헤드가 `/preview` 로 조작 기기(테이블 화면 배경)에 보낸다. `compute(yuvFrameToJpeg, frame)` 로 쓴다.
Uint8List yuvFrameToJpeg(YuvFrame f, {int maxSide = 960, int quality = 75}) {
  final long = f.width > f.height ? f.width : f.height;
  final step = long <= maxSide ? 1 : (long / maxSide).ceil();
  final ow = f.width ~/ step;
  final oh = f.height ~/ step;
  final out = img.Image(width: ow, height: oh, numChannels: 3);

  final y = f.planes[0];
  final yRs = f.rowStrides[0];
  final yPs = f.pixelStrides[0];
  final twoPlanes = f.planes.length < 3;
  final u = f.planes[1];
  final v = twoPlanes ? f.planes[1] : f.planes[2];
  final uvRs = f.rowStrides[1];
  final uvPs = twoPlanes ? 2 : f.pixelStrides[1];
  // NV21 은 V 가 먼저, U 가 그다음.
  final uOff = twoPlanes ? 1 : 0;
  final vOff = 0;

  for (var oy = 0; oy < oh; oy++) {
    final sy = oy * step;
    final yRow = sy * yRs;
    final uvRow = (sy >> 1) * uvRs;
    for (var ox = 0; ox < ow; ox++) {
      final sx = ox * step;
      final yy = y[yRow + sx * yPs];
      final uvIdx = uvRow + (sx >> 1) * uvPs;
      final uu = u[uvIdx + uOff] - 128;
      final vv = v[uvIdx + vOff] - 128;
      final r = (yy + 1.402 * vv).round();
      final g = (yy - 0.344 * uu - 0.714 * vv).round();
      final b = (yy + 1.772 * uu).round();
      out.setPixelRgb(ox, oy, r.clamp(0, 255), g.clamp(0, 255), b.clamp(0, 255));
    }
  }
  return Uint8List.fromList(img.encodeJpg(out, quality: quality));
}
