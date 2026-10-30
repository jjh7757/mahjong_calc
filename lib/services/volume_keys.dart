import 'package:flutter/services.dart';

/// 볼륨키를 촬영 버튼으로 받는다. Android 쪽(MainActivity)이 setCapture 가 켜진 동안만 키를 가로채
/// `volume` 호출을 보낸다. Android 가 아니거나 채널이 없으면 조용히 아무 일도 하지 않는다.
///
/// 화면이 겹칠 수 있다(홈 테이블 화면 위에 "테이블 전체 사진" 테이블 화면): 등록한 순서대로 쌓아 맨 위가 받고, 위가
/// 해제되면 아래가 다시 받는다. 마지막 하나가 해제될 때만 setCapture 를 끈다(2026-10-30 점검: 전엔 위 화면이 닫히며
/// 홈 화면의 볼륨키까지 죽였다).
class VolumeKeys {
  static const MethodChannel _channel = MethodChannel('dev.jjh.mahjong_calc/volume');
  static final List<VoidCallback> _owners = [];

  static Future<void> listen(VoidCallback onPress) async {
    _owners.remove(onPress);
    _owners.add(onPress);
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'volume' && _owners.isNotEmpty) _owners.last();
    });
    if (_owners.length > 1) return;
    try {
      await _channel.invokeMethod<void>('setCapture', true);
    } on MissingPluginException {
      // 테스트·다른 플랫폼
    }
  }

  /// [onPress] 를 뺀다(없으면 전부). 남은 것이 있으면 그것이 계속 받는다.
  static Future<void> stop([VoidCallback? onPress]) async {
    if (onPress == null) {
      _owners.clear();
    } else {
      _owners.remove(onPress);
    }
    if (_owners.isNotEmpty) return;
    _channel.setMethodCallHandler(null);
    try {
      await _channel.invokeMethod<void>('setCapture', false);
    } on MissingPluginException {
      // 무시
    }
  }
}
