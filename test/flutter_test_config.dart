import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/services/announcer.dart';

/// 모든 테스트 공통: 음성 파일은 없는 것으로(플레이어 플러그인도 답이 안 온다),
/// 기기 TTS(결과 음성) 대신 바로 다 읽은 것으로 답하는 가짜 채널.
/// 테스트에는 플랫폼이 없어 실제 호출은 답이 오지 않고, 그러면 결과 화면 연출이 멈춘다.
/// 읽은 순서를 보는 테스트(announcer_test)는 자기 가짜로 바꿔 끼운다.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  setUp(() {
    Announcer.playClip = (_) async => false;
    // 위젯 테스트만(바인딩이 없는 순수 테스트에 바인딩을 만들면 실제 HTTP 가 막힌다).
    final TestDefaultBinaryMessengerBinding binding;
    try {
      binding = TestDefaultBinaryMessengerBinding.instance;
    } on FlutterError {
      return;
    }
    binding.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('flutter_tts'), (_) async => 1);
  });
  await testMain();
}
