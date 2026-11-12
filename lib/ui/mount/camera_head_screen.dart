import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show MissingPluginException, PlatformException, SystemChrome, SystemUiMode;
import 'package:qr_flutter/qr_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../services/camera_head.dart';
import '../../services/head_camera.dart';
import '../../services/screen_wake.dart';
import '../kiosk.dart' show FullscreenMode;

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
///
/// 녹화 모드(시험용, docs/tedashi_video_plan_1112.md 0단계): 오른쪽 위 녹화 아이콘을 눌러 확인하면 켜진다. 스트림 프레임을
/// 초당 10장까지 반 크기 JPEG 로 이 기기에 계속 저장한다(소리 없음, 판독은 그대로). 기본 꺼짐이고 설정에 저장하지 않는다 —
/// 화면을 나가거나 앱을 다시 켜면 꺼져 있다.
///
/// 어두운 화면(2026-11-12, 거치 중 배터리·발열): 조작 기기가 붙어 있거나(최근 [dimClientWindow] 안에 요청) 녹화 중이고
/// [dimAfter] 동안 화면을 안 만지면, 미리보기를 그리지 않고 검은 화면 + 창 밝기 최저 + 시스템 막대 숨김으로 바꾼다.
/// 카메라·서버·녹화는 그대로 돈다(화면을 끄면 안드로이드가 카메라를 닫으므로 화면은 켜 둔다). 화면을 누르면 돌아오고,
/// 연결이 끊기면(요청이 끊기고 녹화도 아님) 저절로 돌아와 QR 을 보인다. 앱바 밝기 아이콘으로 끄고 켠다(기본 켬, 저장).
/// 테스트용: 어두운 화면 판단([_CameraHeadScreenState.shouldDim]).
abstract final class CameraHeadScreenStateForTest {
  static const shouldDim = _CameraHeadScreenState.shouldDim;
}

class CameraHeadScreen extends StatefulWidget {
  const CameraHeadScreen({super.key});

  @override
  State<CameraHeadScreen> createState() => _CameraHeadScreenState();
}

class _CameraHeadScreenState extends State<CameraHeadScreen> {
  static const String zoomPref = 'cameraHead.zoom';
  static const String tokenPref = 'cameraHead.token';
  static const String allowPairPref = 'cameraHead.allowPair';
  static const String dimPref = 'cameraHead.dim';
  static const List<double> zoomSteps = [1, 1.5, 2, 3, 4];

  /// 이만큼 화면을 안 만지면 어두운 화면으로.
  static const Duration dimAfter = Duration(seconds: 30);

  /// 이 안에 조작 기기 요청(/preview·/capture·/rec/frames)이 있었으면 "붙어 있음". 태블릿은 3초마다 부른다.
  static const Duration dimClientWindow = Duration(seconds: 15);

  /// 어두운 화면의 창 밝기(0~1).
  static const double dimBrightness = 0.01;

  // 어두운 화면.
  bool _dimEnabled = true;
  bool _dimmed = false;
  DateTime _lastTouchAt = DateTime.now();
  DateTime? _lastClientAt;
  Timer? _dimTimer;

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

  // 녹화 모드(시험용). 설정에 저장하지 않는다 — 앱을 다시 켜면 늘 꺼져 있다.
  /// 마지막으로 받은 녹화 상태(녹화 중이 아니어도 스트림 속도·남은 용량이 들어 있다). 1초마다 갱신.
  HeadRecordStatus? _rec;
  Timer? _recTimer;
  bool _recBusy = false;
  bool _recPolling = false;

  /// 켜기·끄기 때마다 는다 — 그 전에 떠난 상태 요청의 답은 버린다.
  int _recGen = 0;

  /// 녹화가 스스로 멈춘 까닭(용량 부족·오류). 사용자가 닫거나 다시 켤 때까지 보인다.
  String? _recStopMessage;

  bool get _recording => _rec?.recording == true;

  @override
  void initState() {
    super.initState();
    _server = CameraHeadServer(
      capture: _capture,
      preview: _preview,
      recordFrames: _recordFrames,
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
    _loadDim();
    _dimTimer = Timer.periodic(const Duration(seconds: 1), (_) => _tickDim());
  }

  @override
  void dispose() {
    _recTimer?.cancel();
    _dimTimer?.cancel();
    if (_dimmed) {
      ScreenWake.brightness(null);
      FullscreenMode.apply();
    }
    ScreenWake.keepOn(false);
    _server.stop();
    // 카메라를 멈추면 네이티브가 녹화도 끝낸다(record.json 마무리).
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

  Future<void> _loadDim() async {
    try {
      final v = (await SharedPreferences.getInstance()).getBool(dimPref);
      if (v != null && mounted) setState(() => _dimEnabled = v);
    } catch (_) {}
  }

  Future<void> _toggleDim() async {
    final next = !_dimEnabled;
    setState(() => _dimEnabled = next);
    _lastTouchAt = DateTime.now();
    try {
      await (await SharedPreferences.getInstance()).setBool(dimPref, next);
    } catch (_) {}
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(next
            ? '어두운 화면 켬: 조작 기기가 붙어 있거나 녹화 중이면 ${dimAfter.inSeconds}초 뒤 화면을 어둡게 합니다(카메라는 그대로)'
            : '어두운 화면 끔: 늘 미리보기를 보여 줍니다'),
      ));
  }

  /// 조작 기기 요청이 올 때마다(/preview·/capture·/rec/frames).
  void _noteClient() => _lastClientAt = DateTime.now();

  /// 지금 어둡게 할 때인가(순수 판단, 테스트용으로 static).
  static bool shouldDim({
    required bool enabled,
    required bool cameraReady,
    required bool recording,
    required DateTime now,
    required DateTime lastTouchAt,
    DateTime? lastClientAt,
  }) {
    if (!enabled || !cameraReady) return false;
    if (now.difference(lastTouchAt) < dimAfter) return false;
    final client = lastClientAt != null && now.difference(lastClientAt) < dimClientWindow;
    return client || recording;
  }

  void _tickDim() {
    if (!mounted) return;
    final want = shouldDim(
      enabled: _dimEnabled,
      cameraReady: _cam?.textureId != null,
      recording: _recording,
      now: DateTime.now(),
      lastTouchAt: _lastTouchAt,
      lastClientAt: _lastClientAt,
    );
    if (want != _dimmed) _setDimmed(want);
  }

  void _setDimmed(bool on) {
    setState(() => _dimmed = on);
    ScreenWake.brightness(on ? dimBrightness : null);
    if (on) {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    } else {
      FullscreenMode.apply();
    }
  }

  /// 화면을 만지면 시계를 다시 재고, 어두우면 돌아온다.
  void _touched() {
    _lastTouchAt = DateTime.now();
    if (_dimmed) _setDimmed(false);
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
    // 스트림 속도는 녹화를 안 켜도 보인다(12MP 스트림이 초당 몇 장 오는지 아직 잰 적이 없다).
    _recTimer?.cancel();
    _recTimer = Timer.periodic(const Duration(seconds: 1), (_) => _pollRecord());
  }

  Future<void> _pollRecord() async {
    final c = _cam;
    if (c == null || _recPolling) return;
    _recPolling = true;
    final gen = _recGen;
    try {
      final s = await c.recordStatus();
      // 그 사이 켜기·끄기를 눌렀으면 이 (묵은) 상태는 버린다.
      if (!mounted || gen != _recGen || _recBusy) return;
      final wasOn = _recording;
      setState(() {
        _rec = s;
        // 켜 둔 녹화가 꺼졌는데 사용자가 끈 것이 아니면 까닭을 남긴다.
        if (wasOn && !s.recording) _recStopMessage = s.stopMessage;
      });
    } catch (_) {
      // 상태를 못 받으면 다음 차례에 다시.
    } finally {
      _recPolling = false;
    }
  }

  void _snack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  /// 녹화 켜기(확인 한 번)·끄기.
  Future<void> _toggleRecord() async {
    final c = _cam;
    if (c == null || _recBusy) return;
    final on = _recording;
    if (!on) {
      final free = _rec?.freeBytes ?? -1;
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('녹화 켜기(시험용)'),
          content: Text(
            '카메라 프레임을 초당 10장까지 반 크기 사진으로 이 휴대폰에 계속 저장합니다. 소리는 녹음하지 않습니다.\n'
            '판독(촬영·미리보기)은 그대로 돕니다. 30분에 수 GB 를 쓰고, 남은 용량이 2GB 아래로 내려가면 스스로 멈춥니다.'
            '${free >= 0 ? '\n지금 남은 용량: ${HeadRecordStatus.gb(free)}' : ''}',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('녹화 켜기'),
            ),
          ],
        ),
      );
      if (ok != true || !mounted) return;
    }
    setState(() => _recBusy = true);
    _recGen++;
    try {
      final s = on ? await c.recordStop() : await c.recordStart();
      if (!mounted) return;
      setState(() {
        _rec = s;
        _recStopMessage = null;
      });
      if (!s.supported) {
        _snack('이 기기에서는 녹화를 쓸 수 없습니다(Android 전용)');
      } else if (on) {
        _snack('녹화 끔: 저장 ${s.saved}장 · 버림 ${s.dropped}장');
      } else {
        _snack('녹화 시작: ${s.dir ?? ''}');
      }
    } on PlatformException catch (e) {
      _snack('녹화를 ${on ? '끌' : '시작할'} 수 없습니다: ${e.message ?? e.code}');
    } catch (e) {
      _snack('녹화를 ${on ? '끌' : '시작할'} 수 없습니다: $e');
    } finally {
      if (mounted) setState(() => _recBusy = false);
    }
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
    _noteClient();
    final j = await _ready().jpeg(quality: 92, fresh: true);
    _noteFrame(j);
    return j.bytes;
  }

  /// 조작 기기가 /preview 를 부르면 최신 프레임을 긴 변 [longSide](기본 960)로 줄인 JPEG 로.
  /// 큰 요청(2000 이상, 판 상태 추적의 울기 모서리 읽기)은 패 무늬가 뭉개지지 않게 품질을 올린다.
  /// 태블릿 이어 받기(`/rec/frames`): 다 쓴 프레임 목록을 네이티브에서 받아 파일을 읽어 묶는다.
  /// 카메라가 없으면 빈 묶음(녹화한 적 없음). 읽다 사라진 파일(adb 로 지움 등)은 건너뛴다.
  Future<RecordBatch> _recordFrames(int after, int max) async {
    _noteClient();
    final c = _cam;
    if (c == null) return const RecordBatch();
    final r = await c.recordFrames(after: after, max: max);
    final dir = r.dir;
    if (dir == null) return RecordBatch(recording: r.recording);
    final frames = <RecordFrame>[];
    for (final ms in r.ms) {
      try {
        frames.add(RecordFrame(ms, await File('$dir/f_$ms.jpg').readAsBytes()));
      } on FileSystemException {
        // 건너뜀
      }
    }
    final name = dir.split('/').last;
    return RecordBatch(dir: name, recording: r.recording, latest: r.latest, remaining: r.remaining, frames: frames);
  }

  Future<PreviewFrame> _preview(int? longSide) async {
    _noteClient();
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
    final fps = _rec?.streamFps ?? 0;
    if (fps > 0) b.write(' ${fps.toStringAsFixed(1)}장/초');
    final err = _server.lastError;
    if (err != null) b.write(' · 오류: $err');
    return b.toString();
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (_) => _touched(),
      child: _dimmed ? _dimView() : _normalView(context),
    );
  }

  /// 어두운 화면: 미리보기(Texture)를 그리지 않는 검은 화면에 아주 흐린 한 줄. 같은 자리에 오래 두지 않게 1분마다 옮긴다.
  Widget _dimView() {
    final now = DateTime.now();
    const spots = [Alignment(-0.6, -0.5), Alignment(0.5, -0.1), Alignment(-0.3, 0.4), Alignment(0.4, 0.7)];
    final line = StringBuffer('헤드 동작 중');
    if (_recording) line.write(' · 녹화 ${_rec?.saved ?? 0}장');
    line.write(' · 누르면 화면');
    return Scaffold(
      key: const ValueKey('head-dim'),
      backgroundColor: Colors.black,
      body: Align(
        alignment: spots[now.minute % spots.length],
        child: Text(line.toString(), style: const TextStyle(color: Color(0xFF3A3A3A), fontSize: 13)),
      ),
    );
  }

  Widget _normalView(BuildContext context) {
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
            key: const ValueKey('head-record'),
            tooltip: _recording ? '녹화 중 (끄기)' : '녹화 켜기 (시험용)',
            icon: Icon(_recording ? Icons.fiber_manual_record : Icons.fiber_manual_record_outlined),
            color: _recording ? Colors.redAccent : null,
            onPressed: c != null && !_recBusy ? _toggleRecord : null,
          ),
          IconButton(
            key: const ValueKey('head-dim-toggle'),
            tooltip: _dimEnabled ? '어두운 화면 켬 (끄기)' : '어두운 화면 끔 (켜기)',
            icon: Icon(_dimEnabled ? Icons.brightness_low : Icons.brightness_high),
            onPressed: _toggleDim,
          ),
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
                // 녹화 표시(줌 아래). QR 을 숨겨도 늘 보인다.
                if (_recording || _recStopMessage != null)
                  Positioned(
                    left: 8,
                    right: 8,
                    top: 56,
                    child: Align(
                      alignment: Alignment.topLeft,
                      child: _RecordBanner(
                        status: _rec ?? const HeadRecordStatus(),
                        stopMessage: _recording ? null : _recStopMessage,
                        onClose: () => setState(() => _recStopMessage = null),
                      ),
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

/// 녹화 중: 빨간 띠에 저장 장수·버린 장수·저장 속도·스트림 속도·남은 용량. 스스로 멈췄으면: 까닭과 닫기 단추.
class _RecordBanner extends StatelessWidget {
  final HeadRecordStatus status;

  /// null 이면 녹화 중 표시.
  final String? stopMessage;
  final VoidCallback onClose;
  const _RecordBanner({required this.status, required this.stopMessage, required this.onClose});

  @override
  Widget build(BuildContext context) {
    final s = status;
    final counts = '저장 ${s.saved}장 · 버림 ${s.dropped}장';
    const style = TextStyle(
      color: Colors.white,
      fontSize: 13,
      fontFeatures: [ui.FontFeature.tabularFigures()],
    );
    final stop = stopMessage;
    if (stop != null) {
      return Material(
        key: const ValueKey('head-record-stopped'),
        color: Colors.orange.shade900.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 2, 2, 2),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(child: Text('녹화가 멈췄습니다 — $stop ($counts)', style: style)),
              IconButton(
                tooltip: '닫기',
                icon: const Icon(Icons.close, size: 18, color: Colors.white),
                visualDensity: VisualDensity.compact,
                onPressed: onClose,
              ),
            ],
          ),
        ),
      );
    }
    final free = s.freeBytes >= 0 ? ' · 남은 ${HeadRecordStatus.gb(s.freeBytes)}' : '';
    return Container(
      key: const ValueKey('head-record-on'),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.red.shade700.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.fiber_manual_record, size: 14, color: Colors.white),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              '녹화 중 · $counts · 저장 ${s.savedFps.toStringAsFixed(1)}장/초'
              ' · 스트림 ${s.streamFps.toStringAsFixed(1)}장/초$free',
              style: style,
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
