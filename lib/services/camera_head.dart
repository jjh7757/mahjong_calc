import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show debugPrint;
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
/// - `GET /status`  → 토큰 없이(또는 틀리면) `{"ok":true,"auth":false,"head":"mahjongcam","pair":bool}` 만
///   (살아 있는지·버튼 연결을 받는지 확인용, [discoverCameraHeads] 가 이걸로 헤드를 찾는다).
///   맞는 토큰이면 `{"ok":true,"auth":true,"head":"mahjongcam","pair":bool,"captures":N,"last_capture":"<iso>"|null}`.
/// - `GET /rec/frames?after=<ms>&max=<n>` → 녹화 모드(시험용) 프레임 이어 받기. [after] ms 보다 늦게 다 쓴 프레임을
///   오름차순으로 [n] 장까지(기본 10, 최대 [maxRecordBatch]) 한 응답에 묶는다(본문 형식은 [RecordBatch]).
///   헤더 `X-Rec-Dir`(녹화 폴더 이름, 녹화한 적 없으면 없음)·`X-Rec-Recording`(1/0)·`X-Rec-Latest`(다 쓴 마지막 ms)·
///   `X-Rec-Remaining`(이 묶음 뒤에 남은 장수). 헤드가 녹화를 못 하면 404.
///   `&newest=1` 이면 밀린 것은 건너뛰고 가장 최근 프레임 한 장만(after 보다 늦을 때) — 태블릿 "보기만" 모드.
/// - `GET /pair` → [allowPair] 가 켜져 있으면 `{"ok":true,"token":"..."}`, 꺼져 있으면 403 `{"ok":false,"error":"pair"}`.
///   QR 없이 버튼으로 연결할 때(테스트용). 같은 Wi-Fi 의 누구나 토큰을 받아 가므로 헤드 화면 토글로만 켠다.
class CameraHeadServer {
  static const int defaultPort = 8765;
  static const String tokenHeader = 'X-Head-Token';
  static const String frameSizeHeader = 'X-Frame-Size';

  /// `/status` 의 `head` 값. 같은 포트의 다른 서비스와 헤드를 가른다.
  static const String headId = 'mahjongcam';

  /// 실제로 사진을 찍는 함수. 카메라가 준비되지 않았으면 던진다.
  final Future<Uint8List> Function() capture;

  /// 작은 미리보기를 주는 함수(`/preview`). [longSide] 는 요청한 긴 변(없으면 기본). 없으면 404.
  final Future<PreviewFrame> Function(int? longSide)? preview;

  /// 녹화 프레임 묶음(`/rec/frames`). 없으면 404.
  final Future<RecordBatch> Function(int after, int max)? recordFrames;

  static const int maxRecordBatch = 30;

  /// `newest=1` 에서 마지막 ms 만 알아낼 때 넘기는 after(어떤 프레임보다 늦음).
  static const int newestProbe = 1 << 62;

  /// 촬영 수·시각이 바뀔 때 알린다(화면 갱신용).
  final void Function()? onChanged;

  /// 촬영 응답에 붙일 헤더(촬영 조건). 찍을 때마다 부른다.
  final Map<String, String> Function()? headers;

  /// 조작 기기가 보내야 하는 토큰. 바꾸면 다음 요청부터 새 토큰만 받는다(재발급).
  String token;

  /// 켜져 있으면 `/pair` 가 토큰 없이 토큰을 내준다(버튼 연결). 헤드 화면의 토글.
  bool allowPair;

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
    this.recordFrames,
    this.onChanged,
    this.headers,
    this.allowPair = false,
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
          case '/rec/frames':
            if (!_authorized(req)) {
              res.statusCode = HttpStatus.unauthorized;
              res.headers.contentType = ContentType.json;
              res.write(jsonEncode({'ok': false, 'error': 'token'}));
              break;
            }
            final rf = recordFrames;
            if (rf == null) {
              res.statusCode = HttpStatus.notFound;
              res.headers.contentType = ContentType.json;
              res.write(jsonEncode({'ok': false, 'error': 'no record'}));
              break;
            }
            final after = int.tryParse(req.uri.queryParameters['after'] ?? '') ?? 0;
            final max = (int.tryParse(req.uri.queryParameters['max'] ?? '') ?? 10).clamp(0, maxRecordBatch);
            final RecordBatch b;
            if (req.uri.queryParameters['newest'] == '1') {
              // 보기만: 밀린 것은 건너뛰고 가장 최근 프레임 한 장만(after 보다 늦을 때). 먼저 0장으로 마지막 ms 만 알아낸다.
              final head = await rf(newestProbe, 0);
              final latest = head.latest;
              b = latest != null && latest > after && max > 0 ? await rf(latest - 1, 1) : head;
            } else {
              b = await rf(after, max);
            }
            res.headers.contentType = ContentType('application', 'octet-stream');
            b.headers().forEach(res.headers.set);
            final body = b.encodeBody();
            res.contentLength = body.length;
            res.add(body);
          case '/pair':
            res.headers.contentType = ContentType.json;
            if (!allowPair) {
              res.statusCode = HttpStatus.forbidden;
              res.write(jsonEncode({'ok': false, 'error': 'pair'}));
              break;
            }
            res.write(jsonEncode({'ok': true, 'token': token}));
          case '/':
          case '/status':
            res.headers.contentType = ContentType.json;
            res.write(jsonEncode(_authorized(req)
                ? {
                    'ok': true,
                    'auth': true,
                    'head': headId,
                    'pair': allowPair,
                    'captures': captureCount,
                    'last_capture': lastCaptureAt?.toIso8601String(),
                  }
                : {'ok': true, 'auth': false, 'head': headId, 'pair': allowPair}));
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

/// 사설 IPv4 인가(10/8, 172.16/12, 192.168/16). 헤드 찾기는 이 대역만 훑는다.
bool isPrivateIPv4(String ip) {
  final p = ip.split('.').map(int.tryParse).toList();
  if (p.length != 4 || p.any((x) => x == null || x < 0 || x > 255)) return false;
  final a = p[0]!, b = p[1]!;
  return a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168);
}

/// [localAddresses](이 기기 IPv4, Wi-Fi 먼저)의 /24 대역에서 헤드 후보 주소(.1~.254, 자기 자신 제외).
/// 사설 대역만, 앞에서부터 [maxSubnets] 개 대역까지. 자기 주소 가까운 쪽을 먼저 둔다(공유기가 붙여 준 번호가 비슷한 경우가 많다).
List<String> subnetHosts(List<String> localAddresses, {int maxSubnets = 2}) {
  final selves = localAddresses.toSet();
  final out = <String>[];
  final seen = <String>{};
  final subnets = <String>[];
  for (final ip in localAddresses) {
    if (!isPrivateIPv4(ip)) continue;
    final prefix = ip.substring(0, ip.lastIndexOf('.'));
    if (subnets.contains(prefix)) continue;
    if (subnets.length >= maxSubnets) break;
    subnets.add(prefix);
    final me = int.parse(ip.substring(ip.lastIndexOf('.') + 1));
    final order = [for (var i = 1; i <= 254; i++) i]..sort((x, y) => (x - me).abs().compareTo((y - me).abs()));
    for (final i in order) {
      final h = '$prefix.$i';
      if (selves.contains(h) || !seen.add(h)) continue;
      out.add(h);
    }
  }
  return out;
}

/// [discoverCameraHeads] 가 찾은 카메라 헤드 하나.
class FoundHead {
  /// `http://host:port` 꼴.
  final String baseUrl;

  /// 넘긴 토큰을 헤드가 받아 줬다(이미 연결했던 헤드).
  final bool authorized;

  /// 헤드가 버튼 연결(`/pair`)을 허용한다.
  final bool pairable;
  const FoundHead(this.baseUrl, {this.authorized = false, this.pairable = false});

  @override
  String toString() => 'FoundHead($baseUrl, auth: $authorized, pair: $pairable)';
}

/// 같은 Wi-Fi 의 카메라 헤드를 찾는다: [hosts] 의 [port] 에 TCP 로 붙어 보고(빠르게 거름), 열린 곳만 `/status` 를 묻는다.
/// [token] 을 주면 그 토큰을 받아 주는 헤드에 [FoundHead.authorized] 를 단다. 받아 주는 헤드 → 버튼 연결 허용 → 나머지 순.
/// 254곳을 [concurrency] 개씩 동시에 물어 보통 1~2초 걸린다.
Future<List<FoundHead>> discoverCameraHeads({
  required Iterable<String> hosts,
  int port = CameraHeadServer.defaultPort,
  String? token,
  Duration connectTimeout = const Duration(milliseconds: 700),
  Duration statusTimeout = const Duration(seconds: 2),
  int concurrency = 64,
}) async {
  final queue = hosts.toList();
  final found = <FoundHead>[];
  var next = 0;
  final client = http.Client();
  Future<void> probe(String host) async {
    try {
      final s = await Socket.connect(host, port, timeout: connectTimeout);
      s.destroy();
    } catch (_) {
      return;
    }
    final base = 'http://$host:$port';
    try {
      final r = await client
          .get(
            Uri.parse('$base/status'),
            headers: token == null ? null : {CameraHeadServer.tokenHeader: token},
          )
          .timeout(statusTimeout);
      if (r.statusCode != 200) return;
      final m = jsonDecode(r.body);
      if (m is! Map || m['ok'] != true) return;
      // 예전 헤드 앱은 `head` 없이 {"ok":true,"auth":...} 만 준다.
      final isHead = m['head'] == CameraHeadServer.headId || (m['head'] == null && m['auth'] is bool);
      if (!isHead) return;
      found.add(FoundHead(base, authorized: m['auth'] == true, pairable: m['pair'] == true));
    } catch (_) {}
  }

  Future<void> worker() async {
    while (next < queue.length) {
      await probe(queue[next++]);
    }
  }

  try {
    await Future.wait([for (var i = 0; i < concurrency && i < queue.length; i++) worker()]);
  } finally {
    client.close();
  }
  int rank(FoundHead h) => h.authorized ? 0 : (h.pairable ? 1 : 2);
  found.sort((a, b) => rank(a).compareTo(rank(b)));
  return found;
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

  /// 주소로 닿지 않았다(연결 거부·시간 초과). 헤드 IP 가 바뀌었을 수 있어 [discoverCameraHeads] 로 다시 찾을 만하다.
  final bool unreachable;

  /// `/pair` 가 꺼져 있다(헤드 화면의 "버튼 연결 허용" 이 꺼짐).
  final bool pairOff;
  const RemoteCameraException(
    this.message, {
    this.unauthorized = false,
    this.unsupported = false,
    this.unreachable = false,
    this.pairOff = false,
  });
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
    // 요청 수를 기기 로그로 세려고(logcat `flutter` 태그, 2026-11-12 4080·1020 요청 줄이기 확인).
    debugPrint('[head-req] preview w=${longSide ?? 'default'}');
    final r = await _get(longSide == null ? '/preview' : '/preview?w=$longSide');
    if (!(r.headers['content-type'] ?? '').startsWith('image/')) {
      throw const RemoteCameraException('카메라 기기가 사진이 아닌 응답을 보냈습니다.');
    }
    final size = (r.headers[CameraHeadServer.frameSizeHeader.toLowerCase()] ?? '').split('x');
    final fw = size.length == 2 ? int.tryParse(size[0]) : null;
    final fh = size.length == 2 ? int.tryParse(size[1]) : null;
    return RemotePreview(r.bodyBytes, frameWidth: fw, frameHeight: fh);
  }

  /// 녹화 프레임 이어 받기(`/rec/frames`). [after] ms 보다 늦은 프레임을 [max] 장까지. 헤드가 녹화를 못 하면 `unsupported`.
  Future<RecordBatch> recordFrames({required int after, int max = 10, bool newest = false}) async {
    final r = await _get('/rec/frames?after=$after&max=$max${newest ? '&newest=1' : ''}');
    try {
      return RecordBatch.decode(r.headers, r.bodyBytes);
    } on FormatException catch (e) {
      throw RemoteCameraException('녹화 묶음을 읽을 수 없습니다: ${e.message}');
    }
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

  /// 버튼 연결: 헤드가 허용했으면 토큰을 받아 온다(토큰 없이 부른다). 꺼져 있으면 `pairOff`.
  Future<String> pair() async {
    final http.Response r;
    try {
      r = await _http.get(Uri.parse('$baseUrl/pair')).timeout(timeout);
    } on SocketException {
      throw RemoteCameraException('카메라 기기($baseUrl)에 연결할 수 없습니다.', unreachable: true);
    } on TimeoutException {
      throw RemoteCameraException('카메라 기기가 ${timeout.inSeconds}초 안에 응답하지 않습니다.', unreachable: true);
    } on http.ClientException catch (e) {
      throw RemoteCameraException('카메라 기기 연결 오류: ${e.message}', unreachable: true);
    }
    if (r.statusCode == HttpStatus.forbidden) {
      throw const RemoteCameraException(
        '카메라 헤드의 "버튼 연결 허용" 이 꺼져 있습니다. 헤드 화면 오른쪽 위 고리 아이콘을 켜거나 QR 을 스캔하세요.',
        pairOff: true,
      );
    }
    if (r.statusCode == HttpStatus.notFound) {
      throw const RemoteCameraException('카메라 헤드 앱이 예전 버전이라 버튼 연결을 못 합니다. QR 을 스캔하세요.', unsupported: true);
    }
    try {
      final m = jsonDecode(r.body) as Map<String, dynamic>;
      final t = m['token'];
      if (r.statusCode == 200 && t is String && t.isNotEmpty) return t;
    } catch (_) {}
    throw RemoteCameraException('카메라 기기 오류 (HTTP ${r.statusCode})');
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
      throw RemoteCameraException(
        '카메라 기기($baseUrl)에 연결할 수 없습니다. 같은 Wi-Fi 인지, 카메라 헤드 화면이 켜져 있는지 확인하세요.',
        unreachable: true,
      );
    } on TimeoutException {
      throw RemoteCameraException('카메라 기기가 ${timeout.inSeconds}초 안에 응답하지 않습니다.', unreachable: true);
    } on http.ClientException catch (e) {
      throw RemoteCameraException('카메라 기기 연결 오류: ${e.message}', unreachable: true);
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

/// 녹화 프레임 하나(헤드 파일 `f_<ms>.jpg`).
class RecordFrame {
  final int ms;
  final Uint8List jpeg;
  const RecordFrame(this.ms, this.jpeg);
}

/// `/rec/frames` 응답 한 묶음. 본문은 프레임마다 `[ms: int64 BE][길이: uint32 BE][JPEG]` 를 이어 붙인 것.
class RecordBatch {
  /// 녹화 폴더 이름(`rec_<시각>`). 녹화한 적이 없으면 null.
  final String? dir;
  final bool recording;

  /// 헤드가 다 쓴 마지막 프레임 ms. 없으면 null.
  final int? latest;

  /// 이 묶음 뒤에 남은 장수.
  final int remaining;
  final List<RecordFrame> frames;

  const RecordBatch({this.dir, this.recording = false, this.latest, this.remaining = 0, this.frames = const []});

  static const String dirHeader = 'X-Rec-Dir';
  static const String recordingHeader = 'X-Rec-Recording';
  static const String latestHeader = 'X-Rec-Latest';
  static const String remainingHeader = 'X-Rec-Remaining';

  Map<String, String> headers() => {
        dirHeader: ?dir,
        recordingHeader: recording ? '1' : '0',
        if (latest != null) latestHeader: '$latest',
        remainingHeader: '$remaining',
      };

  Uint8List encodeBody() {
    final out = BytesBuilder(copy: false);
    for (final f in frames) {
      final h = ByteData(12)
        ..setInt64(0, f.ms)
        ..setUint32(8, f.jpeg.length);
      out.add(h.buffer.asUint8List());
      out.add(f.jpeg);
    }
    return out.toBytes();
  }

  /// [headers] 는 소문자 키(http 패키지 응답 헤더).
  static RecordBatch decode(Map<String, String> headers, Uint8List body) {
    String? h(String k) => headers[k.toLowerCase()];
    final frames = <RecordFrame>[];
    final bd = ByteData.sublistView(body);
    var i = 0;
    while (i < body.length) {
      if (body.length - i < 12) throw const FormatException('머리가 잘림');
      final ms = bd.getInt64(i);
      final len = bd.getUint32(i + 8);
      i += 12;
      if (body.length - i < len) throw const FormatException('사진이 잘림');
      frames.add(RecordFrame(ms, Uint8List.sublistView(body, i, i + len)));
      i += len;
    }
    final d = h(dirHeader);
    return RecordBatch(
      dir: d == null || d.isEmpty ? null : d,
      recording: h(recordingHeader) == '1',
      latest: int.tryParse(h(latestHeader) ?? ''),
      remaining: int.tryParse(h(remainingHeader) ?? '') ?? 0,
      frames: frames,
    );
  }
}
