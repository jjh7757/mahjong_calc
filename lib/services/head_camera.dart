import 'package:flutter/services.dart';

/// 카메라 헤드 전용 카메라(Android, `HeadCamera.kt`). 셔터(ImageCapture) 없이 미리보기 + 최대 해상도 YUV 스트림만 묶어,
/// 미리보기(`/preview`)와 촬영(`/capture`)을 모두 스트림의 최신 프레임에서 JPEG 로 만든다 → 셔터음 없음, 12MP.
/// camera 플러그인은 셋(미리보기·촬영·스트림)을 늘 같이 묶어 스트림이 1440×1080 으로 제한됐다(NOTES 32).
///
/// Android 밖(테스트·데스크톱)에서는 [start] 가 [MissingPluginException] 을 던진다.
class HeadCamera {
  static const MethodChannel _channel = MethodChannel('dev.jjh.mahjong_calc/head_camera');

  int? textureId;
  int previewWidth = 0;
  int previewHeight = 0;
  int streamWidth = 0;
  int streamHeight = 0;

  /// 센서 방향(도). 세로로 든 폰의 뒤 카메라는 보통 90 — 미리보기 텍스처를 그만큼 돌려 보여 준다.
  int sensorOrientation = 90;
  double maxZoom = 1;

  bool get isRunning => textureId != null;

  Future<void> start({double zoom = 1}) async {
    final m = await _channel.invokeMapMethod<String, dynamic>('start', {'zoom': zoom});
    if (m == null) throw StateError('start 응답 없음');
    textureId = (m['textureId'] as num).toInt();
    previewWidth = (m['previewWidth'] as num?)?.toInt() ?? 0;
    previewHeight = (m['previewHeight'] as num?)?.toInt() ?? 0;
    streamWidth = (m['streamWidth'] as num?)?.toInt() ?? 0;
    streamHeight = (m['streamHeight'] as num?)?.toInt() ?? 0;
    sensorOrientation = (m['sensorOrientation'] as num?)?.toInt() ?? 90;
    maxZoom = (m['maxZoom'] as num?)?.toDouble() ?? 1;
  }

  Future<void> stop() async {
    textureId = null;
    try {
      await _channel.invokeMethod<void>('stop');
    } on MissingPluginException {
      // 무시
    }
  }

  /// 적용된 줌 배율(기기 상한으로 잘린 값).
  Future<double> setZoom(double zoom) async {
    final z = await _channel.invokeMethod<double>('setZoom', {'zoom': zoom});
    return z ?? zoom;
  }

  /// 최신 프레임의 JPEG. [longSide] 가 프레임보다 작으면 건너뛰어 줄인다. [fresh] 면 이 호출 뒤 들어온 프레임을 기다린다.
  Future<HeadJpeg> jpeg({int? longSide, int quality = 75, bool fresh = false}) async {
    final m = await _channel.invokeMapMethod<String, dynamic>('jpeg', {
      'longSide': longSide,
      'quality': quality,
      'fresh': fresh,
    });
    if (m == null) throw StateError('jpeg 응답 없음');
    return HeadJpeg(
      m['bytes'] as Uint8List,
      width: (m['width'] as num).toInt(),
      height: (m['height'] as num).toInt(),
      frameWidth: (m['frameWidth'] as num).toInt(),
      frameHeight: (m['frameHeight'] as num).toInt(),
    );
  }
}

class HeadJpeg {
  final Uint8List bytes;
  final int width;
  final int height;

  /// 스트림 프레임(줄이기 전) 크기.
  final int frameWidth;
  final int frameHeight;
  const HeadJpeg(this.bytes, {required this.width, required this.height, required this.frameWidth, required this.frameHeight});
}
