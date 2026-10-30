import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/services/volume_keys.dart';

/// 볼륨키 핸들러가 겹친 화면을 쌓아 관리한다(2026-10-30 점검).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const ch = MethodChannel('dev.jjh.mahjong_calc/volume');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final captures = <bool>[];
  setUp(() {
    captures.clear();
    messenger.setMockMethodCallHandler(ch, (c) async {
      if (c.method == 'setCapture') captures.add(c.arguments as bool);
      return null;
    });
  });
  tearDown(() async {
    await VolumeKeys.stop();
    messenger.setMockMethodCallHandler(ch, null);
  });
  Future<void> press() =>
      messenger.handlePlatformMessage(ch.name, ch.codec.encodeMethodCall(const MethodCall('volume')), (_) {});

  test('화면이 둘 겹치면 맨 위가 받고, 위가 닫히면 아래가 다시 받는다. 마지막이 닫힐 때만 setCapture 를 끈다', () async {
    var a = 0, b = 0;
    void onA() => a++;
    void onB() => b++;
    await VolumeKeys.listen(onA);
    await press();
    expect(a, 1);

    await VolumeKeys.listen(onB);
    await press();
    expect((a, b), (1, 1));

    await VolumeKeys.stop(onB);
    await press();
    expect((a, b), (2, 1), reason: '위 화면이 닫히면 아래 화면이 다시 받는다');
    expect(captures, [true], reason: '아직 켜져 있어야 한다');

    await VolumeKeys.stop(onA);
    expect(captures, [true, false]);
    await press();
    expect(a, 2);
  });
}
