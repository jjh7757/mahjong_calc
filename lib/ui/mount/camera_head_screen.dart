import 'dart:async';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart' show compute;
import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../services/camera_head.dart';
import '../../services/screen_wake.dart';
import '../../services/yuv_jpeg.dart';

/// 카메라 헤드 모드. 이 기기를 테이블 위에 고정해 두고, 같은 Wi-Fi 의 다른 기기(태블릿·노트북)가
/// 거치 촬영 화면에서 이 화면의 QR 을 스캔해(또는 "원격 카메라 주소" 에 적어) 사진을 받아 간다.
/// 이 화면은 미리보기·줌·접속 QR 만 보여 준다. 판독·대국 기록은 조작 기기 쪽에서 한다.
///
/// QR 에는 주소와 토큰이 들어 있다. 토큰은 기기에 저장해 다시 열어도 같고(한 번 스캔하면 끝),
/// 오른쪽 위 "새 QR" 로 바꾸면 이전에 스캔한 기기는 더 이상 찍을 수 없다.
///
/// 미리보기는 자르지 않고(조준용) 가능한 한 크게 띄우며, 주소·상태는 그 위에 반투명으로 겹친다.
/// 줌은 촬영 사진에도 적용된다. 패 최소 상자는 뺐다(고정 거치라 손으로 맞출 일이 없음, 2026-10-27 사용자).
///
/// `/preview` 는 셔터 없이 미리보기 프레임(이미지 스트림)에서 작은 JPEG 를 만들어 준다(조작 기기의 테이블 화면 배경).
/// 스트림은 처음 요청에 켜고, 30초 동안 요청이 없으면 끈다. 촬영 중에는 스트림을 멈춰 사진 해상도를 지킨다.
class CameraHeadScreen extends StatefulWidget {
  const CameraHeadScreen({super.key});

  @override
  State<CameraHeadScreen> createState() => _CameraHeadScreenState();
}

class _CameraHeadScreenState extends State<CameraHeadScreen>
    with WidgetsBindingObserver {
  static const String zoomPref = 'cameraHead.zoom';
  static const String tokenPref = 'cameraHead.token';
  static const List<double> zoomSteps = [1, 1.5, 2, 3, 4];

  CameraController? _cam;
  String? _camError;
  late final CameraHeadServer _server;
  String? _serverError;
  List<String> _addresses = const [];
  double _zoom = 1;
  double _maxZoom = 1;
  bool _showInfo = true;

  /// 미리보기 스트림의 마지막 프레임과 상태.
  CameraImage? _frame;
  bool _streaming = false;
  bool _capturing = false;
  PreviewFrame? _lastPreview;
  DateTime? _previewAskedAt;
  Timer? _idleTimer;
  static const Duration _previewIdle = Duration(seconds: 30);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
    _idleTimer = Timer.periodic(const Duration(seconds: 5), (_) => _stopStreamIfIdle());
  }

  @override
  void dispose() {
    _idleTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    ScreenWake.keepOn(false);
    _server.stop();
    _cam?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final c = _cam;
    if (c == null) return;
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      c.dispose();
      _cam = null;
      _streaming = false;
      _frame = null;
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
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
    } catch (_) {}
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
    try {
      final cams = await availableCameras();
      if (cams.isEmpty) {
        if (mounted) setState(() => _camError = '카메라가 없습니다');
        return;
      }
      final back = cams.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cams.first,
      );
      final c = CameraController(
        back,
        ResolutionPreset.max,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await c.initialize();
      double maxZoom = 1;
      try {
        maxZoom = await c.getMaxZoomLevel();
      } catch (_) {}
      if (!mounted) {
        c.dispose();
        return;
      }
      setState(() {
        _cam = c;
        _camError = null;
        _maxZoom = maxZoom;
      });
      await _applyZoom(_zoom, save: false);
    } catch (e) {
      if (mounted) setState(() => _camError = '카메라를 열 수 없습니다: $e');
    }
  }

  Future<void> _applyZoom(double z, {bool save = true}) async {
    final c = _cam;
    final upper = _maxZoom < 1 ? 1.0 : _maxZoom;
    final clamped = z.clamp(1.0, upper).toDouble();
    if (c != null && c.value.isInitialized) {
      try {
        await c.setZoomLevel(clamped);
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

  /// 조작 기기가 /capture 를 부르면 여기서 찍는다.
  Future<Uint8List> _capture() async {
    final c = _cam;
    if (c == null || !c.value.isInitialized) {
      throw StateError('카메라 헤드의 카메라가 준비되지 않았습니다');
    }
    _capturing = true;
    try {
      // 스트림을 켠 채 찍으면 기기에 따라 사진 해상도가 낮아질 수 있어 잠깐 멈춘다. 다음 /preview 가 다시 켠다.
      await _stopStream();
      final x = await c.takePicture();
      return await x.readAsBytes();
    } finally {
      _capturing = false;
    }
  }

  /// 조작 기기가 /preview 를 부르면 미리보기 프레임을 JPEG 로 바꿔 준다(기본 긴 변 960, [longSide] 로 더 크게).
  Future<PreviewFrame> _preview(int? longSide) async {
    _previewAskedAt = DateTime.now();
    final c = _cam;
    if (c == null || !c.value.isInitialized) {
      throw StateError('카메라 헤드의 카메라가 준비되지 않았습니다');
    }
    if (_capturing) {
      final last = _lastPreview;
      if (last != null) return last;
      throw StateError('촬영 중');
    }
    if (!_streaming) {
      _frame = null;
      await c.startImageStream((im) => _frame = im);
      _streaming = true;
    }
    // 첫 프레임을 기다린다(보통 수십 ms).
    for (var i = 0; i < 40 && _frame == null; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    final im = _frame;
    if (im == null) throw StateError('미리보기 프레임이 아직 없습니다');
    final frame = YuvFrame(
      width: im.width,
      height: im.height,
      planes: [for (final p in im.planes) p.bytes],
      rowStrides: [for (final p in im.planes) p.bytesPerRow],
      pixelStrides: [for (final p in im.planes) p.bytesPerPixel ?? 1],
    );
    final jpeg = await compute(yuvFrameToJpegSized, (frame, longSide ?? 960));
    final out = PreviewFrame(jpeg, frameWidth: im.width, frameHeight: im.height);
    _lastPreview = out;
    return out;
  }

  Future<void> _stopStream() async {
    final c = _cam;
    if (!_streaming || c == null) return;
    _streaming = false;
    _frame = null;
    try {
      await c.stopImageStream();
    } catch (_) {}
  }

  void _stopStreamIfIdle() {
    final t = _previewAskedAt;
    if (_streaming && (t == null || DateTime.now().difference(t) > _previewIdle)) {
      unawaited(_stopStream());
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
    final Widget preview = c != null && c.value.isInitialized
        ? Center(child: CameraPreview(c))
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
                // 줌 선택. 촬영 사진에도 적용된다.
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
  final String status;
  const _InfoPanel({
    required this.serverError,
    required this.running,
    required this.urls,
    required this.qr,
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
