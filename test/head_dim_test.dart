import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/ui/mount/camera_head_screen.dart';

void main() {
  final t0 = DateTime(2026, 11, 12, 17);
  bool dim({
    bool enabled = true,
    bool cameraReady = true,
    bool recording = false,
    int touchAgoS = 60,
    int? clientAgoS = 2,
  }) =>
      CameraHeadScreenStateForTest.shouldDim(
        enabled: enabled,
        cameraReady: cameraReady,
        recording: recording,
        now: t0,
        lastTouchAt: t0.subtract(Duration(seconds: touchAgoS)),
        lastClientAt: clientAgoS == null ? null : t0.subtract(Duration(seconds: clientAgoS)),
      );

  test('조작 기기가 붙어 있고 30초 안 만지면 어둡게', () {
    expect(dim(), isTrue);
  });

  test('최근에 만졌으면 밝게', () {
    expect(dim(touchAgoS: 10), isFalse);
  });

  test('연결이 끊기면(요청 15초 넘게 없음) 밝게 — QR 을 보여야 한다', () {
    expect(dim(clientAgoS: 20), isFalse);
    expect(dim(clientAgoS: null), isFalse);
  });

  test('연결이 없어도 녹화 중이면 어둡게', () {
    expect(dim(clientAgoS: null, recording: true), isTrue);
  });

  test('끄거나 카메라가 안 돌면 밝게', () {
    expect(dim(enabled: false), isFalse);
    expect(dim(cameraReady: false), isFalse);
  });
}
