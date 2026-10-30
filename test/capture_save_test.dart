import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/services/capture_log.dart';

const _files = MethodChannel('dev.jjh.mahjong_calc/files');

/// 저장 채널에 넘기는 값. track.json 처럼 저장할 때마다 전체를 다시 쓰는 파일만 덮어쓴다(2026-10-30: 사본이 쌓였다).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('덮어쓰기는 요청한 파일에만 켜고, 기본은 새 파일', () async {
    final calls = <Map<Object?, Object?>>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_files, (call) async {
      calls.add(call.arguments as Map<Object?, Object?>);
      return 'content://x';
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_files, null));
    final bytes = Uint8List.fromList([1, 2, 3]);
    expect(await CaptureLog.saveFile('Download/mahjong_calc/x_track', 'track.json', bytes, 'application/json', overwrite: true), isTrue);
    expect(await CaptureLog.saveFile('Download/mahjong_calc/x', 'shot.jpg', bytes, 'image/jpeg'), isTrue);
    expect(calls.map((c) => c['overwrite']), [true, false]);
    expect(calls.first['name'], 'track.json');
  });
}
