import 'package:flutter/services.dart';

/// 화면 꺼짐 방지. Android 쪽(MainActivity)이 FLAG_KEEP_SCREEN_ON 을 켜고 끈다.
/// 다른 플랫폼·테스트에서는 조용히 아무 일도 하지 않는다.
class ScreenWake {
  static const MethodChannel _channel = MethodChannel('dev.jjh.mahjong_calc/screen');

  static Future<void> keepOn(bool on) async {
    try {
      await _channel.invokeMethod<void>('keepOn', on);
    } on MissingPluginException {
      // 무시
    }
  }
}
