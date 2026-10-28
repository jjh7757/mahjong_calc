/// 원본 사진에서 구역을 잘라 자리에 맞게 돌린다. `image` 패키지만 쓰는 순수 Dart.
///
/// 12MP 디코딩은 1~2초 걸리므로 UI 에서는 [shrinkForLocate]·[cropMany] 를 `compute()` 로 isolate 에서 돌린다.
/// 두 함수가 각각 디코딩하므로 원본을 두 번 읽지만, 디코딩된 이미지를 isolate 사이로 옮기지 않아도 된다.
/// 서버는 긴 변을 1568px 로 줄이므로 전경은 보내지 말고, 구역별 크롭을 보내야 패가 100px 이상으로 남는다.
library;

import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'table_layout.dart';

/// 손패 크롭 패딩. 넓히면 옆자리 버림패가 들어와 화료패로 오인된다(실험 결과 4%).
const double handCropPad = 0.04;

/// 중앙 크롭 패딩.
const double centerCropPad = 0.05;

/// 왕패 크롭 패딩. 상자가 작아서 넉넉히 넓힌다.
const double wallCropPad = 0.3;

/// 울기 크롭 패딩.
const double meldCropPad = 0.15;

/// 강 크롭 패딩.
const double riverCropPad = 0.08;

/// locate 에 보낼 축소본의 긴 변.
const int locateMaxSide = 1024;

/// 잘라낼 구역 하나.
class CropSpec {
  final NormBox box;
  final Side side;
  final double pad;
  const CropSpec(this.box, {this.side = Side.bottom, this.pad = 0});

  factory CropSpec.hand(NormBox box, Side side) => CropSpec(box, side: side, pad: handCropPad);
  factory CropSpec.center(NormBox box) => CropSpec(box, pad: centerCropPad);
  factory CropSpec.wall(NormBox box) => CropSpec(box, pad: wallCropPad);

  /// 울기 묶음 하나. 상자가 작아서 넉넉히 넓히고 그 자리 방향으로 세운다.
  factory CropSpec.meld(NormBox box, Side side) => CropSpec(box, side: side, pad: meldCropPad);

  /// 강 하나. 손패처럼 그 자리 사람이 보는 방향으로 세운다(버린 순서 = 윗줄부터 왼쪽→오른쪽).
  factory CropSpec.river(NormBox box, Side side) => CropSpec(box, side: side, pad: riverCropPad);
}

class TableImage {
  final img.Image image;
  const TableImage(this.image);

  /// JPEG/PNG/WebP 바이트를 디코딩하고 EXIF 회전을 반영한다.
  factory TableImage.decode(Uint8List bytes) {
    final im = img.decodeImage(bytes);
    if (im == null) throw const FormatException('이미지를 디코딩할 수 없습니다');
    return TableImage(img.bakeOrientation(im));
  }

  int get width => image.width;
  int get height => image.height;

  /// `/v1/locate` 에 보낼 축소본. 긴 변 [maxSide].
  Uint8List shrunkJpeg({int maxSide = locateMaxSide, int quality = 90}) {
    final longest = width > height ? width : height;
    var im = image;
    if (longest > maxSide) {
      im = width >= height
          ? img.copyResize(image, width: maxSide, interpolation: img.Interpolation.average)
          : img.copyResize(image, height: maxSide, interpolation: img.Interpolation.average);
    }
    return Uint8List.fromList(img.encodeJpg(im, quality: quality));
  }

  /// 구역을 잘라 [side] 의 패가 바로 서도록 돌린 이미지. [pad] 는 상자 크기 비율.
  img.Image cropImage(NormBox box, {Side side = Side.bottom, double pad = 0}) {
    final r = box.toPixels(width, height, pad: pad);
    var out = img.copyCrop(image, x: r.x, y: r.y, width: r.width, height: r.height);
    final deg = side.uprightRotationCw;
    if (deg != 0) out = img.copyRotate(out, angle: deg, interpolation: img.Interpolation.linear);
    return out;
  }

  Uint8List cropJpeg(NormBox box, {Side side = Side.bottom, double pad = 0, int quality = 92}) =>
      Uint8List.fromList(img.encodeJpg(cropImage(box, side: side, pad: pad), quality: quality));
}

/// 원본 → locate 용 축소 JPEG. `compute()` 에 그대로 넘길 수 있다.
Uint8List shrinkForLocate(Uint8List original) => TableImage.decode(original).shrunkJpeg();

/// 원본 → 구역별 크롭 JPEG 목록(순서 유지). `compute()` 에 그대로 넘길 수 있다.
List<Uint8List> cropMany((Uint8List, List<CropSpec>) args) {
  final (original, specs) = args;
  final im = TableImage.decode(original);
  return [for (final s in specs) im.cropJpeg(s.box, side: s.side, pad: s.pad)];
}
