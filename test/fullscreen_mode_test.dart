import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/ui/kiosk.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('전체 화면을 켜면 immersiveSticky, 끄면 edgeToEdge 로 바꾸고 설정을 저장·복원한다', () async {
    SharedPreferences.setMockInitialValues({});
    final modes = <Object?>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform,
        (call) async {
      if (call.method == 'SystemChrome.setEnabledSystemUIMode') modes.add(call.arguments);
      return null;
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));

    await FullscreenMode.load();
    expect(FullscreenMode.enabled.value, isFalse);
    expect(modes.last, 'SystemUiMode.edgeToEdge');

    await FullscreenMode.set(true);
    expect(modes.last, 'SystemUiMode.immersiveSticky');
    expect((await SharedPreferences.getInstance()).getBool(FullscreenMode.pref), isTrue);

    // 앱을 다시 켜면 저장된 값으로.
    FullscreenMode.enabled.value = false;
    await FullscreenMode.load();
    expect(FullscreenMode.enabled.value, isTrue);
    expect(modes.last, 'SystemUiMode.immersiveSticky');

    await FullscreenMode.set(false);
    expect(modes.last, 'SystemUiMode.edgeToEdge');
  });
}
