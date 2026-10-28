// 데스크톱(Windows 등) 실제 앱 안에서 촬영 기록이 사용자 다운로드 폴더에 써지는지 본다(Android 채널 없음 → 파일).
//   flutter test integration_test/desktop_capture_log_test.dart -d windows
// 다운로드\mahjong_calc\_desktop_check 에 썼다가 지운다.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/services/capture_log.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  test('채널이 없으면 다운로드 폴더에 쓴다', () async {
    final home = Platform.environment[Platform.isWindows ? 'USERPROFILE' : 'HOME']!;
    // 기기에서 도는 앱에 FLUTTER_TEST 가 있으면 기본 폴더를 막으므로, 같은 경로를 직접 준다.
    CaptureLog.desktopRootOverride = CaptureLog.desktopBase ?? '$home/Downloads';
    final dir = Directory('$home/Downloads/mahjong_calc/_desktop_check');
    addTearDown(() {
      CaptureLog.desktopRootOverride = null;
      if (dir.existsSync()) dir.deleteSync(recursive: true);
    });
    expect(await CaptureLog.saveFile('Download/mahjong_calc/_desktop_check', 'a.bin', Uint8List.fromList([7, 8]), 'x'),
        isTrue);
    expect(File('${dir.path}/a.bin').readAsBytesSync(), [7, 8]);
    // ignore: avoid_print
    print('desktopBase=${CaptureLog.desktopBase} file=${dir.path}/a.bin');
  });
}
