import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show MissingPluginException;
import 'package:qr_flutter/qr_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../services/camera_head.dart';
import '../../services/head_camera.dart';
import '../../services/screen_wake.dart';

/// 카메라 헤드 모드. 이 기기를 테이블 위에 고정해 두고, 같은 Wi-Fi 의 다른 기기(태블릿·노트북)가
/// 거치 촬영 화면에서 이 화면의 QR 을 스캔해(또는 "원격 카메라 주소" 에 적어) 사진을 받아 간다.
/// 이 화면은 미리보기·줌·접속 QR 만 보여 준다. 판독·대국 기록은 조작 기기 쪽에서 한다.
///
/// QR 에는 주소와 토큰이 들어 있다. 토큰은 기기에 저장해 다시 열어도 같고(한 번 스캔하면 끝),
/// 오른쪽 위 "새 QR" 로 바꾸면 이전에 스캔한 기기는 더 이상 찍을 수 없다.
///
/// 테스트용 버튼 연결: 오른쪽 위 고리 아이콘으로 "버튼 연결 허용" 을 켜면, 조작 기기의 "카메라 헤드 찾기" 가
/// 같은 Wi-Fi 를 훑어 이 헤드를 찾고 `/pair` 로 토큰까지 받아 간다(QR 없이). 켠 상태는 기기에 저장된다.
/// 같은 Wi-Fi 의 누구나 토큰을 받을 수 있으므로 기본은 꺼짐.
///
/// 카메라는 camera 플러그인이 아니라 전용 [HeadCamera](Android, 셔터 없이 미리보기 + 12MP YUV 스트림)다.
/// `/capture` 와 `/preview` 모두 스트림의 최신 프레임에서 JPEG 를 만든다 — 셔터음이 없고, 미리보기도 촬영과 같은
/// 해상도까지 줄 수 있다(판 상태 추적의 울기 모서리 읽기용, NOTES 32). 줌은 둘 다에 적용된다.
class CameraHeadScreen extends StatefulWidget {
  const CameraHeadScreen({super.key});

  @override
  State<CameraHeadScreen> createState() => _CameraHeadScreenState();
}

class _CameraHeadScreenState extends State<CameraHeadScreen> {
  static const String zoomPref = 'cameraHead.zoom';
  static const String tokenPref = 'cameraHead.token';
  static const String allowPairPref = 'cameraHead.allowPair';
  static const List<double> zoomSteps = [1, 1.5, 2, 3, 4];

  HeadCamera? _cam;
  String? _camError;
  late final CameraHeadServer _server;
  String? _serverError;
  List<String> _addresses = const [];
  double _zoom = 1;
  double _maxZoom = 1;
  bool _showInfo = true;
  int _frameW = 0;
  int _frameH = 0;

  @override
  void initState() {
    super.initState();
    _server = CameraHeadServer(
      capture: _capture,
      preview: _preview,
      // 저장된 토큰을 읽기 전까지는 서버를 열지 않으므로 이 값은 쓰이지 않는다.
      token: generateHeadToken(),
      onChanged: () {
        if (mounted) setState(() {});
      },
      headers: () => {'X-Zoom': _zoom.toStringAsFixed(2)},
    );
    ScreenWake.keepOn(true);
    _loadZoom().then((_) => _initCamera());
    _loadToken().then((_) => _startServer());
  }

  @override
  void dispose() {
    ScreenWake.keepOn(false);
    _server.stop();
    _cam?.stop();
    super.dispose();
  }

  Future<void> _loadZoom() async {
    try {
      final z = (await SharedPreferences.getInstance()).getDouble(zoomPref);
      if (z != null && z >= 1) _zoom = z;
    } catch (_) {}
  }

  /// 저장된 토큰을 쓰고, 없으면 새로 만들어 저장한다.
  Future<void> _loadToken() async {
    try {
      final p = await SharedPreferences.getInstance();
      final t = p.getString(tokenPref);
      if (t != null && t.isNotEmpty) {
        _server.token = t;
      } else {
        await p.setString(tokenPref, _server.token);
      }
      _server.allowPair = p.getBool(allowPairPref) ?? false;
    } catch (_) {}
  }

  /// 버튼 연결(토큰 없이 `/pair` 로 토큰 내주기)을 켜고 끈다.
  Future<void> _toggleAllowPair() async {
    final next = !_server.allowPair;
    setState(() => _server.allowPair = next);
    try {
      await (await SharedPreferences.getInstance()).setBool(allowPairPref, next);
    } catch (_) {}
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(next
            ? '버튼 연결 허용: 조작 기기의 "카메라 헤드 찾기" 로 QR 없이 연결됩니다.'
            : '버튼 연결 끔: 새 기기는 QR 로만 연결합니다(이미 연결된 기기는 그대로).'),
      ));
  }

  /// 토큰을 바꾼다. 이전 QR 로 연결한 기기는 다시 스캔해야 한다.
  Future<void> _regenerateToken() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('새 QR 만들기'),
        content: const Text('지금 연결된 조작 기기는 더 이상 찍을 수 없고, 새 QR 을 다시 스캔해야 합니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('새 QR'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    final t = generateHeadToken();
    try {
      await (await SharedPreferences.getInstance()).setString(tokenPref, t);
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _server.token = t;
      _showInfo = true;
    });
  }

  Future<void> _initCamera() async {
    final c = HeadCamera();
    try {
      await c.start(zoom: _zoom);
    } on MissingPluginException {
      if (mounted) setState(() => _camError = '이 기기에서는 카메라 헤드를 쓸 수 없습니다(Android 전용)');
      return;
    } catch (e) {
      if (mounted) setState(() => _camError = '카메라를 열 수 없습니다: $e');
      return;
    }
    if (!mounted) {
      c.stop();
      return;
    }
    setState(() {
      _cam = c;
      _camError = null;
      _maxZoom = c.maxZoom;
      _frameW = c.streamWidth;
      _frameH = c.streamHeight;
      _zoom = _zoom.clamp(1.0, c.maxZoom < 1 ? 1.0 : c.maxZoom).toDouble();
    });
  }

  Future<void> _applyZoom(double z, {bool save = true}) async {
    final c = _cam;
    final upper = _maxZoom < 1 ? 1.0 : _maxZoom;
    var clamped = z.clamp(1.0, upper).toDouble();
    if (c != null) {
      try {
        clamped = await c.setZoom(clamped);
      } catch (_) {
        return;
      }
    }
    if (!mounted) return;
    setState(() => _zoom = clamped);
    if (save) {
      try {
        await (await SharedPreferences.getInstance()).setDouble(zoomPref, clamped);
      } catch (_) {}
    }
  }

  Future<void> _startServer() async {
    try {
      await _server.start();
      _addresses = await localIPv4Addresses();
      if (mounted) setState(() => _serverError = null);
    } catch (e) {
      if (mounted) setState(() => _serverError = '서버를 열 수 없습니다: $e');
    }
  }

  HeadCamera _ready() {
    final c = _cam;
    if (c == null || !c.isRunning) {
      throw StateError('카메라 헤드의 카메라가 준비되지 않았습니다');
    }
    return c;
  }

  /// 조작 기기가 /capture 를 부르면 스트림의 다음 프레임을 원 크기 JPEG 로(셔터 없음).
  Future<Uint8List> _capture() async {
    final j = await _ready().jpeg(quality: 92, fresh: true);
    _noteFrame(j);
    return j.bytes;
  }

  /// 조작 기기가 /preview 를 부르면 최신 프레임을 긴 변 [longSide](기본 960)로 줄인 JPEG 로.
  /// 큰 요청(2000 이상, 판 상태 추적의 울기 모서리 읽기)은 패 무늬가 뭉개지지 않게 품질을 올린다.
  Future<PreviewFrame> _preview(int? longSide) async {
    final side = longSide ?? 960;
    final j = await _ready().jpeg(longSide: side, quality: side >= 2000 ? 88 : 75);
    _noteFrame(j);
    return PreviewFrame(j.bytes, frameWidth: j.frameWidth, frameHeight: j.frameHeight);
  }

  void _noteFrame(HeadJpeg j) {
    if (j.frameWidth != _frameW || j.frameHeight != _frameH) {
      _frameW = j.frameWidth;
      _frameH = j.frameHeight;
      if (mounted) setState(() {});
    }
  }

  String _time(DateTime t) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
  }

  String _status() {
    final b = StringBuffer('촬영 ${_server.captureCount}회');
    if (_server.previewCount > 0) b.write(' · 미리보기 ${_server.previewCount}');
    final last = _server.lastCaptureAt;
    if (last != null) b.write(' · 마지막 ${_time(last)}');
    if (_frameW > 0) b.write(' · 스트림 $_frameW×$_frameH');
    final err = _server.lastError;
    if (err != null) b.write(' · 오류: $err');
    return b.toString();
  }

  @override
  Widget build(BuildContext context) {
    final c = _cam;
    final port = _server.port;
    final token = _server.token;
    final qr = _addresses.isEmpty
        ? null
        : CameraHeadLink.qrString(_addresses.first, port, token);
    // 수동 입력용(조작 기기의 주소 칸에 그대로 붙여 넣으면 토큰까지 들어간다).
    final urls = [for (final a in _addresses) 'http://$a:$port?t=$token'];
    final Widget preview = c != null && c.textureId != null
        ? Center(child: _TexturePreview(cam: c))
        : Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(
                _camError ?? '카메라 준비 중…',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70),
              ),
            ),
          );
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('카메라 헤드'),
        actions: [
          IconButton(
            key: const ValueKey('head-allow-pair'),
            tooltip: _server.allowPair ? '버튼 연결 허용 중 (끄기)' : '버튼 연결 허용 (QR 없이)',
            icon: Icon(_server.allowPair ? Icons.link : Icons.link_off),
            color: _server.allowPair ? Colors.lightGreenAccent : null,
            onPressed: _toggleAllowPair,
          ),
          IconButton(
            key: const ValueKey('head-new-token'),
            tooltip: '새 QR (토큰 재발급)',
            icon: const Icon(Icons.autorenew),
            onPressed: _server.isRunning ? _regenerateToken : null,
          ),
          IconButton(
            tooltip: _showInfo ? 'QR 숨기기' : 'QR 보기',
            icon: Icon(_showInfo ? Icons.info : Icons.info_outline),
            onPressed: () => setState(() => _showInfo = !_showInfo),
          ),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          preview,
          // 겹치는 요소는 시스템 바(가로 모드의 내비게이션 바) 안쪽에 둔다.
          SafeArea(
            child: Stack(
              fit: StackFit.expand,
              children: [
                // 줌 선택. 촬영·미리보기 모두에 적용된다.
                Positioned(
                  right: 8,
                  top: 8,
                  child: _ZoomChips(
                    zoom: _zoom,
                    maxZoom: _maxZoom,
                    enabled: c != null,
                    onChanged: _applyZoom,
                  ),
                ),
                if (_showInfo)
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    child: _InfoPanel(
                      serverError: _serverError,
                      running: _server.isRunning,
                      urls: urls,
                      qr: qr,
                      allowPair: _server.allowPair,
                      status: _status(),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 네이티브 미리보기 텍스처. 센서 방향(보통 90)만큼 돌려 화면에 맞게 보여 준다.
class _TexturePreview extends StatelessWidget {
  final HeadCamera cam;
  const _TexturePreview({required this.cam});

  @override
  Widget build(BuildContext context) {
    final w = cam.previewWidth > 0 ? cam.previewWidth : 4;
    final h = cam.previewHeight > 0 ? cam.previewHeight : 3;
    return RotatedBox(
      quarterTurns: (cam.sensorOrientation ~/ 90) % 4,
      child: AspectRatio(
        aspectRatio: w / h,
        child: Texture(textureId: cam.textureId!),
      ),
    );
  }
}

class _ZoomChips extends StatelessWidget {
  final double zoom;
  final double maxZoom;
  final bool enabled;
  final ValueChanged<double> onChanged;
  const _ZoomChips({
    required this.zoom,
    required this.maxZoom,
    required this.enabled,
    required this.onChanged,
  });

  static String _label(double z) =>
      z == z.roundToDouble() ? '${z.toInt()}x' : '${z}x';

  @override
  Widget build(BuildContext context) {
    final upper = maxZoom < 1 ? 1.0 : maxZoom;
    final steps = _CameraHeadScreenState.zoomSteps
        .where((z) => z <= upper + 1e-6)
        .toList();
    if (steps.length < 2) return const SizedBox.shrink();
    return Material(
      color: Colors.black.withValues(alpha: 0.45),
      borderRadius: BorderRadius.circular(20),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final z in steps)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: ChoiceChip(
                  key: ValueKey('head-zoom-$z'),
                  label: Text(_label(z)),
                  selected: (zoom - z).abs() < 0.05,
                  visualDensity: VisualDensity.compact,
                  onSelected: enabled ? (_) => onChanged(z) : null,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _InfoPanel extends StatelessWidget {
  final String? serverError;
  final bool running;
  final List<String> urls;

  /// 조작 기기가 스캔할 QR 문자열(첫 번째 주소 + 토큰). 주소가 없으면 null.
  final String? qr;
  final bool allowPair;
  final String status;
  const _InfoPanel({
    required this.serverError,
    required this.running,
    required this.urls,
    required this.qr,
    required this.allowPair,
    required this.status,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final white = theme.textTheme.bodySmall?.copyWith(color: Colors.white70);
    final text = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (serverError != null)
            Text(serverError!, style: TextStyle(color: theme.colorScheme.error))
          else if (!running)
            Text('서버 여는 중…', style: white)
          else if (urls.isEmpty)
            Text('Wi-Fi 에 연결되어 있지 않습니다. 같은 Wi-Fi 에 붙은 뒤 다시 여세요.', style: white)
          else ...[
            Text(
              '조작 기기의 거치 촬영 → 더보기 → "카메라 헤드 QR 스캔" 으로 이 QR 을 찍으세요.',
              style: theme.textTheme.bodyMedium?.copyWith(color: Colors.white),
            ),
            Text(
              allowPair
                  ? '버튼 연결 허용 중: 조작 기기의 더보기 → "카메라 헤드 찾기" 로 QR 없이 연결됩니다.'
                  : '버튼 연결 꺼짐(오른쪽 위 고리 아이콘으로 켜면 QR 없이 "카메라 헤드 찾기" 로 연결).',
              key: const ValueKey('head-pair-state'),
              style: white?.copyWith(color: allowPair ? Colors.lightGreenAccent : null),
            ),
            Text('직접 적을 때(원격 카메라 주소):', style: white),
            for (final u in urls)
              SelectableText(
                u,
                key: ValueKey('head-url-$u'),
                style: white?.copyWith(
                  color: Colors.white,
                  fontFeatures: const [ui.FontFeature.tabularFigures()],
                ),
              ),
          ],
          Text(status, style: white),
          Text(
            '화면은 꺼지지 않습니다.',
            style: white,
          ),
        ],
      );
    final q = running && serverError == null ? qr : null;
    return Container(
      color: Colors.black.withValues(alpha: 0.55),
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          if (q != null) ...[
            // 스캔이 잘 되도록 흰 바탕에 여백을 둔다.
            Container(
              key: const ValueKey('head-qr'),
              color: Colors.white,
              padding: const EdgeInsets.all(6),
              child: QrImageView(
                data: q,
                size: 150,
                padding: EdgeInsets.zero,
                backgroundColor: Colors.white,
              ),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(child: text),
        ],
      ),
    );
  }
}
