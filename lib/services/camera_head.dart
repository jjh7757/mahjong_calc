import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

/// 카메라 헤드(테이블 위에 고정해 사진만 찍는 기기)와 조작 기기(태블릿·노트북) 사이의 작은 HTTP 규약.
/// 같은 Wi-Fi 안에서만 쓴다. 토큰 하나로 인증한다(헤더 `X-Head-Token` 또는 쿼리 `t`).
/// 주소와 토큰은 카메라 헤드 화면의 QR([CameraHeadLink])로 조작 기기에 넘긴다.
///
/// - `GET /capture` → `image/jpeg` 원본 한 장. 토큰이 없거나 틀리면 401.
///   요청이 겹치면 한 번에 하나씩 찍는다. 촬영 조건은 응답 헤더로 알린다(`X-Zoom`: 줌 배율).
/// - `GET /preview[?w=긴변]` → `image/jpeg` 작은 미리보기 한 장(셔터 없이 미리보기 프레임에서, 촬영 수에 안 셈).
///   조작 기기가 테이블 화면 배경으로 몇 초마다 받는다(기본 긴 변 960). `w` 를 주면 그 긴 변까지(프레임 원 크기가 상한),
///   판 상태 추적이 울기 모서리를 읽을 때 쓴다. 응답 헤더 `X-Frame-Size: WxH` 는 줄이기 전 프레임 크기(해상도 게이트 측정용).
///   헤드가 미리보기를 못 주면 404.
/// - `GET /status`  → 토큰 없이(또는 틀리면) `{"ok":true,"auth":false}` 만(살아 있는지 확인용).
///   맞는 토큰이면 `{"ok":true,"auth":true,"captures":N,"last_capture":"<iso>"|null}`.
class CameraHeadServer {
  static const int defaultPort = 8765;
  static const String tokenHeader = 'X-Head-Token';
  static const String frameSizeHeader = 'X-Frame-Size';

  /// 실제로 사진을 찍는 함수. 카메라가 준비되지 않았으면 던진다.
  final Future<Uint8List> Function() capture;

  /// 작은 미리보기를 주는 함수(`/preview`). [longSide] 는 요청한 긴 변(없으면 기본). 없으면 404.
  final Future<PreviewFrame> Function(int? longSide)? preview;

  /// 촬영 수·시각이 바뀔 때 알린다(화면 갱신용).
  final void Function()? onChanged;

  /// 촬영 응답에 붙일 헤더(촬영 조건). 찍을 때마다 부른다.
  final Map<String, String> Function()? headers;

  /// 조작 기기가 보내야 하는 토큰. 바꾸면 다음 요청부터 새 토큰만 받는다(재발급).
  String token;

  HttpServer? _server;
  Future<void> _chain = Future<void>.value();
  int captureCount = 0;
  int previewCount = 0;
  DateTime? lastCaptureAt;
  String? lastError;

  CameraHeadServer({
    required this.capture,
    required this.token,
    this.preview,
    this.onChanged,
    this.headers,
  });

  bool get isRunning => _server != null;
  int get port => _server?.port ?? 0;

  /// [port] 0 이면 빈 포트를 고른다(테스트용). 기본은 모든 IPv4 인터페이스.
  Future<void> start({int port = defaultPort, InternetAddress? address}) async {
    if (_server != null) return;
    final s = await HttpServer.bind(address ?? InternetAddress.anyIPv4, port);
    _server = s;
    s.listen(_handle, onError: (_) {});
  }

  Future<void> stop() async {
    final s = _server;
    _server = null;
    await s?.close(force: true);
  }

  /// 촬영을 직렬화한다. 앞선 촬영이 실패해도 다음 촬영은 진행한다.
  Future<Uint8List> _captureSerialized() {
    final next = _chain.then((_) => capture());
    _chain = next.then((_) {}, onError: (_) {});
    return next;
  }

  bool _authorized(HttpRequest req) {
    final given = req.headers.value(tokenHeader) ?? req.uri.queryParameters['t'];
    return given != null && tokenEquals(given, token);
  }

  Future<void> _handle(HttpRequest req) async {
    final res = req.response;
    res.headers.set('Access-Control-Allow-Origin', '*');
    res.headers.set('Cache-Control', 'no-store');
    try {
      if (req.method != 'GET') {
        res.statusCode = HttpStatus.methodNotAllowed;
      } else {
        switch (req.uri.path) {
          case '/capture':
            if (!_authorized(req)) {
              res.statusCode = HttpStatus.unauthorized;
              res.headers.contentType = ContentType.json;
              res.write(jsonEncode({'ok': false, 'error': 'token'}));
              break;
            }
            final bytes = await _captureSerialized();
            captureCount++;
            lastCaptureAt = DateTime.now();
            lastError = null;
            onChanged?.call();
            res.headers.contentType = ContentType('image', 'jpeg');
            headers?.call().forEach(res.headers.set);
            res.contentLength = bytes.length;
            res.add(bytes);
          case '/preview':
            if (!_authorized(req)) {
              res.statusCode = HttpStatus.unauthorized;
              res.headers.contentType = ContentType.json;
              res.write(jsonEncode({'ok': false, 'error': 'token'}));
              break;
            }
            final p = preview;
            if (p == null) {
              res.statusCode = HttpStatus.notFound;
              res.headers.contentType = ContentType.json;
              res.write(jsonEncode({'ok': false, 'error': 'no preview'}));
              break;
            }
            final w = int.tryParse(req.uri.queryParameters['w'] ?? '');
            final frame = await p(w?.clamp(240, 8192));
            previewCount++;
            onChanged?.call();
            res.headers.contentType = ContentType('image', 'jpeg');
            res.headers.set(frameSizeHeader, '${frame.frameWidth}x${frame.frameHeight}');
            res.contentLength = frame.jpeg.length;
            res.add(frame.jpeg);
          case '/':
          case '/status':
            res.headers.contentType = ContentType.json;
            res.write(jsonEncode(_authorized(req)
                ? {
                    'ok': true,
                    'auth': true,
                    'captures': captureCount,
                    'last_capture': lastCaptureAt?.toIso8601String(),
                  }
                : {'ok': true, 'auth': false}));
          default:
            res.statusCode = HttpStatus.notFound;
        }
      }
    } catch (e) {
      lastError = '$e';
      onChanged?.call();
      res.statusCode = HttpStatus.serviceUnavailable;
      res.headers.contentType = ContentType.json;
      res.write(jsonEncode({'ok': false, 'error': '$e'}));
    }
    await res.close();
  }
}

/// 새 토큰. 16바이트 난수를 base64url(패딩 없음, 22자)로.
String generateHeadToken([Random? random]) {
  final r = random ?? Random.secure();
  final bytes = Uint8List.fromList(List<int>.generate(16, (_) => r.nextInt(256)));
  return base64Url.encode(bytes).replaceAll('=', '');
}

/// 내용과 무관하게 같은 시간이 걸리는 비교(응답 시간으로 토큰을 한 글자씩 맞히는 것 방지).
bool tokenEquals(String a, String b) {
  final x = utf8.encode(a);
  final y = utf8.encode(b);
  var diff = x.length ^ y.length;
  for (var i = 0; i < x.length; i++) {
    diff |= x[i] ^ (i < y.length ? y[i] : 0);
  }
  return diff == 0;
}

/// 카메라 헤드 접속 정보(주소 + 토큰). QR 로 주고받는다.
///
/// QR 문자열: `mahjongcam://<host>:<port>?t=<token>`. 사람이 붙여 넣는 `http://<host>:<port>?t=<token>`,
/// `<host>[:port][?t=<token>]` 도 [parse] 가 받는다.
class CameraHeadLink {
  static const String scheme = 'mahjongcam';

  /// `http://host:port` 꼴.
  final String baseUrl;

  /// 없으면 null(수동 입력에서 토큰을 따로 적는 경우).
  final String? token;

  const CameraHeadLink(this.baseUrl, {this.token});

  /// QR 에 넣을 문자열. [host] 는 카메라 헤드의 LAN IP.
  static String qrString(String host, int port, String token) =>
      '$scheme://$host:$port?t=${Uri.encodeQueryComponent(token)}';

  /// QR 스캔용. `mahjongcam://` 이고 토큰이 있을 때만 받는다(다른 QR 은 null).
  static CameraHeadLink? fromQr(String raw) {
    final s = raw.trim();
    if (!s.toLowerCase().startsWith('$scheme://')) return null;
    final link = parse(s);
    return link?.token == null ? null : link;
  }

  /// 사람이 적은 주소(또는 QR 문자열)를 해석한다. 주소가 아니거나 비어 있으면 null.
  /// 포트가 없으면 8765, `mahjongcam://` 은 `http://` 로 바꾼다.
  static CameraHeadLink? parse(String input) {
    var s = input.trim();
    if (s.isEmpty || s.contains(' ')) return null;
    if (!s.contains('://')) s = 'http://$s';
    final u = Uri.tryParse(s);
    if (u == null || u.host.isEmpty) return null;
    final sch = u.scheme.toLowerCase();
    if (sch != 'http' && sch != 'https' && sch != scheme) return null;
    final port = u.hasPort ? u.port : CameraHeadServer.defaultPort;
    if (port <= 0 || port > 65535) return null;
    final t = u.queryParameters['t']?.trim();
    return CameraHeadLink(
      '${sch == scheme ? 'http' : sch}://${u.host}:$port',
      token: t == null || t.isEmpty ? null : t,
    );
  }
}

/// 이 기기의 LAN IPv4 주소들. Wi-Fi(wlan) 인터페이스를 앞에 둔다.
Future<List<String>> localIPv4Addresses() async {
  try {
    final ifs = await NetworkInterface.list(
      type: InternetAddressType.IPv4,
      includeLoopback: false,
    );
    final wifi = <String>[];
    final other = <String>[];
    for (final i in ifs) {
      final isWifi = i.name.toLowerCase().contains('wlan') ||
          i.name.toLowerCase().contains('wi-fi');
      for (final a in i.addresses) {
        (isWifi ? wifi : other).add(a.address);
      }
    }
    return [...wifi, ...other];
  } catch (_) {
    return const [];
  }
}

/// 헤드가 만든 미리보기 한 장: 줄인 JPEG 와 줄이기 전 프레임 크기.
class PreviewFrame {
  final Uint8List jpeg;
  final int frameWidth;
  final int frameHeight;
  const PreviewFrame(this.jpeg, {required this.frameWidth, required this.frameHeight});
}

/// 조작 기기가 받은 미리보기. [frameWidth]·[frameHeight] 는 헤드 스트림의 원 크기(헤더가 없으면 null).
class RemotePreview {
  final Uint8List bytes;
  final int? frameWidth;
  final int? frameHeight;
  const RemotePreview(this.bytes, {this.frameWidth, this.frameHeight});

  int? get frameLongSide {
    final w = frameWidth, h = frameHeight;
    if (w == null || h == null) return null;
    return w > h ? w : h;
  }
}

/// 원격 카메라에서 받은 사진과 촬영 조건.
class RemoteShot {
  final Uint8List bytes;

  /// 카메라 헤드가 알려 준 줌 배율. 모르면 null.
  final double? zoom;
  const RemoteShot(this.bytes, {this.zoom});
}

class RemoteCameraException implements Exception {
  final String message;

  /// 토큰이 없거나 틀려 카메라 헤드가 거절했다(QR 을 다시 스캔해야 함).
  final bool unauthorized;

  /// 헤드가 그 기능이 없다(404, 예전 헤드 앱의 `/preview`). 다시 묻지 않는다.
  final bool unsupported;
  const RemoteCameraException(this.message, {this.unauthorized = false, this.unsupported = false});
  @override
  String toString() => message;
}

/// 조작 기기 쪽. [CameraHeadServer] 에 촬영을 부탁한다.
class RemoteCamera {
  static const String rescanMessage =
      '카메라 헤드가 연결을 거부했습니다(토큰이 없거나 바뀜). 카메라 헤드 화면의 QR 을 다시 스캔하세요.';

  final String baseUrl;

  /// 카메라 헤드 토큰. 안 주면 [url] 의 `?t=` 를 쓴다.
  final String? token;
  final Duration timeout;
  final http.Client _http;

  RemoteCamera(
    String url, {
    String? token,
    this.timeout = const Duration(seconds: 30),
    http.Client? httpClient,
  })  : baseUrl = normalize(url),
        token = token ?? CameraHeadLink.parse(url)?.token,
        _http = httpClient ?? http.Client();

  /// 사용자가 적은 주소를 `http://host:port` 꼴로 맞춘다(토큰 쿼리는 뺀다). 비어 있으면 빈 문자열.
  /// `192.168.0.5` → `http://192.168.0.5:8765`, `192.168.0.5:9000` → `http://192.168.0.5:9000`.
  static String normalize(String input) {
    final s = input.trim();
    if (s.isEmpty) return '';
    return CameraHeadLink.parse(s)?.baseUrl ?? s;
  }

  Future<RemoteShot> capture() async {
    final r = await _get('/capture');
    if (!(r.headers['content-type'] ?? '').startsWith('image/')) {
      throw const RemoteCameraException('카메라 기기가 사진이 아닌 응답을 보냈습니다.');
    }
    return RemoteShot(ignoreExifRotation(r.bodyBytes), zoom: double.tryParse(r.headers['x-zoom'] ?? ''));
  }

  /// 미리보기 한 장. 기본은 작게(테이블 화면 배경용), [longSide] 를 주면 그 긴 변까지(울기 모서리 읽기용).
  /// 헤드가 미리보기를 못 주면 `unsupported`.
  Future<RemotePreview> preview({int? longSide}) async {
    final r = await _get(longSide == null ? '/preview' : '/preview?w=$longSide');
    if (!(r.headers['content-type'] ?? '').startsWith('image/')) {
      throw const RemoteCameraException('카메라 기기가 사진이 아닌 응답을 보냈습니다.');
    }
    final size = (r.headers[CameraHeadServer.frameSizeHeader.toLowerCase()] ?? '').split('x');
    final fw = size.length == 2 ? int.tryParse(size[0]) : null;
    final fh = size.length == 2 ? int.tryParse(size[1]) : null;
    return RemotePreview(r.bodyBytes, frameWidth: fw, frameHeight: fh);
  }

  /// EXIF 회전값을 1(그대로)로 바꾼다. 픽셀은 다시 인코딩하지 않는다.
  /// 테이블을 내려다보는 폰은 중력으로 가로·세로를 못 가려 회전값이 촬영 중에 바뀐다(매장 실험 13:18, 1→6).
  /// 고정된 카메라는 센서 방향이 늘 같고, 어느 쪽이 아래인지는 "화면 아래쪽 자리" 설정이 맞춘다.
  static Uint8List ignoreExifRotation(Uint8List jpeg) {
    try {
      final exif = img.decodeJpgExif(jpeg);
      if (exif == null || !exif.imageIfd.hasOrientation || exif.imageIfd.orientation == 1) {
        return jpeg;
      }
      exif.imageIfd.orientation = 1;
      return img.injectJpgExif(jpeg, exif) ?? jpeg;
    } catch (_) {
      return jpeg;
    }
  }

  /// 상태. 토큰이 맞지 않으면 `unauthorized` 로 던진다(QR 스캔 직후 연결 확인용).
  Future<Map<String, dynamic>> status() async {
    final r = await _get('/status');
    final Map<String, dynamic> m;
    try {
      m = jsonDecode(r.body) as Map<String, dynamic>;
    } on FormatException {
      throw const RemoteCameraException('카메라 기기 응답을 읽을 수 없습니다.');
    }
    if (m['auth'] == false) {
      throw const RemoteCameraException(rescanMessage, unauthorized: true);
    }
    return m;
  }

  Future<http.Response> _get(String path) async {
    final http.Response r;
    try {
      final t = token;
      r = await _http
          .get(
            Uri.parse('$baseUrl$path'),
            headers: t == null ? null : {CameraHeadServer.tokenHeader: t},
          )
          .timeout(timeout);
    } on SocketException {
      throw RemoteCameraException('카메라 기기($baseUrl)에 연결할 수 없습니다. 같은 Wi-Fi 인지, 카메라 헤드 화면이 켜져 있는지 확인하세요.');
    } on TimeoutException {
      throw RemoteCameraException('카메라 기기가 ${timeout.inSeconds}초 안에 응답하지 않습니다.');
    } on http.ClientException catch (e) {
      throw RemoteCameraException('카메라 기기 연결 오류: ${e.message}');
    }
    if (r.statusCode == 200) return r;
    if (r.statusCode == HttpStatus.unauthorized) {
      throw const RemoteCameraException(rescanMessage, unauthorized: true);
    }
    if (r.statusCode == HttpStatus.notFound) {
      throw RemoteCameraException('카메라 기기에 $path 가 없습니다(헤드 앱이 예전 버전).', unsupported: true);
    }
    String detail = '';
    try {
      detail = (jsonDecode(r.body) as Map<String, dynamic>)['error']?.toString() ?? '';
    } catch (_) {}
    throw RemoteCameraException(
      detail.isNotEmpty ? '카메라 기기 오류: $detail' : '카메라 기기 오류 (HTTP ${r.statusCode})',
    );
  }

  void close() => _http.close();
}
