import 'package:flutter/services.dart';

/// 화면 꺼짐 방지·창 밝기. Android 쪽(MainActivity)이 FLAG_KEEP_SCREEN_ON 과 창 밝기를 바꾼다.
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

  /// 이 앱 창의 밝기(0~1). null 이면 시스템 밝기로 되돌린다. 폰 설정은 바꾸지 않는다.
  static Future<void> brightness(double? v) async {
    try {
      await _channel.invokeMethod<void>('brightness', v ?? -1.0);
    } on MissingPluginException {
      // 무시
    }
  }
}
