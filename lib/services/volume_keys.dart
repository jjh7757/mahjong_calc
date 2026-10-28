import 'package:flutter/services.dart';

/// 볼륨키를 촬영 버튼으로 받는다. Android 쪽(MainActivity)이 setCapture 가 켜진 동안만 키를 가로채
/// `volume` 호출을 보낸다. Android 가 아니거나 채널이 없으면 조용히 아무 일도 하지 않는다.
class VolumeKeys {
  static const MethodChannel _channel = MethodChannel('dev.jjh.mahjong_calc/volume');

  static Future<void> listen(VoidCallback onPress) async {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'volume') onPress();
    });
    try {
      await _channel.invokeMethod<void>('setCapture', true);
    } on MissingPluginException {
      // 테스트·다른 플랫폼
    }
  }

  static Future<void> stop() async {
    _channel.setMethodCallHandler(null);
    try {
      await _channel.invokeMethod<void>('setCapture', false);
    } on MissingPluginException {
      // 무시
    }
  }
}
