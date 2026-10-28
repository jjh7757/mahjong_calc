import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;
import 'package:mahjong_calc/services/camera_head.dart';

final Uint8List _jpeg = Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, 1, 2, 3, 0xFF, 0xD9]);
const String _tok = 'test-token-AbC_123';

void main() {
  group('RemoteCamera.ignoreExifRotation', () {
    test('EXIF 회전 6 을 1 로 바꿔 센서 방향(가로) 그대로 읽힌다', () {
      final im = img.Image(width: 8, height: 4);
      im.exif.imageIfd.orientation = 6;
      final jpeg = Uint8List.fromList(img.encodeJpg(im));
      expect(img.bakeOrientation(img.decodeJpg(jpeg)!).width, 4); // 그대로면 세로로 돈다

      final fixed = RemoteCamera.ignoreExifRotation(jpeg);
      expect(img.decodeJpgExif(fixed)!.imageIfd.orientation, 1);
      final baked = img.bakeOrientation(img.decodeJpg(fixed)!);
      expect([baked.width, baked.height], [8, 4]);
    });

    test('EXIF 가 없거나 JPEG 가 아니면 바이트를 그대로 둔다', () {
      expect(RemoteCamera.ignoreExifRotation(_jpeg), same(_jpeg));
      final plain = Uint8List.fromList(img.encodeJpg(img.Image(width: 4, height: 2)));
      expect(RemoteCamera.ignoreExifRotation(plain), same(plain));
    });
  });

  group('RemoteCamera.normalize', () {
    test('호스트만 적으면 http 와 기본 포트를 붙인다', () {
      expect(RemoteCamera.normalize('192.168.0.12'), 'http://192.168.0.12:8765');
      expect(RemoteCamera.normalize('  192.168.0.12  '), 'http://192.168.0.12:8765');
    });
    test('포트·스킴·끝 슬래시는 그대로 존중한다', () {
      expect(RemoteCamera.normalize('192.168.0.12:9000'), 'http://192.168.0.12:9000');
      expect(RemoteCamera.normalize('http://10.0.0.3:8765/'), 'http://10.0.0.3:8765');
      expect(RemoteCamera.normalize('https://cam.local'), 'https://cam.local:8765');
    });
    test('비면 빈 문자열', () {
      expect(RemoteCamera.normalize(''), '');
      expect(RemoteCamera.normalize('   '), '');
    });
    test('토큰 쿼리는 주소에서 빼고, 토큰으로 쓴다', () {
      expect(RemoteCamera.normalize('192.168.0.12:8765?t=abc'), 'http://192.168.0.12:8765');
      expect(RemoteCamera('192.168.0.12?t=abc').token, 'abc');
      expect(RemoteCamera('192.168.0.12?t=abc', token: 'xyz').token, 'xyz');
      expect(RemoteCamera('192.168.0.12').token, isNull);
    });
  });

  group('CameraHeadLink', () {
    test('QR 문자열 만들기·해석 라운드트립', () {
      final token = generateHeadToken();
      final qr = CameraHeadLink.qrString('192.168.50.35', 8765, token);
      expect(qr, 'mahjongcam://192.168.50.35:8765?t=$token');
      final link = CameraHeadLink.fromQr(qr)!;
      expect(link.baseUrl, 'http://192.168.50.35:8765');
      expect(link.token, token);
      // 수동 입력 경로(parse)로도 같다.
      final p = CameraHeadLink.parse(qr)!;
      expect(p.baseUrl, link.baseUrl);
      expect(p.token, token);
    });

    test('특수 문자가 든 토큰도 인코딩해 되돌린다', () {
      final qr = CameraHeadLink.qrString('10.0.0.2', 9000, 'a+b/c=d&e');
      final link = CameraHeadLink.fromQr(qr)!;
      expect(link.baseUrl, 'http://10.0.0.2:9000');
      expect(link.token, 'a+b/c=d&e');
    });

    test('fromQr 는 카메라 헤드 QR 이 아니면 null', () {
      for (final bad in [
        '',
        'hello world',
        'https://example.com',
        'http://192.168.0.5:8765?t=abc', // 스킴이 다르면 다른 QR 로 본다
        'mahjongcam://192.168.0.5:8765', // 토큰 없음
        'mahjongcam://192.168.0.5:8765?t=',
        'mahjongcam://?t=abc', // 호스트 없음
        'mahjongcam://192.168.0.5:99999?t=abc', // 포트 범위 밖
      ]) {
        expect(CameraHeadLink.fromQr(bad), isNull, reason: bad);
      }
    });

    test('parse 는 수동 입력 형태를 받는다', () {
      final a = CameraHeadLink.parse('192.168.0.5')!;
      expect(a.baseUrl, 'http://192.168.0.5:8765');
      expect(a.token, isNull);
      final b = CameraHeadLink.parse(' http://192.168.0.5:9000/?t=xyz ')!;
      expect(b.baseUrl, 'http://192.168.0.5:9000');
      expect(b.token, 'xyz');
      final c = CameraHeadLink.parse('MahjongCam://192.168.0.5:8765?t=q')!;
      expect(c.baseUrl, 'http://192.168.0.5:8765');
      expect(c.token, 'q');
    });

    test('parse 는 주소가 아니면 null', () {
      for (final bad in ['', '   ', 'hello world', 'ftp://192.168.0.5', 'http://', 'http://h:0']) {
        expect(CameraHeadLink.parse(bad), isNull, reason: bad);
      }
    });
  });

  group('토큰', () {
    test('generateHeadToken 은 16바이트 base64url(22자, 패딩 없음)', () {
      final t = generateHeadToken();
      expect(t.length, 22);
      expect(RegExp(r'^[A-Za-z0-9_-]{22}$').hasMatch(t), isTrue);
      expect(base64Url.decode('$t==').length, 16);
      expect(generateHeadToken(), isNot(t));
      // 같은 시드면 같은 토큰(난수원만 바뀐다).
      expect(generateHeadToken(Random(1)), generateHeadToken(Random(1)));
    });

    test('tokenEquals', () {
      expect(tokenEquals('abc', 'abc'), isTrue);
      expect(tokenEquals('abc', 'abd'), isFalse);
      expect(tokenEquals('abc', 'ab'), isFalse);
      expect(tokenEquals('ab', 'abc'), isFalse);
      expect(tokenEquals('', 'abc'), isFalse);
      expect(tokenEquals('', ''), isTrue);
    });
  });

  group('CameraHeadServer + RemoteCamera', () {
    late CameraHeadServer server;
    late int captures;
    late int inFlight;
    late int maxInFlight;
    Object? failWith;

    setUp(() async {
      captures = 0;
      inFlight = 0;
      maxInFlight = 0;
      failWith = null;
      server = CameraHeadServer(
        token: _tok,
        capture: () async {
          inFlight++;
          if (inFlight > maxInFlight) maxInFlight = inFlight;
          await Future<void>.delayed(const Duration(milliseconds: 20));
          inFlight--;
          final f = failWith;
          if (f != null) throw f;
          captures++;
          return _jpeg;
        },
      );
      await server.start(port: 0, address: InternetAddress.loopbackIPv4);
    });

    tearDown(() => server.stop());

    String url() => 'http://127.0.0.1:${server.port}';

    test('/capture 는 image/jpeg 로 사진을 주고 횟수를 센다', () async {
      final cam = RemoteCamera(url(), token: _tok);
      final shot = await cam.capture();
      expect(shot.bytes, _jpeg);
      expect(shot.zoom, isNull); // 헤더를 안 붙이는 서버
      expect(server.captureCount, 1);
      expect(server.lastCaptureAt, isNotNull);
      final st = await cam.status();
      expect(st['ok'], true);
      expect(st['captures'], 1);
      cam.close();
    });

    test('동시에 여러 번 부르면 한 번에 하나씩 찍는다', () async {
      final cam = RemoteCamera(url(), token: _tok);
      final results = await Future.wait([cam.capture(), cam.capture(), cam.capture()]);
      expect(results.length, 3);
      expect(captures, 3);
      expect(maxInFlight, 1);
      cam.close();
    });

    test('카메라가 준비되지 않았으면 503 과 메시지, 다음 촬영은 계속된다', () async {
      failWith = StateError('카메라 헤드의 카메라가 준비되지 않았습니다');
      final cam = RemoteCamera(url(), token: _tok);
      await expectLater(
        cam.capture(),
        throwsA(isA<RemoteCameraException>().having(
          (e) => e.message,
          'message',
          contains('준비되지 않았습니다'),
        )),
      );
      expect(server.lastError, contains('준비되지'));
      failWith = null;
      expect((await cam.capture()).bytes, _jpeg);
      expect(server.lastError, isNull);
      cam.close();
    });

    test('촬영 조건 헤더(X-Zoom)를 RemoteShot.zoom 으로 받는다', () async {
      final head = CameraHeadServer(
        token: _tok,
        capture: () async => _jpeg,
        headers: () => {'X-Zoom': '2.00'},
      );
      await head.start(port: 0, address: InternetAddress.loopbackIPv4);
      final cam = RemoteCamera('http://127.0.0.1:${head.port}', token: _tok);
      final shot = await cam.capture();
      expect(shot.zoom, 2.0);
      expect(shot.bytes, _jpeg);
      cam.close();
      await head.stop();
    });

    test('모르는 경로는 404, GET 이 아니면 405', () async {
      final r404 = await http.get(Uri.parse('${url()}/nope'));
      expect(r404.statusCode, 404);
      final r405 = await http.post(Uri.parse('${url()}/capture'));
      expect(r405.statusCode, 405);
    });

    test('status 는 / 로도 받는다', () async {
      final r = await http.get(Uri.parse('${url()}/'));
      expect(r.statusCode, 200);
      expect(r.headers['content-type'], contains('application/json'));
    });

    test('토큰이 없거나 틀리면 /capture 는 401 이고 찍지 않는다', () async {
      final none = await http.get(Uri.parse('${url()}/capture'));
      expect(none.statusCode, 401);
      final wrong = await http.get(
        Uri.parse('${url()}/capture'),
        headers: {'X-Head-Token': 'wrong'},
      );
      expect(wrong.statusCode, 401);
      final wrongQuery = await http.get(Uri.parse('${url()}/capture?t=wrong'));
      expect(wrongQuery.statusCode, 401);
      expect(captures, 0);
      expect(server.captureCount, 0);
    });

    test('맞는 토큰은 헤더나 쿼리 t 로 보낼 수 있다', () async {
      final byHeader = await http.get(
        Uri.parse('${url()}/capture'),
        headers: {'X-Head-Token': _tok},
      );
      expect(byHeader.statusCode, 200);
      expect(byHeader.bodyBytes, _jpeg);
      final byQuery = await http.get(Uri.parse('${url()}/capture?t=$_tok'));
      expect(byQuery.statusCode, 200);
      expect(server.captureCount, 2);
    });

    test('/status 는 토큰 없이 ok 만, 맞는 토큰이면 촬영 수까지', () async {
      final open = jsonDecode((await http.get(Uri.parse('${url()}/status'))).body);
      expect(open, {'ok': true, 'auth': false});
      final authed = jsonDecode((await http.get(
        Uri.parse('${url()}/status'),
        headers: {'X-Head-Token': _tok},
      ))
          .body);
      expect(authed['auth'], true);
      expect(authed['captures'], 0);
    });

    test('RemoteCamera 는 토큰이 틀리면 QR 다시 스캔 안내(unauthorized)', () async {
      final cam = RemoteCamera(url(), token: 'wrong');
      final rescan = isA<RemoteCameraException>()
          .having((e) => e.unauthorized, 'unauthorized', isTrue)
          .having((e) => e.message, 'message', contains('QR 을 다시 스캔'));
      await expectLater(cam.capture(), throwsA(rescan));
      await expectLater(cam.status(), throwsA(rescan));
      cam.close();
      final noToken = RemoteCamera(url());
      await expectLater(noToken.capture(), throwsA(rescan));
      noToken.close();
    });

    test('토큰을 바꾸면 예전 토큰은 거절된다(재발급)', () async {
      final cam = RemoteCamera(url(), token: _tok);
      expect((await cam.capture()).bytes, _jpeg);
      server.token = generateHeadToken();
      await expectLater(
        cam.capture(),
        throwsA(isA<RemoteCameraException>().having((e) => e.unauthorized, 'unauthorized', isTrue)),
      );
      final fresh = RemoteCamera(url(), token: server.token);
      expect((await fresh.capture()).bytes, _jpeg);
      cam.close();
      fresh.close();
    });

    test('QR 문자열 그대로 RemoteCamera 를 만들면 찍힌다', () async {
      final link = CameraHeadLink.fromQr(
        CameraHeadLink.qrString('127.0.0.1', server.port, _tok),
      )!;
      final cam = RemoteCamera(link.baseUrl, token: link.token);
      expect((await cam.capture()).bytes, _jpeg);
      cam.close();
    });

    test('꺼진 주소면 연결 오류 메시지', () async {
      await server.stop();
      final cam = RemoteCamera(url(), token: _tok, timeout: const Duration(seconds: 3));
      await expectLater(
        cam.capture(),
        throwsA(isA<RemoteCameraException>().having(
          (e) => e.message,
          'message',
          contains('연결할 수 없습니다'),
        )),
      );
      cam.close();
    });

    test('응답이 느리면 시간 초과 메시지', () async {
      final slow = CameraHeadServer(
        token: _tok,
        capture: () async {
          await Future<void>.delayed(const Duration(seconds: 2));
          return _jpeg;
        },
      );
      await slow.start(port: 0, address: InternetAddress.loopbackIPv4);
      final cam = RemoteCamera('http://127.0.0.1:${slow.port}', token: _tok, timeout: const Duration(milliseconds: 200));
      await expectLater(
        cam.capture(),
        throwsA(isA<RemoteCameraException>().having(
          (e) => e.message,
          'message',
          contains('응답하지 않습니다'),
        )),
      );
      cam.close();
      await slow.stop();
    });
  });

  test('localIPv4Addresses 는 루프백을 빼고 돌려준다', () async {
    final a = await localIPv4Addresses();
    expect(a, isNot(contains('127.0.0.1')));
  });

  group('/preview (테이블 화면 배경)', () {
    test('토큰이 맞으면 작은 JPEG, 촬영 수는 안 세고 previewCount 만 는다', () async {
      var asked = 0;
      final asks = <int?>[];
      final head = CameraHeadServer(
        token: _tok,
        capture: () async => _jpeg,
        preview: (w) async {
          asked++;
          asks.add(w);
          return PreviewFrame(_jpeg, frameWidth: 1920, frameHeight: 1080);
        },
      );
      await head.start(port: 0, address: InternetAddress.loopbackIPv4);
      final cam = RemoteCamera('http://127.0.0.1:${head.port}', token: _tok);
      final p = await cam.preview();
      expect(p.bytes, _jpeg);
      expect(p.frameWidth, 1920);
      expect(p.frameLongSide, 1920);
      expect(asked, 1);
      // 긴 변을 요청하면 헤드에 그대로 전달된다(터무니없는 값은 240~8192 로 자른다).
      await cam.preview(longSide: 2000);
      await cam.preview(longSide: 99999);
      expect(asks, [null, 2000, 8192]);
      expect(head.previewCount, 3);
      expect(head.captureCount, 0);
      final none = await http.get(Uri.parse('http://127.0.0.1:${head.port}/preview'));
      expect(none.statusCode, 401);
      expect(asked, 3);
      cam.close();
      await head.stop();
    });

    test('헤드에 미리보기가 없으면(예전 앱) 404 → unsupported 로 더 묻지 않게 한다', () async {
      final head = CameraHeadServer(token: _tok, capture: () async => _jpeg);
      await head.start(port: 0, address: InternetAddress.loopbackIPv4);
      final cam = RemoteCamera('http://127.0.0.1:${head.port}', token: _tok);
      await expectLater(
        cam.preview(),
        throwsA(isA<RemoteCameraException>().having((e) => e.unsupported, 'unsupported', isTrue)),
      );
      cam.close();
      await head.stop();
    });
  });
}
