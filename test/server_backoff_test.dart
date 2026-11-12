import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mahjong_calc/services/on_device_reader.dart';
import 'package:mahjong_calc/services/recognizer_client.dart';
import 'package:mahjong_calc/services/server_backoff.dart';

void main() {
  final t0 = DateTime(2026, 11, 14, 14);

  test('연결 실패면 정한 시간 동안 쉬고, 지나면 다시 부른다', () {
    final b = ServerBackoff(rest: const Duration(minutes: 2));
    expect(b.ready(t0), isTrue);
    b.failed(const RecognizerException('서버에 연결할 수 없습니다. 네트워크를 확인하세요.'), t0);
    expect(b.ready(t0.add(const Duration(seconds: 30))), isFalse);
    expect(b.ready(t0.add(const Duration(minutes: 2))), isTrue);
  });

  test('시간 초과도 쉰다', () {
    final b = ServerBackoff();
    b.failed(const RecognizerException('응답이 없습니다(10초). 다시 시도하세요.'), t0);
    expect(b.ready(t0.add(const Duration(seconds: 1))), isFalse);
  });

  test('서버가 답한 오류(키·사진)는 쉬지 않는다', () {
    final b = ServerBackoff();
    b.failed(const RecognizerException('API 키가 맞지 않습니다.'), t0);
    expect(b.ready(t0), isTrue);
  });

  test('성공하면 쉼이 풀린다', () {
    final b = ServerBackoff();
    b.failed(const RecognizerException('서버에 연결할 수 없습니다. 네트워크를 확인하세요.'), t0);
    b.succeeded();
    expect(b.ready(t0), isTrue);
  });

  group('자체 판독(이 기기) 모드', () {
    tearDown(() {
      OnDeviceReader.enabled = false;
      OnDeviceReader.debugSupported = null;
    });

    Future<(int, Object?)> call() async {
      var sent = 0;
      final c = RecognizerClient(apiKey: 'k', httpClient: MockClient((_) async {
        sent++;
        return http.Response('{"sticks": {}}', 200);
      }));
      Object? err;
      try {
        await c.observe('sticks', Uint8List(4));
      } catch (e) {
        err = e;
      }
      return (sent, err);
    }

    test('켜면 서버에 요청을 보내지 않고 바로 실패한다', () async {
      OnDeviceReader.debugSupported = true;
      OnDeviceReader.enabled = true;
      final (sent, err) = await call();
      expect(sent, 0);
      expect('$err', contains(RecognizerClient.serverBlocked));
    });

    test('끄면 서버를 부른다', () async {
      OnDeviceReader.debugSupported = true;
      final (sent, err) = await call();
      expect(sent, 1);
      expect(err, isNull);
    });
  });
}
