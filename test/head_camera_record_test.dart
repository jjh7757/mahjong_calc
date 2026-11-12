import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/services/head_camera.dart';

/// 헤드 녹화 모드(시험용)의 Dart 쪽: 채널 인자·상태 파싱·플러그인 없음 처리. 네이티브(HeadCamera.kt)는 흉내 낸다.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('dev.jjh.mahjong_calc/head_camera');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  group('HeadRecordStatus.fromMap', () {
    test('네이티브 맵(Long·Double·null 섞임)을 읽는다', () {
      final s = HeadRecordStatus.fromMap({
        'recording': true,
        'dir': '/storage/emulated/0/Android/data/x/files/rec/rec_20261112_120000',
        'saved': 1234,
        'dropped': 5,
        'bytes': 456789012,
        'streamFps': 14.93,
        'streamFpsAvg': 15,
        'savedFps': 9.8,
        'freeBytes': 50 * (1 << 30),
        'stopReason': null,
        'stopDetail': null,
      });
      expect(s.supported, isTrue);
      expect(s.recording, isTrue);
      expect(s.dir, endsWith('rec_20261112_120000'));
      expect(s.saved, 1234);
      expect(s.dropped, 5);
      expect(s.bytes, 456789012);
      expect(s.streamFps, 14.93);
      expect(s.streamFpsAvg, 15.0); // int 로 와도 double
      expect(s.savedFps, 9.8);
      expect(HeadRecordStatus.gb(s.freeBytes), '50.0GB');
      expect(s.stoppedBySelf, isFalse);
      expect(s.stopMessage, isNull);
    });

    test('녹화한 적 없으면 스트림 속도·남은 용량만 있고 나머지는 기본값', () {
      final s = HeadRecordStatus.fromMap({'recording': false, 'streamFps': 0.0, 'streamFpsAvg': 0.0, 'freeBytes': 123});
      expect(s.recording, isFalse);
      expect(s.dir, isNull);
      expect(s.saved, 0);
      expect(s.dropped, 0);
      expect(s.savedFps, 0);
      expect(s.freeBytes, 123);
      expect(s.stopReason, isNull);
      expect(s.stoppedBySelf, isFalse);
    });

    test('null 맵이면 꺼진 기본 상태(남은 용량 모름 -1)', () {
      final s = HeadRecordStatus.fromMap(null);
      expect(s.supported, isTrue);
      expect(s.recording, isFalse);
      expect(s.freeBytes, -1);
    });

    test('멈춘 까닭: 사용자가 끈 것은 메시지 없음, 용량 부족·오류·카메라 정지는 문장으로', () {
      HeadRecordStatus stopped(String reason, [String? detail]) =>
          HeadRecordStatus.fromMap({'recording': false, 'saved': 10, 'stopReason': reason, 'stopDetail': detail});
      expect(stopped('user').stoppedBySelf, isFalse);
      expect(stopped('user').stopMessage, isNull);
      expect(stopped('low_storage', '남은 용량 1.9GB').stopMessage, '남은 용량이 2GB 아래라 스스로 멈췄습니다: 남은 용량 1.9GB');
      expect(stopped('camera_stop').stopMessage, '카메라가 꺼져 멈췄습니다');
      expect(stopped('error', 'java.io.IOException: x').stopMessage, startsWith('저장 중 오류로 멈췄습니다: '));
      expect(stopped('weird').stopMessage, '멈췄습니다(weird)');
      // 녹화 중이면 지난 세션의 까닭이 남아 있어도 메시지 없음.
      final on = HeadRecordStatus.fromMap({'recording': true, 'stopReason': 'low_storage'});
      expect(on.stoppedBySelf, isFalse);
      expect(on.stopMessage, isNull);
    });

    test('gb 는 1024³ 기준 소수 한 자리', () {
      expect(HeadRecordStatus.gb(0), '0.0GB');
      expect(HeadRecordStatus.gb(2 * (1 << 30)), '2.0GB');
      expect(HeadRecordStatus.gb(1610612736), '1.5GB');
    });
  });

  group('HeadCamera 녹화 채널', () {
    test('recordStart 는 fps·quality 를 넘기고 상태를 돌려받는다(기본 10·85)', () async {
      final calls = <MethodCall>[];
      messenger.setMockMethodCallHandler(channel, (call) async {
        calls.add(call);
        return <String, Object?>{'recording': true, 'dir': '/d', 'saved': 0, 'streamFps': 12.5, 'freeBytes': 9};
      });
      final cam = HeadCamera();
      final s = await cam.recordStart();
      expect(calls.single.method, 'recordStart');
      expect(calls.single.arguments, {'fps': 10, 'quality': 85});
      expect(s.recording, isTrue);
      expect(s.dir, '/d');
      expect(s.streamFps, 12.5);

      await cam.recordStart(fps: 5, quality: 90);
      expect(calls.last.arguments, {'fps': 5, 'quality': 90});
    });

    test('recordStop·recordStatus 는 인자 없이 부른다', () async {
      final calls = <MethodCall>[];
      messenger.setMockMethodCallHandler(channel, (call) async {
        calls.add(call);
        return <String, Object?>{'recording': false, 'saved': 300, 'dropped': 2, 'stopReason': 'user'};
      });
      final cam = HeadCamera();
      final stop = await cam.recordStop();
      final st = await cam.recordStatus();
      expect(calls.map((c) => c.method), ['recordStop', 'recordStatus']);
      expect(calls.every((c) => c.arguments == null), isTrue);
      expect(stop.saved, 300);
      expect(stop.dropped, 2);
      expect(st.recording, isFalse);
      expect(st.stopMessage, isNull);
    });

    test('네이티브가 실패하면(카메라 안 돎·용량 부족) PlatformException 이 그대로 올라온다', () async {
      messenger.setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(code: 'HEAD', message: '카메라가 돌고 있지 않아 녹화를 시작할 수 없습니다');
      });
      await expectLater(
        HeadCamera().recordStart(),
        throwsA(isA<PlatformException>().having((e) => e.message, 'message', contains('카메라가 돌고 있지 않아'))),
      );
    });

    test('플러그인이 없으면(Android 밖) 세 메서드 모두 예외 없이 unsupported', () async {
      // 흉내 처리기를 두지 않으면 MissingPluginException 이 난다.
      final cam = HeadCamera();
      for (final s in [await cam.recordStart(), await cam.recordStop(), await cam.recordStatus()]) {
        expect(s.supported, isFalse);
        expect(s.recording, isFalse);
        expect(s.stopMessage, isNull);
      }
    });

    test('예전 네이티브(녹화 메서드 없음, notImplemented)도 unsupported', () async {
      messenger.setMockMethodCallHandler(channel, (call) async {
        throw MissingPluginException();
      });
      expect((await HeadCamera().recordStatus()).supported, isFalse);
    });
  });
}
