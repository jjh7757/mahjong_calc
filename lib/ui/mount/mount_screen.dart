import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart' show compute, kIsWeb;
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../engine/calculator.dart' as engine;
import '../../game/game.dart';
import '../../game/game_store.dart';
import '../../services/camera_head.dart';
import '../../services/capture_log.dart';
import '../../services/recognizer_client.dart';
import '../../services/volume_keys.dart';
import '../../table/auto_record.dart';
import '../../table/corner_change.dart';
import '../../table/cropper.dart';
import '../../table/fixed_layout.dart';
import '../../table/frame_recorder.dart';
import '../../table/grid_zones.dart';
import '../../table/merge.dart';
import '../../table/observation.dart';
import '../../table/seat_map.dart';
import '../../table/shot_image.dart';
import '../../table/table_layout.dart';
import '../../table/table_reader.dart';
import '../../table/table_reading.dart';
import '../../table/river_change.dart';
import '../../table/river_tracker.dart';
import '../../table/scene_shift.dart';
import '../../table/tracker.dart';
import '../game/game_screen.dart';
import '../game/record_edit.dart';
import '../game/settlement_screen.dart';
import '../hand_editor.dart';
import '../input_screen.dart';
import '../kiosk.dart';
import '../result_screen.dart';
import '../score_table_screen.dart';
import '../settings_screen.dart';
import '../tile_view.dart';
import 'capture_label.dart';
import 'grid_editor.dart';
import 'qr_scan_screen.dart';
import 'score_panel.dart';

Future<Uint8List> _shrinkInIsolate(Uint8List o) => compute(shrinkForLocate, o);
Future<List<Uint8List>> _cropInIsolate(Uint8List o, List<CropSpec> s) => compute(cropMany, (o, s));
Future<ShotAnalysis> _analyzeInIsolate(Uint8List small, FixedTable f) => compute(analyzeShot, (small, f));
Future<ShotAnalysis> _analyzeGridInIsolate(Uint8List small, GridZones g) => compute(analyzeGridShot, (small, g));

/// 격자 판독은 원본을 isolate 하나에서 한 번만 디코딩한다(웹은 isolate 를 띄워 둘 수 없어 같은 스레드).
Future<ShotImage> _openShot(Uint8List o) async => kIsWeb ? DirectShotImage(o) : await IsolateShotImage.open(o);

/// 무거운 디코딩·크롭은 isolate 에서.
const ImageOps _isolateOps = ImageOps(
  shrink: _shrinkInIsolate,
  cropMany: _cropInIsolate,
  analyze: _analyzeInIsolate,
  analyzeGrid: _analyzeGridInIsolate,
  openShot: _openShot,
);

/// 거치 촬영 모드. 폰을 테이블 위에 고정해 두고 화료 때 한 장 찍으면
/// 서버가 구역을 찾고(locate) 손패·중앙을 읽어, 대국 기록과 합쳐 결과 화면으로 간다.
/// 대국 기록 중에만 쓸 수 있다(자풍·장풍·본장·자리 배치를 기록에서 가져온다).
/// 사진 가운데에는 대국 점수판([TableScorePanel])을 겹친다.
///
/// 키오스크(태블릿 가로)에서는 대국 중 첫 화면([isHome])이다. 점수 계산은 따로 열고,
/// "대국에 반영" 하면 이 화면으로 돌아온다.
///
/// 사진 출처는 둘 중 하나다.
/// - 이 기기의 카메라(기본).
/// - 원격 카메라: 같은 Wi-Fi 의 다른 기기가 "카메라 헤드" 화면을 켜 두면 그 주소에서 받아 온다
///   (메뉴 "카메라 헤드 QR 스캔" 또는 "원격 카메라 주소", 주소·토큰은 기기에 저장).
///   이때 이 기기는 화면·조작만 맡는다.
class MountScreen extends StatefulWidget {
  final HandEditor editor;

  /// 앱 첫 화면으로 쓰는지(키오스크 대국 중). 그러면 뒤로 갈 화면이 없어 손패 고치기는 계산 화면을 새로 연다.
  final bool isHome;

  /// 열자마자 갤러리를 띄울지(폰 계산기의 "테이블 전체 사진").
  final bool openGallery;
  const MountScreen({super.key, required this.editor, this.isHome = false, this.openGallery = false});

  @override
  State<MountScreen> createState() => _MountScreenState();
}

class _MountScreenState extends State<MountScreen> with WidgetsBindingObserver {
  CameraController? _cam;
  String? _camError;
  TableLayout? _lastLayout;
  bool _busy = false;

  /// 카메라가 고정이면 처음 locate 한 구역을 다음 촬영에 다시 쓴다([FixedTable]). 화면을 닫았다 열어도 유지하고,
  /// 카메라 출처를 바꾸면 버린다. 움직임은 촬영마다 펠트 모양으로 확인한다.
  static FixedTable? _fixed;

  /// 미리 그은 격자 구역([GridZones]). 켜져 있으면 locate 없이 칸마다 잘라 읽는다(기본).
  /// 끄면 예전처럼 locate(+[_fixed]) 로 읽는다.
  GridZones _grid = GridZones.initial;
  bool _useGrid = true;
  static const String gridPref = 'mount.grid';
  static const String useGridPref = 'mount.useGrid';

  /// 격자를 맞추는 중이면 편집 전 값(취소용). null 이면 편집 중 아님.
  GridZones? _gridBeforeEdit;

  /// 갤러리에서 고른 사진(읽기 전)과 그 가로/세로 비율. 있으면 이 사진 위에서 격자를 맞춘 뒤 읽는다.
  /// 갤러리 사진은 거치 카메라와 찍은 자리가 달라 저장된 격자가 맞지 않는다. 맞춘 격자는 이 한 장에만 쓰고 저장하지 않는다.
  Uint8List? _galleryShot;
  double? _galleryAspect;

  /// 촬영 기록(원본·크롭·응답)을 Download/mahjong_calc 에 남길지(데스크톱은 사용자 다운로드 폴더).
  bool _logEnabled = true;

  /// 원격 카메라(카메라 헤드) 주소. null 이면 이 기기의 카메라를 쓴다.
  String? _remoteUrl;
  static const String remoteUrlPref = 'mount.remoteUrl';

  /// 카메라 헤드 토큰(QR 에 들어 있음). 없으면 카메라 헤드가 401 로 거절한다.
  String? _remoteToken;
  static const String remoteTokenPref = 'mount.remoteToken';

  /// 거치 높이(cm, 테이블 면에서 카메라까지). 실험 기록용. 사용자가 적는다.
  int? _heightCm;
  static const String heightPref = 'mount.heightCm';

  /// 원격 카메라일 때 미리보기 대신 보여 줄 마지막 사진과 그 크기.
  Uint8List? _lastShot;
  int? _captureW;
  int? _captureH;

  /// 실제 촬영 해상도의 긴 변(px). 첫 촬영 뒤에 안다(촬영 기록용).
  int? _captureLongSide;

  /// 촬영 사진의 가로·세로. 미리보기(배경)는 비율이 다를 수 있어, 알고 나면 이 비율로 가운데를 잘라 보여 준다(격자와 맞게).
  int? _photoW;
  int? _photoH;

  /// 카메라 헤드 미리보기를 몇 초마다 받아 배경으로 쓴다(테이블 화면이 작혼처럼 살아 있게).
  Timer? _bgTimer;
  bool _bgFetching = false;

  /// 헤드가 미리보기를 못 주거나(예전 앱) 토큰을 거절하면 더 묻지 않는다. 주소를 바꾸면 다시 시도.
  bool _bgStopped = false;

  /// 마지막 헤드 미리보기 오류(없으면 연결됨). 테이블 화면 "헤드" 버튼이 빨강/초록으로 보여 주고, 누르면 다시 붙거나 QR 스캔.
  String? _headError;

  /// 헤드 미리보기 스트림의 원 프레임 긴 변(px). 해상도 게이트(울기 모서리를 미리보기로 읽을 수 있나) 판단용. 모르면 null.
  int? _previewFrameLongSide;

  /// 판 상태 추적(울기 미리 읽기, docs/state_tracking_design.md). 격자 + 카메라 헤드일 때만 돈다.
  /// 배경 미리보기 프레임마다 모서리 통계를 내고, 변화가 확정되면 모서리만 잘라 /v2/corner 로 읽어 둔다.
  MeldTracker? _tracker;

  /// 2단계: 강(마지막 버림패 위치 → 방총자·론 패 힌트)·리치봉(띠 변화 → /v2/sticks 두 번 일치) 추적. 같은 프레임을 쓴다.
  RiverTracker? _riverTracker;
  /// 기본 켬(2026-10-29, 사용자: 터치 없는 자동화). 격자 + 카메라 헤드가 아니면 켜져 있어도 돌지 않는다.
  bool _trackingEnabled = true;
  static const String trackingPref = 'mount.tracking';

  /// 그림자 모드(실험): 추적 자리의 화료 때 손패 전용과 자리 전체를 같은 사진으로 동시에 읽어 둘 다 기록한다.
  bool _shadow = false;
  static const String shadowPref = 'mount.shadow';

  /// 격자 판독 전에 펠트 네 모서리로 사진을 펴서 작탁만 남기고 표준 격자로 나눈다(더보기에서 켬, 기본 끔).
  /// 펠트를 못 찾으면 맞춘 격자 그대로. 사용자 제안(2026-10-28 "처음 자를 때 작탁만"), `lib/table/rectify.dart`.
  /// 기본 끔: B·C·D 앱 흐름 같은 순간 24쌍에서 점수 정답 23 → 12·자동 반영 23 → 8·중앙 +3초(펴기 2.8초)였다(metrics 표 1).
  bool _rectify = false;
  static const String rectifyPref = 'mount.rectify';

  /// 이 판의 왕패(도라 산) 상자. 판 상태 추적이 새 판의 첫 버림패(패산이 다 올라오고 도라를 뒤집은 뒤)를 보면 `/v2/wall` 을
  /// 한 번 부르고(판당 1회, 3초마다 부르지 않는다), 더보기 "도라 산 찾기" 로도 부른다. "격자 편집" 에서 주황 상자를 끌어 고칠 수 있고,
  /// 판이 바뀌면 버린다. 리치 아닌 화료 때 이 상자를 잘라 도라를 읽는다(`readGrid(wall:)`).
  WallZone? _wall;
  bool _wallBusy = false;
  bool _wallTried = false;

  /// 판 시작 자동 찾기가 실패하면 [_wallRetryGap] 뒤 한 번 더(같은 판일 때만). 매장에서 손 가림·조명으로 한 번 놓친 판을
  /// 건지려고(2026-10-29). 수동 "도라 산 찾기" 는 세지 않는다.
  int _wallAutoTries = 0;
  Timer? _wallRetryTimer;
  static const int _wallMaxAutoTries = 2;
  static const Duration _wallRetryGap = Duration(seconds: 30);

  /// 갤러리 사진에서 "자동 맞추기" 로 찾은 도라 산(그 사진 한 장에만 쓴다).
  WallZone? _galleryWall;

  /// "자동 맞추기"(처음 설정 틀 `/v2/setup` + 도라 산 `/v2/wall`)를 부르는 중.
  bool _setupBusy = false;

  /// 격자 자동 맞추기는 **카메라를 놓을 때 한 번**(2026-10-29 사용자: "대국마다 할 필요가 있나" — 판마다 잡는 것은 도라 산만).
  /// 격자를 저장할 때 어느 카메라로 잡았는지([gridSourcePref] = 헤드 주소 또는 'local')를 같이 적고, 테이블 화면에서
  /// 카메라가 준비됐을 때 저장된 격자의 카메라와 지금 카메라가 다르면(처음 설치, 새 헤드 QR, 헤드 ↔ 이 기기 카메라) 자동 맞추기를
  /// 돈다. 같은 카메라면 저장된 격자(사용자가 고친 것 포함)를 그대로 쓴다. 네 자리 손패를 못 찾으면(패를 아직 안 돌렸을 때)
  /// [_autoSetupRetryGap] 뒤 다시, 최대 [_autoSetupMaxTries]회. 맞으면 격자를 저장한다. 같은 카메라엔 앱이 켜져 있는 동안 한 번만.
  /// 같은 주소의 폰을 다른 자리에 다시 거치한 경우는 못 알아보므로 "격자 편집" 의 "자동 맞추기" 를 누른다.
  bool _autoSetupOnStart = true;
  static const String autoSetupPref = 'mount.autoSetupOnStart';
  static const String gridSourcePref = 'mount.gridSource';
  String? _gridSource;
  static String? _autoSetupDoneFor;
  int _autoSetupTries = 0;
  Timer? _autoSetupTimer;

  /// 볼륨키 핸들러(등록·해제에 같은 것을 넘긴다).
  late final VoidCallback _volumeShoot = _shoot;
  /// 10회 × 20초 ≈ 3분 반: 대국 시작을 누른 뒤 패가 올라오고 배패가 끝날 때까지 기다릴 수 있게(10-29 처음엔 3회 ≈ 1분).
  static const int _autoSetupMaxTries = 10;
  static const Duration _autoSetupRetryGap = Duration(seconds: 20);

  /// 지금 판(국·본장·기록 수). 바뀌면 추적을 비운다.
  String? _trackRoundKey;
  String? _trackDir;
  bool _trackBusy = false;
  int _trackSeq = 0;

  /// 배경 프레임 중 추적 변화 주변만 모아 판마다 `<시각>_track/frames_##.zip` 으로(촬영 기록이 켜졌을 때, 2026-10-29).
  final FrameRecorder _frames = FrameRecorder();
  int _framesPart = 0;
  int _meldEventsSeen = 0;
  int _riverEventsSeen = 0;

  /// 미리보기 스트림이 이 긴 변 이상이면 모서리 읽기용 사진도 고해상 미리보기로(셔터 없음), 아니면 촬영.
  static const int _trackPreviewMinLongSide = 1600;
  static const Duration _bgInterval = Duration(seconds: 3);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadSource();
    VolumeKeys.listen(_volumeShoot);
    CaptureLog.isEnabled().then((v) {
      if (mounted) setState(() => _logEnabled = v);
    });
    AutoRecordStore.load().then((v) {
      if (mounted) setState(() => _autoRecord = v);
    });
    if (widget.openGallery) WidgetsBinding.instance.addPostFrameCallback((_) => _pickFromGallery());
  }

  /// 판독이 확실하면 결과 화면에서 [autoRecordDelay] 뒤 대국에 자동 반영(기본 켬, 룰 설정·더보기에서 끔).
  static const autoRecordDelay = Duration(seconds: 10);
  bool _autoRecord = true;

  @override
  void dispose() {
    _flushFrames('dispose');
    _bgTimer?.cancel();
    _autoSetupTimer?.cancel();
    _wallRetryTimer?.cancel();
    VolumeKeys.stop(_volumeShoot);
    WidgetsBinding.instance.removeObserver(this);
    _cam?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final paused = state == AppLifecycleState.inactive || state == AppLifecycleState.paused;
    // 배경 미리보기는 화면이 안 보일 때만 쉰다. inactive 는 데스크톱에서 창 포커스만 잃어도 오므로 계속 받는다.
    if (state == AppLifecycleState.paused || state == AppLifecycleState.hidden) {
      _bgTimer?.cancel();
      _bgTimer = null;
    } else if (state == AppLifecycleState.resumed || state == AppLifecycleState.inactive) {
      _startBg();
    }
    final c = _cam;
    if (paused) {
      if (c != null) {
        c.dispose();
        _cam = null;
      }
    } else if (state == AppLifecycleState.resumed && c == null && _remoteUrl == null && _camError == null) {
      // 일시정지에서 버린 카메라를 다시 연다(예전엔 _cam == null 이면 먼저 돌아가 복귀 뒤 카메라가 영영 안 열렸다, 2026-10-30 점검).
      _initCamera();
    }
  }

  /// 원격 카메라면 배경 미리보기 받기를 시작한다(이미 돌고 있으면 그대로).
  void _startBg() {
    if (_remoteUrl == null || _bgTimer != null) return;
    _bgTimer = Timer.periodic(_bgInterval, (_) => _tickBg());
    _tickBg();
  }

  void _stopBg() {
    _bgTimer?.cancel();
    _bgTimer = null;
  }

  Future<void> _tickBg() async {
    final url = _remoteUrl;
    if (!mounted || url == null || _busy || _bgFetching || _bgStopped) return;
    // 계산·결과 화면이 위에 있으면 쉰다.
    if (ModalRoute.of(context)?.isCurrent == false) return;
    _bgFetching = true;
    final cam = RemoteCamera(url, token: _remoteToken, timeout: const Duration(seconds: 4));
    try {
      final p = await cam.preview();
      if (!mounted || _busy) return;
      _previewFrameLongSide = p.frameLongSide;
      setState(() {
        _lastShot = p.bytes;
        _headError = null;
      });
      await _measureCapture(p.bytes, capture: false);
      _maybeAutoSetup();
      await _trackFrame(p.bytes);
    } on RemoteCameraException catch (e) {
      // 예전 헤드 앱(404)이나 토큰 거절이면 그만 묻는다. 연결 오류는 다음 차례에 다시.
      if (e.unsupported || e.unauthorized) _bgStopped = true;
      if (mounted) setState(() => _headError = e.message);
    } catch (e) {
      if (mounted) setState(() => _headError = '연결 안 됨 ($e)');
    } finally {
      cam.close();
      _bgFetching = false;
    }
  }

  /// 저장된 원격 카메라 주소를 읽고, 없으면 이 기기의 카메라를 연다.
  Future<void> _loadSource() async {
    String? url;
    try {
      final p = await SharedPreferences.getInstance();
      url = p.getString(remoteUrlPref);
      _remoteToken = p.getString(remoteTokenPref);
      _heightCm = p.getInt(heightPref);
      _useGrid = p.getBool(useGridPref) ?? true;
      _trackingEnabled = p.getBool(trackingPref) ?? true;
      _autoSetupOnStart = p.getBool(autoSetupPref) ?? true;
      _gridSource = p.getString(gridSourcePref);
      _shadow = p.getBool(shadowPref) ?? false;
      _rectify = p.getBool(rectifyPref) ?? false;
      final g = p.getString(gridPref);
      if (g != null) _grid = GridZones.fromJson(jsonDecode(g) as Map<String, dynamic>) ?? GridZones.initial;
    } catch (_) {}
    if (!mounted) return;
    if (url != null && url.isNotEmpty) {
      setState(() => _remoteUrl = url);
      _startBg();
    } else {
      await _initCamera();
    }
  }

  /// 원격 카메라 주소·토큰을 저장한다. [input] 에 `?t=토큰` 이 있으면 [token] 보다 앞선다.
  /// [input] 이 비면 이 기기 카메라로 돌아간다. 저장했으면 true.
  Future<bool> _setRemoteUrl(String input, {String? token}) async {
    final link = CameraHeadLink.parse(input);
    if (input.trim().isNotEmpty && link == null) {
      _toast('주소를 알아볼 수 없습니다: ${input.trim()}');
      return false;
    }
    final url = link?.baseUrl ?? '';
    final t = link?.token ?? token?.trim();
    final tok = url.isEmpty || t == null || t.isEmpty ? null : t;
    try {
      final p = await SharedPreferences.getInstance();
      if (url.isEmpty) {
        await p.remove(remoteUrlPref);
      } else {
        await p.setString(remoteUrlPref, url);
      }
      if (tok == null) {
        await p.remove(remoteTokenPref);
      } else {
        await p.setString(remoteTokenPref, tok);
      }
    } catch (_) {}
    if (!mounted) return false;
    _remoteToken = tok;
    _fixed = null;
    _bgStopped = false;
    if (url.isEmpty) {
      _stopBg();
      setState(() {
        _remoteUrl = null;
        _lastShot = null;
      });
      await _initCamera();
    } else {
      _cam?.dispose();
      setState(() {
        _cam = null;
        _camError = null;
        _remoteUrl = url;
      });
      _startBg();
    }
    return true;
  }

  /// 카메라 헤드 화면의 QR 을 스캔해 주소·토큰을 저장하고, 바로 연결을 확인한다.
  Future<void> _scanQr() async {
    if (_busy) return;
    // 스캐너가 카메라를 쓰므로 이 화면의 카메라는 닫아 둔다.
    final cam = _cam;
    if (cam != null) {
      setState(() => _cam = null);
      await cam.dispose();
    }
    if (!mounted) return;
    final link = await Navigator.of(context)
        .push<CameraHeadLink>(MaterialPageRoute(builder: (_) => const QrScanScreen()));
    if (!mounted) return;
    if (link == null) {
      if (_remoteUrl == null) await _initCamera();
      return;
    }
    if (!await _setRemoteUrl(link.baseUrl, token: link.token)) return;
    await _checkRemote();
  }

  /// 저장한 원격 카메라에 /status 로 붙어 보고 결과를 알린다(찍지는 않는다).
  Future<void> _checkRemote() async {
    final url = _remoteUrl;
    if (url == null) return;
    final cam = RemoteCamera(url, token: _remoteToken, timeout: const Duration(seconds: 5));
    try {
      await cam.status();
      _toast('카메라 헤드에 연결했습니다 ($url)');
    } on RemoteCameraException catch (e) {
      _toast('저장했지만 연결 확인 실패: ${e.message}', long: true);
    } finally {
      cam.close();
    }
  }

  bool _camOpening = false;

  Future<void> _initCamera() async {
    if (_remoteUrl != null || _camOpening) return;
    _camOpening = true;
    try {
      final cams = await availableCameras();
      if (cams.isEmpty) {
        if (mounted) {
          setState(() => _camError = '카메라가 없습니다. 갤러리 사진으로 시험할 수 있습니다');
        }
        return;
      }
      final back = cams.firstWhere((c) => c.lensDirection == CameraLensDirection.back, orElse: () => cams.first);
      final c = CameraController(back, ResolutionPreset.max, enableAudio: false);
      await c.initialize();
      if (!mounted) {
        c.dispose();
        return;
      }
      setState(() {
        _cam = c;
        _camError = null;
      });
      _maybeAutoSetup();
    } catch (e) {
      if (mounted) setState(() => _camError = '카메라를 열 수 없습니다: $e');
    } finally {
      _camOpening = false;
    }
  }

  /// 대국 시작 직후 자동 맞추기 한 번(조건은 [_autoSetupOnStart] 설명). 카메라가 준비될 때마다 불리고, 조건이 맞을 때만 돈다.
  /// 지금 카메라의 정체(격자를 어느 카메라로 잡았는지 적어 둘 값).
  String get _cameraId => _remoteUrl ?? 'local';

  void _maybeAutoSetup() {
    final g = gameStore.current;
    if (!mounted || !widget.isHome || !_autoSetupOnStart || !_useGrid) return;
    if (g == null || g.isOver) return;
    if (_busy || _setupBusy || _gridBeforeEdit != null || _galleryShot != null) return;
    if (_cam == null && _remoteUrl == null) return;
    // 이 카메라로 이미 잡은(또는 사용자가 저장한) 격자가 있으면 그대로 쓴다.
    final cam = _cameraId;
    if (_gridSource == cam || _autoSetupDoneFor == cam) return;
    _autoSetupDoneFor = cam;
    _autoSetupTries = 0;
    unawaited(_autoSetupAttempt());
  }

  Future<void> _autoSetupAttempt() async {
    if (!mounted) return;
    if (_busy || _setupBusy || _gridBeforeEdit != null || _galleryShot != null) {
      // 촬영·편집 중이면 횟수를 세지 않고 미룬다(여기서 끝내면 남은 재시도가 조용히 사라진다, 2026-10-30 점검).
      _autoSetupTimer?.cancel();
      _autoSetupTimer = Timer(_autoSetupRetryGap, () => unawaited(_autoSetupAttempt()));
      return;
    }
    _autoSetupTries++;
    final last = _autoSetupTries >= _autoSetupMaxTries;
    final ok = await _autoSetup(auto: true, lastTry: last);
    if (!mounted || ok || last) return;
    _autoSetupTimer?.cancel();
    _autoSetupTimer = Timer(_autoSetupRetryGap, () => unawaited(_autoSetupAttempt()));
  }

  // ---------------- 입력 ----------------

  Future<void> _shoot() async {
    if (_busy || !mounted) return;
    // 볼륨키는 위에 다른 화면(결과·입력·설정)이 떠 있어도 들어온다: 이 화면이 맨 위이고 대국 중일 때만 찍는다
    // (2026-10-30 점검: 결과 화면 위에 결과 화면이 또 쌓이고 자동 반영 pop 이 엉뚱한 화면을 닫을 수 있었다).
    if (ModalRoute.of(context)?.isCurrent == false) return;
    if (widget.isHome) {
      final g = gameStore.current;
      if (g == null || g.isOver) return;
    }
    final remote = _remoteUrl;
    if (remote != null) {
      await _shootRemote(remote);
      return;
    }
    final c = _cam;
    if (c == null || !c.value.isInitialized) return;
    try {
      final x = await c.takePicture();
      final bytes = await x.readAsBytes();
      if (_captureLongSide == null) await _measureCapture(bytes);
      await _process(bytes, setup: _setup('local', zoom: 1));
    } on CameraException catch (e) {
      _toast('촬영 실패: ${e.description ?? e.code}');
    }
  }

  /// 카메라 헤드에 찍어 달라고 하고, 받은 사진을 미리보기 자리에 보여 준 뒤 판독한다([read] 가 false 면 보여 주기만).
  Future<void> _shootRemote(String url, {bool read = true}) async {
    // 화료 직전까지의 프레임을 먼저 남긴다(판독 중 앱이 닫혀도 남게).
    if (read) _flushFrames('capture');
    setState(() => _busy = true);
    final cam = RemoteCamera(url, token: _remoteToken);
    final RemoteShot shot;
    try {
      shot = await cam.capture();
    } on RemoteCameraException catch (e) {
      if (mounted) setState(() => _busy = false);
      if (e.unauthorized) {
        _toastScan(e.message);
      } else {
        _toast(e.message, long: true);
      }
      return;
    } finally {
      cam.close();
    }
    if (!mounted) return;
    setState(() {
      _lastShot = shot.bytes;
      _busy = false;
    });
    await _measureCapture(shot.bytes);
    if (read) await _process(shot.bytes, setup: _setup('remote', zoom: shot.zoom));
  }

  Future<void> _saveGrid() async {
    _tracker = null; // 격자가 바뀌면 패 한 장 비율·기준이 달라진다.
    _riverTracker = null;
    _shiftGate.reset();
    _gridSource = _cameraId;
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(gridPref, jsonEncode(_grid.toJson()));
      await p.setBool(useGridPref, _useGrid);
      await p.setString(gridSourcePref, _gridSource!);
    } catch (_) {}
  }

  /// 격자 맞추기 중 아래 버튼 줄: 원격이면 사진 받기, 초기값, 취소, 저장.
  Widget _gridEditBar() {
    final remote = _remoteUrl;
    if (_galleryShot != null) {
      return Wrap(
        spacing: 8,
        runSpacing: 4,
        alignment: WrapAlignment.end,
        children: [
          _autoSetupButton(),
          TextButton(onPressed: () => setState(() => _grid = GridZones.initial), child: const Text('초기값')),
          TextButton(onPressed: _busy ? null : _cancelGallery, child: const Text('취소')),
          FilledButton(
            key: const ValueKey('mount-gallery-read'),
            onPressed: _busy ? null : _readGallery,
            child: const Text('이 격자로 읽기'),
          ),
        ],
      );
    }
    return Wrap(
      spacing: 8,
      runSpacing: 4,
      alignment: WrapAlignment.end,
      children: [
        if (remote != null)
          OutlinedButton.icon(
            icon: const Icon(Icons.photo_camera_outlined, size: 18),
            label: const Text('사진 받기'),
            onPressed: _busy ? null : () => _shootRemote(remote, read: false),
          ),
        _autoSetupButton(),
        TextButton(onPressed: () => setState(() => _grid = GridZones.initial), child: const Text('초기값')),
        TextButton(
          onPressed: () => setState(() {
            _grid = _gridBeforeEdit ?? _grid;
            _gridBeforeEdit = null;
          }),
          child: const Text('취소'),
        ),
        FilledButton(
          key: const ValueKey('mount-grid-save'),
          onPressed: () async {
            setState(() => _gridBeforeEdit = null);
            await _saveGrid();
            _toast('구역 격자를 저장했습니다');
          },
          child: const Text('저장 (편집 끝)'),
        ),
      ],
    );
  }

  Widget _autoSetupButton() => OutlinedButton.icon(
        key: const ValueKey('mount-grid-auto'),
        icon: _setupBusy
            ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.auto_fix_high, size: 18),
        label: const Text('자동 맞추기'),
        onPressed: _busy || _setupBusy ? null : _autoSetup,
      );

  /// meta.json 의 `setup`. 집계 스크립트가 높이·줌별로 묶는 데 쓴다.
  Map<String, Object?> _setup(String source, {double? zoom}) => {
    'source': source,
    'remote_url': source == 'remote' ? _remoteUrl : null,
    'zoom': zoom,
    'height_cm': _heightCm,
    'tracking': _trackingEnabled,
    'shadow': _shadow,
    'rectify': _rectify,
    'tracked_sides': [for (final s in _trackedNow().keys) s.name],
    'tracked_riichi': [for (final s in _trackedRiichi()) s.name],
    'tracked_double_riichi': [for (final s in _trackedDoubleRiichi()) s.name],
    'tracked_ippatsu': [for (final s in _trackedIppatsu()) s.name],
    'tracked_discard': _trackedDiscard()?.toJson(),
    'preview_long_side': _previewFrameLongSide,
  };

  // ---------------- 판 상태 추적 ----------------

  MeldTracker _trackerFor(GridZones grid) => _tracker ??= MeldTracker(tileFrac: tileFracsOf(grid));
  RiverTracker _riverTrackerFor(GridZones grid) => _riverTracker ??= RiverTracker(tileFrac: riverTileFracsOf(grid));

  /// 카메라가 움직이거나 조명이 한꺼번에 바뀐 프레임이면 두 추적기가 사건 대신 기준만 다시 잡게 한다.
  final SceneShiftGate _shiftGate = SceneShiftGate();

  /// 화료 판독에 넘길 힌트: 게임 중 확정한 리치봉 자리, 가장 최근 버림(방총자 후보·론 패 위치).
  Set<Side> _trackedRiichi() =>
      _trackingEnabled && _useGrid ? (_riverTracker?.riichi ?? const {}) : const {};
  Set<Side> _trackedDoubleRiichi() =>
      _trackingEnabled && _useGrid ? (_riverTracker?.doubleRiichiCandidates ?? const {}) : const {};
  Set<Side> _trackedIppatsu() => _trackingEnabled && _useGrid
      ? (_riverTracker?.ippatsuCandidates(meldGrewSince: (t) => _tracker?.grewSince(t) ?? false) ?? const {})
      : const {};
  Discard? _trackedDiscard() => _trackingEnabled && _useGrid ? _riverTracker?.lastDiscard : null;

  /// 화료 때 손패 전용 읽기를 써도 되는 자리와 그 울기(확정 + 그 뒤 변화 없음).
  Map<Side, List<ObservedMeld>> _trackedNow() {
    final t = _tracker;
    if (t == null || !_trackingEnabled || !_useGrid) return const {};
    return {for (final s in Side.values) s: ?t.trackedMelds(s)};
  }

  /// 판이 바뀌면(화료·유국 기록) 추적을 비운다. 처음 보는 판은 비우지 않는다(열자마자 리셋 로그가 남지 않게).
  /// 판 중간의 리치·점수 정정 기록은 판이 바뀐 게 아니다(2026-10-29 전엔 기록 수를 봐서 리치 버튼에 도라 산·울기 추적이 지워졌다).
  void _syncTrackerRound(Game g) {
    final hands = g.events.where((e) => e.kind == 'win' || e.kind == 'draw').length;
    final key = '${g.id}/${g.roundLabel}/${g.honba}/$hands';
    if (_trackRoundKey == key) return;
    final first = _trackRoundKey == null;
    _flushFrames('round');
    _frames.reset();
    _framesPart = 0;
    _trackRoundKey = key;
    _trackDir = null;
    if (!first) {
      _tracker?.reset(DateTime.now());
      _riverTracker?.reset(DateTime.now());
      _wall = null;
      _wallTried = false;
      _wallAutoTries = 0;
      _wallRetryTimer?.cancel();
      _wallRetryTimer = null;
    }
  }

  /// 배경 미리보기 한 장 → 모서리 통계 → 추적기. 읽을 자리가 나오면 모서리를 읽는다.
  Future<void> _trackFrame(Uint8List preview) async {
    final g = gameStore.current;
    if (!_trackingEnabled || !_useGrid || g == null || _trackBusy || _remoteUrl == null || _gridBeforeEdit != null) return;
    final tracker = _trackerFor(_grid);
    final river = _riverTrackerFor(_grid);
    final TableFrameStats stats;
    try {
      stats = await compute(analyzeTableFrame, (preview, _grid));
    } catch (e) {
      debugPrint('[track] analyze failed: $e');
      return;
    }
    if (!mounted) return;
    final now = DateTime.now();
    final shifted = _shiftGate.check(stats);
    if (shifted) {
      tracker.cameraMoved(now);
      river.cameraMoved(now);
    }
    final actions = tracker.onFrame(stats.corners, now);
    final riverActions = river.onFrame(stats.rivers, stats.strips, now);
    _recordFrame(preview, now, tracker, river, shifted);
    setState(() {});
    for (final a in actions) {
      unawaited(_readCorner(a, g));
    }
    for (final a in riverActions) {
      unawaited(_readSticks(a, g));
    }
    // 새 판의 첫 버림패 = 패산이 다 올라오고 도라를 뒤집은 뒤. 이때 한 번만 왕패를 찾는다.
    if (!_wallTried && _wall == null && river.lastDiscard != null) {
      _wallTried = true;
      unawaited(_locateWall(g));
    }
  }

  /// 배경 프레임 한 장을 [_frames] 에 넣는다(변화 주변·10장마다 한 장만 남음). 꽉 차면 그만큼 저장한다.
  void _recordFrame(Uint8List jpeg, DateTime now, MeldTracker tracker, RiverTracker river, bool shifted) {
    if (!_logEnabled) return;
    final why = frameChanges(
      melds: tracker,
      river: river,
      meldEventsFrom: _meldEventsSeen,
      riverEventsFrom: _riverEventsSeen,
      sceneShift: shifted,
    );
    _meldEventsSeen = tracker.events.length;
    _riverEventsSeen = river.events.length;
    _frames.add(jpeg, now, why: why);
    if (_frames.isFull) _flushFrames('full');
  }

  /// 모은 프레임을 판 기록 폴더에 `frames_##.zip` 으로(판이 바뀔 때·꽉 찼을 때·화료 촬영 직전·화면을 닫을 때).
  void _flushFrames(String reason) {
    final frames = _frames.take();
    if (frames.isEmpty || !_logEnabled) return;
    final g = gameStore.current;
    final dir = _trackDir ??= '${CaptureLog.newDir()}_track';
    final name = 'frames_${(++_framesPart).toString().padLeft(2, '0')}.zip';
    final meta = <String, dynamic>{
      'reason': reason,
      'round_key': _trackRoundKey,
      'part': _framesPart,
      'seen': _frames.seen,
      'interval_s': _bgInterval.inSeconds,
      'keep': {'before': _frames.before, 'after': _frames.after, 'every': _frames.every},
      'names': g?.names,
      'bottom_seat': g?.settings.bottomSeat,
      'preview_long_side': _previewFrameLongSide,
      'grid': _grid.toJson(),
    };
    unawaited(() async {
      try {
        final zip = await compute(encodeFramesZip, (frames, meta));
        await CaptureLog.saveFile(dir, name, zip, 'application/zip');
      } catch (e) {
        debugPrint('[frames] $name 저장 실패: $e');
      }
    }());
  }

  /// 지금 카메라 사진 한 장(줄여서)으로 왕패 상자를 찾는다. [manual] 이면 결과를 알린다.
  Future<void> _locateWall(Game g, {bool manual = false}) async {
    if (_wallBusy) return;
    setState(() => _wallBusy = true);
    // 자동 시도 횟수는 호출마다 센다(응답이 온 뒤에만 세면 타임아웃·429 같은 예외 때 재시도가 안 걸렸다, 2026-10-30 점검).
    if (!manual) _wallAutoTries++;
    final retry = !manual && _wallAutoTries < _wallMaxAutoTries;
    var found = false;
    final client = RecognizerClient();
    try {
      final src = await _currentPhoto();
      if (src == null) {
        if (manual) _toast('카메라가 준비되지 않았습니다');
        return;
      }
      final small = await _shrinkInIsolate(src);
      final j = await client.observe('wall', small, filename: 'wall.jpg');
      if (!mounted) return;
      final w = parseWallV2(j);
      setState(() => _wall = w);
      found = w != null;
      if (manual || w == null) {
        _toast(w == null
            ? (retry
                ? '도라 산을 찾지 못했습니다. ${_wallRetryGap.inSeconds}초 뒤 한 번 더 찾습니다.'
                : '도라 산을 찾지 못했습니다. "도라 산 찾기" 로 다시 해 보세요.')
            : '도라 산을 찾았습니다. 틀렸으면 "격자 편집" 에서 주황 상자를 끌어 고치세요.');
      }
      unawaited(_saveWall(g, small, j));
    } catch (e) {
      if (mounted && manual) _toast('도라 산 찾기 실패: $e');
    } finally {
      client.close();
      if (mounted) {
        setState(() => _wallBusy = false);
        if (retry && !found) _scheduleWallRetry(g);
      }
    }
  }

  /// 같은 판이고 아직 상자가 없으면 [_wallRetryGap] 뒤 한 번 더 찾는다(못 찾음·예외 모두).
  void _scheduleWallRetry(Game g) {
    final key = _trackRoundKey;
    _wallRetryTimer?.cancel();
    _wallRetryTimer = Timer(_wallRetryGap, () {
      if (!mounted || _trackRoundKey != key || _wall != null || _wallBusy) return;
      unawaited(_locateWall(g));
    });
  }

  /// 지금 카메라 사진 한 장: 카메라 헤드면 추적과 같은 출처(고해상 미리보기 또는 촬영), 이 기기 카메라면 촬영.
  Future<Uint8List?> _currentPhoto() async {
    final url = _remoteUrl;
    if (url != null) {
      final cam = RemoteCamera(url, token: _remoteToken, timeout: const Duration(seconds: 20));
      try {
        return await _trackSource(cam);
      } finally {
        cam.close();
      }
    }
    final c = _cam;
    if (c != null && c.value.isInitialized) return (await c.takePicture()).readAsBytes();
    return _lastShot;
  }

  /// 격자 맞추기 "자동 맞추기": 사진 한 장(갤러리 사진이면 그것)을 줄여 처음 설정 틀(`/v2/setup`)과 도라 산(`/v2/wall`)을
  /// 나란히 부르고, 손패+울기 바깥 띠 선·리치봉 상자([proposeGrid])와 도라 산 상자를 채운다. 사용자가 끌어 고친 뒤 저장/읽기.
  /// 네 자리 손패를 찾아 격자를 바꿨으면 true. [auto](대국 시작 직후)면 격자를 저장하고, 실패 안내는 [lastTry] 일 때만.
  Future<bool> _autoSetup({bool auto = false, bool lastTry = true}) async {
    if (_setupBusy) return false;
    final gallery = _galleryShot;
    setState(() => _setupBusy = true);
    final client = RecognizerClient();
    final sw = Stopwatch()..start();
    try {
      final src = gallery ?? await _currentPhoto();
      if (src == null) {
        if (!auto) _toast('사진이 없습니다. 카메라가 준비되면 다시 누르세요.');
        return false;
      }
      final small = await _shrinkInIsolate(src);
      final setupF = client.observe('setup', small, filename: 'setup.jpg');
      final wallF = client.observe('wall', small, filename: 'wall.jpg').then<Map<String, dynamic>?>((j) => j,
          onError: (Object _) => null);
      final setup = await setupF;
      final wallJ = await wallF;
      if (!mounted) return false;
      final proposed = proposeGrid(setup, keep: _grid);
      final wall = wallJ == null ? null : parseWallV2(wallJ);
      setState(() {
        if (proposed != null) _grid = proposed;
        if (gallery != null) {
          _galleryWall = wall;
        } else if (wall != null) {
          _wall = wall;
        }
      });
      if (auto && proposed != null) await _saveGrid();
      if (gallery == null) {
        unawaited(_saveSetup(small, setup, wallJ, proposed, wall, auto: auto, ms: sw.elapsedMilliseconds));
      }
      final secs = (sw.elapsedMilliseconds / 1000).toStringAsFixed(1);
      debugPrint('[setup] auto=$auto try=$_autoSetupTries ${sw.elapsedMilliseconds}ms grid=${proposed != null} wall=${wall != null}');
      if (!auto || proposed != null || lastTry) {
        final body = [
          proposed == null ? '네 자리 손패를 다 찾지 못해 격자는 그대로입니다' : '손패+울기 띠와 리치봉 상자를 맞췄습니다',
          wall == null ? '도라 산은 못 찾았습니다' : '도라 산을 찾았습니다',
          auto ? '틀렸으면 더보기 "구역 격자 맞추기" 에서 고치세요' : '틀렸으면 끌어 고치세요',
        ].join('. ');
        _toast(auto ? '격자 자동 맞추기 ($secs초, 이 카메라로 처음): $body' : '$body ($secs초)', long: auto);
      }
      return proposed != null;
    } catch (e) {
      if (mounted && (!auto || lastTry)) _toast('자동 맞추기 실패: $e');
      return false;
    } finally {
      client.close();
      if (mounted) setState(() => _setupBusy = false);
    }
  }

  String get _wallStatus => _wallBusy ? ' · 도라 산 찾는 중' : (_wall != null ? ' · 도라 산 잡음' : '');

  /// 테이블 화면 "도라 산 찾기" 버튼(더보기에도 있음; 매장에서 판 시작에 못 잡았을 때 바로 누르려고, 2026-10-29).
  Widget _wallButton(Game g) => TextButton.icon(
        key: const ValueKey('table-wall'),
        onPressed: _wallBusy || _busy || (_cam == null && _remoteUrl == null) ? null : () => _locateWall(g, manual: true),
        icon: _wallBusy
            ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.view_week_outlined, size: 16),
        label: Text(_wallBusy ? '도라 산 찾는 중…' : (_wall == null ? '도라 산 찾기' : '도라 산 다시 찾기')),
      );

  /// 테이블 화면 "헤드" 버튼: 연결됨(초록)/끊김(빨강)/헤드 없음. 끊겼으면 누르면 다시 붙어 보고, 안 되면 QR 스캔을 권한다.
  Widget _headButton() {
    final url = _remoteUrl;
    if (url == null) {
      return TextButton.icon(
        key: const ValueKey('table-head'),
        onPressed: _busy ? null : _scanQr,
        icon: const Icon(Icons.qr_code_scanner, size: 16),
        label: const Text('헤드 QR'),
      );
    }
    final ok = _headError == null && _bgTimer != null && !_bgStopped;
    final color = ok ? const Color(0xFF66BB6A) : const Color(0xFFEF5350);
    return TextButton.icon(
      key: const ValueKey('table-head'),
      style: TextButton.styleFrom(foregroundColor: color),
      onPressed: _busy
          ? null
          : () async {
              if (ok) {
                _toast('카메라 헤드 연결됨 ($url)');
                return;
              }
              // 다시 붙어 본다(토큰 거절·옛 헤드로 멈춘 것도 풀고). 안 되면 QR 스캔.
              _bgStopped = false;
              setState(() => _headError = null);
              _startBg();
              await _tickBg();
              if (!mounted) return;
              if (_headError == null) {
                _toast('카메라 헤드에 다시 연결했습니다');
              } else {
                final m = ScaffoldMessenger.of(context)..hideCurrentSnackBar();
                m.showSnackBar(
                  SnackBar(
                    content: Text('헤드 연결 실패: $_headError'),
                    duration: const Duration(seconds: 10),
                    persist: false,
                    action: SnackBarAction(label: 'QR 스캔', onPressed: _scanQr),
                  ),
                );
              }
            },
      icon: Icon(ok ? Icons.videocam : Icons.videocam_off, size: 16),
      label: Text(ok ? '헤드 연결됨' : '헤드 끊김 · 다시 연결'),
    );
  }

  /// 자동 맞추기 입력 사진(줄인 것)과 `/v2/setup`·`/v2/wall` 응답·제안 격자를 촬영 기록 `<시각>_track/setup_###` 에 남긴다
  /// (매장에서 자동 맞추기가 틀리거나 실패했을 때 뒤에 원인을 보려고, 2026-10-29).
  Future<void> _saveSetup(
    Uint8List small,
    Map<String, dynamic> setup,
    Map<String, dynamic>? wallRead,
    GridZones? proposed,
    WallZone? wall, {
    required bool auto,
    required int ms,
  }) async {
    if (!_logEnabled) return;
    final g = gameStore.current;
    final dir = _trackDir ??= '${CaptureLog.newDir()}_track';
    final stem = 'setup_${(++_trackSeq).toString().padLeft(3, '0')}';
    await CaptureLog.saveFile(dir, '$stem.jpg', small, 'image/jpeg');
    await CaptureLog.saveFile(
      dir,
      '$stem.json',
      CaptureLog.jsonBytes({
        'auto': auto,
        'try': auto ? _autoSetupTries : null,
        'ms': ms,
        'round': g?.roundLabel,
        'honba': g?.honba,
        'dealer': g?.dealer,
        'grid_before': _gridBeforeEdit?.toJson() ?? (proposed == null ? _grid.toJson() : null),
        'grid_proposed': proposed?.toJson(),
        'wall_box': wall?.box.toList(),
        'wall_side': wall?.side.name,
        'setup': setup,
        'wall': wallRead,
      }),
      'application/json',
    );
  }

  Future<void> _saveWall(Game g, Uint8List small, Map<String, dynamic> read) async {
    if (!_logEnabled) return;
    final dir = _trackDir ??= '${CaptureLog.newDir()}_track';
    final stem = 'wall_${(++_trackSeq).toString().padLeft(3, '0')}';
    await CaptureLog.saveFile(dir, '$stem.jpg', small, 'image/jpeg');
    await CaptureLog.saveFile(
      dir,
      '$stem.json',
      CaptureLog.jsonBytes({'round': g.roundLabel, 'honba': g.honba, 'dealer': g.dealer, 'read': read}),
      'application/json',
    );
  }

  /// 리치봉 띠가 바뀌어 가운데 기기를 `/v2/sticks` 로 읽는다(두 읽기가 같으면 추적기가 확정).
  Future<void> _readSticks(RiverAction a, Game g) async {
    final url = _remoteUrl;
    final river = _riverTracker;
    if (url == null || river == null) return;
    _trackBusy = true;
    final cam = RemoteCamera(url, token: _remoteToken, timeout: const Duration(seconds: 20));
    final client = RecognizerClient();
    final seq = ++_trackSeq;
    try {
      final src = await _trackSource(cam);
      final crop = (await _cropInIsolate(src, [CropSpec(_grid.sticksZone)])).first;
      final j = await client.observe('sticks', crop, filename: 'sticks.jpg');
      if (!mounted) return;
      river.onSticksRead(a.frame, parseCenterV2(j).sticks, DateTime.now());
      unawaited(_saveTrackSticks(g, seq, crop, j));
    } catch (e) {
      if (mounted) river.onSticksReadFailed(a.frame, DateTime.now(), '$e');
    } finally {
      cam.close();
      client.close();
      _trackBusy = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _saveTrackSticks(Game g, int seq, Uint8List crop, Map<String, dynamic> read) async {
    if (!_logEnabled) return;
    final dir = _trackDir ??= '${CaptureLog.newDir()}_track';
    final stem = 'sticks_${seq.toString().padLeft(3, '0')}';
    await CaptureLog.saveFile(dir, '$stem.jpg', crop, 'image/jpeg');
    await CaptureLog.saveFile(dir, '$stem.json', CaptureLog.jsonBytes({'round': g.roundLabel, 'read': read}), 'application/json');
    await _saveTrackState(g, dir);
  }

  /// 모서리 읽기용 사진: 헤드 스트림이 충분히 크면 고해상 미리보기(셔터 없음), 아니면 촬영(셔터음).
  /// 미리보기는 프레임 긴 변 그대로 받는다 — 네이티브 헤드(HeadCamera)는 스트림이 12MP 라 2000 으로 줄이면 패가 50px 대로
  /// 떨어진다(NOTES 32·33). 0.3초·0.7MB 라 전체를 받아도 부담이 작다.
  Future<Uint8List> _trackSource(RemoteCamera cam) async {
    final long = _previewFrameLongSide;
    if (long != null && long >= _trackPreviewMinLongSide) return (await cam.preview(longSide: long)).bytes;
    return (await cam.capture()).bytes;
  }

  Future<void> _readCorner(TrackerAction a, Game g) async {
    final url = _remoteUrl;
    final tracker = _tracker;
    if (url == null || tracker == null) return;
    _trackBusy = true;
    final cam = RemoteCamera(url, token: _remoteToken, timeout: const Duration(seconds: 20));
    final client = RecognizerClient();
    final seq = ++_trackSeq;
    try {
      final src = await _trackSource(cam);
      final crop = (await _cropInIsolate(src, [CropSpec(_grid.cornerCell(a.side), side: a.side)])).first;
      final j = await client.observe('corner', crop, filename: 'corner_${a.side.name}.jpg');
      if (!mounted) return;
      tracker.onRead(a.side, a.frame, parseCornerV2(j).melds, DateTime.now());
      unawaited(_saveTrack(g, a.side, seq, crop, j));
    } catch (e) {
      if (mounted) tracker.onReadFailed(a.side, a.frame, DateTime.now(), '$e');
    } finally {
      cam.close();
      client.close();
      _trackBusy = false;
      if (mounted) setState(() {});
    }
  }

  /// 추적 기록: 모서리 크롭 + 읽기 + 누구 것(사진 자리·대국 자리·이름) + 추적기 상태. 판마다 폴더 하나.
  Future<void> _saveTrack(Game g, Side side, int seq, Uint8List crop, Map<String, dynamic> read) async {
    final tracker = _tracker;
    if (!_logEnabled || tracker == null) return;
    final dir = _trackDir ??= '${CaptureLog.newDir()}_track';
    final seat = SeatMap(g.settings.bottomSeat).seatOf(side);
    final stem = 'corner_${seq.toString().padLeft(3, '0')}_${side.name}';
    await CaptureLog.saveFile(dir, '$stem.jpg', crop, 'image/jpeg');
    await CaptureLog.saveFile(
      dir,
      '$stem.json',
      CaptureLog.jsonBytes({
        'side': side.name,
        'seat': seat,
        'name': g.names[seat],
        'round': g.roundLabel,
        'honba': g.honba,
        'read': read,
      }),
      'application/json',
    );
    await _saveTrackState(g, dir);
  }

  /// 추적기 상태 전부(울기·강·리치봉)를 track.json 으로.
  Future<void> _saveTrackState(Game g, String dir) async {
    final tracker = _tracker;
    if (tracker == null) return;
    await CaptureLog.saveFile(
      dir,
      'track.json',
      CaptureLog.jsonBytes({
        ...tracker.toJson(),
        'rivers': _riverTracker?.toJson(),
        'names': g.names,
        'bottom_seat': g.settings.bottomSeat,
        'round': g.roundLabel,
        'preview_long_side': _previewFrameLongSide,
      }),
      'application/json',
    );
  }

  /// 자리별 울기 칩: 미리 읽은 울기와 상태. 누르면 다시 읽기, 길게 누르면 지우기.
  Widget _meldChips(Game g, SeatMap seats) {
    final t = _tracker;
    if (!_trackingEnabled || t == null) return const SizedBox.shrink();
    final rows = <Widget>[];
    for (final side in Side.values) {
      final ts = t.seat(side);
      if (ts.status == TrackStatus.idle && ts.melds.isEmpty) continue;
      final seat = seats.seatOf(side);
      final (label, color) = switch (ts.status) {
        TrackStatus.confirmed when !ts.changedSinceConfirm => ('미리 읽음', kioskGold),
        TrackStatus.reading => ('읽는 중', Colors.grey),
        TrackStatus.unconfirmed => ('미확정', Colors.orange),
        _ => ('바뀜', Colors.grey),
      };
      rows.add(
        InkWell(
          key: ValueKey('track-chip-${side.name}'),
          onTap: () => setState(() => t.requestReread(side, DateTime.now())),
          onLongPress: () => setState(() => t.clear(side, DateTime.now())),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              children: [
                Text('${g.names[seat]} · $label', style: TextStyle(fontSize: 12, color: color)),
                const SizedBox(width: 8),
                for (final m in ts.melds)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: TileRow([for (final x in m.tiles) x.tile], width: 18, open: m.faceDown.isEmpty),
                  ),
              ],
            ),
          ),
        ),
      );
    }
    // 강·리치봉 추적 요약: 자리별 감지한 버림 수, 마지막 버림 자리, 확정한 리치.
    final rv = _riverTracker;
    if (rv != null) {
      final counts = rv.discardCounts;
      final last = rv.lastDiscard;
      if (counts.values.any((n) => n > 0) || rv.riichi.isNotEmpty) {
        final parts = [
          '강 ${[for (final s in Side.values) if (counts[s]! > 0) '${g.names[seats.seatOf(s)]} ${counts[s]}'].join(' · ')}',
          if (last != null) '마지막 ${g.names[seats.seatOf(last.side)]}',
          if (rv.riichi.isNotEmpty) '리치 ${rv.riichi.map((s) => g.names[seats.seatOf(s)]).join('·')}',
        ];
        rows.add(Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Text(parts.join('  |  '), key: const ValueKey('track-river-line'),
              style: const TextStyle(fontSize: 12, color: Colors.white70)),
        ));
      }
    }
    if (rows.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows),
    );
  }

  Future<void> _askHeight() async {
    final ctl = TextEditingController(text: _heightCm?.toString() ?? '');
    final v = await showDialog<String>(
      context: context,
      builder: (ctx) => kioskWrap(ctx, AlertDialog(
        title: const Text('거치 높이 (cm)'),
        content: TextField(
          key: const ValueKey('mount-height'),
          controller: ctl,
          autofocus: true,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            hintText: '예: 70',
            helperText: '테이블 면에서 카메라까지. 촬영 기록에 같이 남아 높이별 정확도를 비교합니다. 비우면 기록 안 함.',
            helperMaxLines: 3,
          ),
          onSubmitted: (s) => Navigator.pop(ctx, s),
        ),
        actions: [FilledButton(onPressed: () => Navigator.pop(ctx, ctl.text), child: const Text('저장'))],
      )),
    );
    ctl.dispose();
    if (v == null) return;
    final cm = int.tryParse(v.trim());
    try {
      final p = await SharedPreferences.getInstance();
      if (cm == null) {
        await p.remove(heightPref);
      } else {
        await p.setInt(heightPref, cm);
      }
    } catch (_) {}
    if (mounted) setState(() => _heightCm = cm);
  }

  /// 사진 크기를 잰다(플랫폼 디코더라 빠르다). 촬영 사진이면 촬영 기록용 긴 변과 격자 기준 비율도 갱신한다.
  /// 웹은 ImageDescriptor 가 안 되므로 그때는 통째로 디코딩해 잰다.
  Future<void> _measureCapture(Uint8List bytes, {bool capture = true}) async {
    try {
      int w;
      int h;
      try {
        final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
        final desc = await ui.ImageDescriptor.encoded(buffer);
        w = desc.width;
        h = desc.height;
        desc.dispose();
        buffer.dispose();
      } catch (_) {
        final im = await decodeImageFromList(bytes);
        w = im.width;
        h = im.height;
        im.dispose();
      }
      if (mounted && w > 0 && h > 0) {
        setState(() {
          _captureW = w;
          _captureH = h;
          if (capture) {
            _captureLongSide = w > h ? w : h;
            _photoW = w;
            _photoH = h;
          }
        });
      }
    } catch (_) {}
  }

  Future<void> _askRemoteUrl() async {
    final ctl = TextEditingController(text: _remoteUrl ?? '');
    final tokenCtl = TextEditingController(text: _remoteToken ?? '');
    // scan: QR 스캔으로 넘어감. 그 밖엔 (주소, 토큰) 저장.
    final v = await showDialog<({bool scan, String url, String token})>(
      context: context,
      builder: (ctx) {
        void save() => Navigator.pop(ctx, (scan: false, url: ctl.text, token: tokenCtl.text));
        return kioskWrap(ctx, AlertDialog(
          title: const Text('원격 카메라 주소'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: double.infinity,
                child: FilledButton.tonalIcon(
                  key: const ValueKey('mount-remote-scan'),
                  onPressed: () => Navigator.pop(ctx, (scan: true, url: '', token: '')),
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('QR 스캔'),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                key: const ValueKey('mount-remote-url'),
                controller: ctl,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: '주소',
                  hintText: '예: 192.168.0.12:8765',
                  helperText:
                      '카메라 헤드 화면의 주소. "주소?t=토큰" 을 통째로 붙여 넣어도 됩니다. '
                      '비우면 이 기기의 카메라를 씁니다.',
                  helperMaxLines: 3,
                ),
                onSubmitted: (_) => save(),
              ),
              TextField(
                key: const ValueKey('mount-remote-token'),
                controller: tokenCtl,
                autocorrect: false,
                enableSuggestions: false,
                decoration: const InputDecoration(labelText: '토큰', helperText: '카메라 헤드 화면 주소의 t= 뒤 글자'),
                onSubmitted: (_) => save(),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, (scan: false, url: '', token: '')),
              child: const Text('이 기기 카메라'),
            ),
            FilledButton(onPressed: save, child: const Text('저장')),
          ],
        ));
      },
    );
    ctl.dispose();
    tokenCtl.dispose();
    if (v == null) return;
    if (v.scan) {
      await _scanQr();
      return;
    }
    if (!await _setRemoteUrl(v.url, token: v.token)) return;
    await _checkRemote();
  }

  Future<void> _pickFromGallery() async {
    if (_busy) return;
    final XFile? picked;
    try {
      // 원본 해상도 그대로. 줄이면 패가 100px 아래로 내려가 못 읽는다.
      picked = await ImagePicker().pickImage(source: ImageSource.gallery);
    } catch (e) {
      _toast('사진을 가져오지 못했습니다: $e');
      return;
    }
    if (picked == null) return;
    final bytes = await picked.readAsBytes();
    double? aspect;
    try {
      final codec = await ui.instantiateImageCodec(bytes, targetWidth: 400);
      final frame = await codec.getNextFrame();
      aspect = frame.image.width / frame.image.height;
      frame.image.dispose();
      codec.dispose();
    } catch (_) {}
    if (!mounted) return;
    // 사진을 띄우고 지금 격자를 겹쳐 맞추게 한다. "이 격자로 읽기" 에서 읽는다([_readGallery]).
    setState(() {
      _galleryShot = bytes;
      _galleryAspect = aspect;
      _gridBeforeEdit = _grid;
    });
  }

  /// 갤러리 사진 위에서 맞춘 격자로 읽는다. 끝나면 격자·읽기 방식을 고르기 전으로 되돌린다.
  Future<void> _readGallery() async {
    final bytes = _galleryShot;
    if (bytes == null || _busy) return;
    final savedGrid = _gridBeforeEdit ?? _grid;
    final savedUseGrid = _useGrid;
    setState(() {
      _gridBeforeEdit = null;
      _useGrid = true;
    });
    try {
      await _process(bytes, setup: _setup('gallery'));
    } finally {
      if (mounted) {
        setState(() {
          _grid = savedGrid;
          _useGrid = savedUseGrid;
          _galleryShot = null;
          _galleryAspect = null;
          _galleryWall = null;
        });
      }
    }
  }

  void _cancelGallery() => setState(() {
        _grid = _gridBeforeEdit ?? _grid;
        _gridBeforeEdit = null;
        _galleryShot = null;
        _galleryAspect = null;
        _galleryWall = null;
      });

  // ---------------- 판독 ----------------

  Future<void> _process(Uint8List bytes, {Map<String, Object?> setup = const {}}) async {
    final g = gameStore.current;
    if (g == null || !mounted) return;
    setState(() => _busy = true);
    // 기록 폴더를 먼저 정해 두고, 이 국에서 "대국에 반영" 하면 거기에 정답(label.json)을 쓴다.
    final logDir = CaptureLog.newDir();
    if (_logEnabled) {
      CaptureLog.setPending(logDir, CaptureLog.roundKey(g.roundLabel, g.honba));
    }
    final trace = TableReadTrace();
    void saveLog({TableMerge? merge, String? error, List<String> warnings = const []}) =>
        _saveLog(logDir, bytes, trace, g, setup, merge: merge, error: error, warnings: warnings);
    final seats = SeatMap(g.settings.bottomSeat);
    final client = RecognizerClient();
    final reader = TableReader(client, ops: _isolateOps);
    final stage = ValueNotifier<ReadStage>(ReadStage.decoding);
    final done = Completer<void>();
    // 진행 다이얼로그는 done 이 끝나면 스스로 닫힌다. 다음 화면을 띄우기 전에 반드시 닫힘을 기다려야
    // 한다 — 그러지 않으면 다이얼로그의 pop 이 방금 띄운 화면을 닫아 버린다.
    final dialog = showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _ProgressDialog(stage: stage, done: done.future),
    );
    Future<void> closeProgress() async {
      if (!done.isCompleted) done.complete();
      await dialog;
    }

    // 트리플론을 유국으로 하는 규칙에서 선택 창이 바로 도중 유국을 기록했으면 판독을 멈춘다.
    var drawRecorded = false;
    // 화료자마다 병합한다. 동시 론이면 서로를 방총자 후보에서 뺀다.
    List<TableMerge> mergeAll(List<TableReading> readings) {
      final winnerSides = {for (final r in readings) r.winnerSide!};
      return [
        for (final r in readings)
          mergeReading(
            hand: r.hand!,
            center: r.center,
            winnerSide: r.winnerSide!,
            game: g,
            seats: seats,
            otherWinners: winnerSides.difference({r.winnerSide!}),
            meldsTracked: r.meldsTracked,
            loserHint: r.trackedDiscardSide,
            doubleRiichiHint: r.trackedDoubleRiichi.contains(r.winnerSide!),
            ippatsuHint: r.trackedIppatsu.contains(r.winnerSide!),
          ),
      ];
    }

    try {
      final reading = _useGrid
          ? await reader.readGrid(
              bytes,
              _grid,
              rectify: _rectify,
              dealer: seats.sideOf(g.dealer),
              // 그 판의 왕패 상자는 이 카메라의 좌표다. 갤러리 사진(다른 사진)에는 쓰지 않는다.
              wall: setup['source'] == 'gallery' ? _galleryWall : _wall,
              onStage: (s) => stage.value = s,
              pickWinners: (cands) async {
                final r = await _pickWinners(cands, g, seats);
                if (identical(r, _tripleRonDraw)) {
                  gameStore.mutate((g) => g.abortiveDraw('트리플론'));
                  drawRecorded = true;
                  return null;
                }
                return r;
              },
              // 눕힌 손패 둘이 같은 방총자·같은 화료패로 둘 다 화료형이면 묻지 않고 더블론(결과 화면에서 한 명으로 되돌림).
              acceptAll: (rs) => clearDoubleRon(
                mergeAll(rs),
                (m) => engine.calculate(m.hand!, m.situation, rules: widget.editor.rules).isValid,
              ),
              tracked: _trackedNow(),
              shadow: _shadow,
              trackedRiichi: _trackedRiichi(),
              trackedDoubleRiichi: _trackedDoubleRiichi(),
              trackedIppatsu: _trackedIppatsu(),
              trackedDiscard: _trackedDiscard(),
              trace: trace,
            )
          : await reader.read(
              bytes,
              onStage: (s) => stage.value = s,
              // locate 판독은 화료자 한 자리만 읽는다(동시 론은 격자 판독에서만).
              pickWinner: (cands) async => (await _pickWinners(cands, g, seats, single: true))?.first,
              trace: trace,
              fixed: _fixed,
            );
      // 새로 locate 했으면 그 구역을 다음 촬영의 기준으로 삼는다.
      final small = trace.small;
      if (!_useGrid && trace.layoutMode != 'fixed' && small != null && FixedTable.usable(reading.layout)) {
        _fixed = await compute(calibrateFixed, (small, reading.layout));
      }
      if (!mounted) return;
      setState(() => _lastLayout = reading.layout);
      // 규칙(머리치기·인원)에 맞춰 화료자를 고른다.
      final readings = [reading, ...reading.others];
      final picked = pickRonWinners(mergeAll(readings), g.settings, g.names);
      final merge = picked.kept.first;
      final others = <OtherWin>[];
      final otherFlags = <String>[];
      for (final m in picked.kept.skip(1)) {
        final who = g.names[m.winner];
        otherFlags.addAll(m.flags.map((f) => '$who: ${f.message}'));
        if (m.hand == null) {
          otherFlags.add('$who 손패를 계산하지 못했습니다. "대국에 반영" 에서 판·부로 더해 주세요');
          continue;
        }
        others.add(
          OtherWin(
            m.winner,
            engine.calculate(m.hand!, m.situation, rules: widget.editor.rules),
            riichi: m.situation.riichi,
            hand: m.hand,
            situation: m.situation,
          ),
        );
      }
      widget.editor.setFromMerge(merge, g);
      final flags = [
        for (final r in readings) ...r.warnings.where((w) => r == reading || !reading.warnings.contains(w)),
        if (trace.autoMultiRon && picked.kept.length > 1)
          '눕힌 손패 둘이 같은 패로 화료형이라 더블론으로 봤습니다. 한 명만 났으면 "한 명만 론" 을 누르세요',
        ...picked.flags.map((f) => f.message),
        ...merge.flags.map((f) => f.message),
        ...otherFlags,
      ];
      saveLog(merge: merge, warnings: reading.warnings);
      debugPrint('[read] merged winner=${merge.winner} hand=${merge.hand != null} → 진행 창 닫기');
      await closeProgress();
      debugPrint('[read] 진행 창 닫힘 mounted=$mounted');
      if (!mounted) return;

      if (merge.hand == null) {
        // 장수가 안 맞음 → 입력 화면으로 돌아가 고친다.
        _toast('계산 전에 손패를 고쳐 주세요. ${flags.join(' / ')}', long: true);
        if (widget.isHome) {
          _openCalculator();
        } else {
          Navigator.of(context).pop();
        }
        return;
      }
      final result = engine.calculate(merge.hand!, merge.situation, rules: widget.editor.rules);
      final autoBlock = autoRecordBlocker(
        warnings: [
          for (final r in readings) ...r.warnings,
          ...picked.flags.map((f) => f.message),
          ...otherFlags,
        ],
        issues: [for (final f in merge.flags) f.issue],
        otherWinners: picked.kept.length - 1,
        isTsumo: merge.isTsumo,
        loser: picked.loser,
        resultValid: result.isValid,
        paoBase: result.isValid ? engine.paoBasePoints(result) : 0,
        gameOver: g.isOver,
        doraIndicators: merge.situation.doraIndicators.length,
        riichi: merge.situation.riichi,
      );
      // 테이블 화면이 열린 채 룰 설정에서 바꿨을 수 있어 매번 다시 읽는다.
      _autoRecord = await AutoRecordStore.load();
      if (!mounted) return;
      debugPrint('[read] 결과 화면 띄움 valid=${result.isValid} autoBlock=$autoBlock');
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (ctx) => ResultScreen(
            result: result,
            hand: merge.hand,
            situation: merge.situation,
            isTsumo: merge.isTsumo,
            gameSeat: merge.winner,
            loser: picked.loser,
            otherWins: others,
            flags: flags,
            onFix: widget.isHome
                ? () => Navigator.of(ctx).pushReplacement(MaterialPageRoute(
                    builder: (_) => InputScreen(editor: widget.editor, popAfterRecord: true)))
                : () => Navigator.of(ctx).popUntil((r) => r.isFirst),
            photoRiichiSeats: Set.of(merge.photoRiichiSeats),
            winnerRiichi: merge.situation.riichi || merge.situation.doubleRiichi,
            rules: widget.editor.rules,
            onWinRecorded: (o) => saveCaptureLabel(widget.editor, o),
            onSituationChanged: widget.editor.applySituation,
            onRecorded: widget.editor.clear,
            autoRecordAfter: _autoRecord && autoBlock == null ? autoRecordDelay : null,
          ),
        ),
      );
    } on TableReadException catch (e) {
      saveLog(error: drawRecorded ? '트리플론 유국' : e.message);
      await closeProgress();
      if (!mounted) return;
      if (drawRecorded) {
        _toast('트리플론 — 도중 유국으로 기록했습니다 (친 유지, 본장 +1)', long: true);
        return;
      }
      setState(() => _lastLayout = e.layout);
      await _showProblem(e.message, e.layout?.notes ?? '');
    } on RecognizerException catch (e) {
      saveLog(error: e.message);
      await closeProgress();
      _toast(e.message, long: true);
    } catch (e) {
      saveLog(error: '$e');
      await closeProgress();
      _toast('판독 중 오류: $e', long: true);
    } finally {
      await closeProgress();
      client.close();
      if (mounted) setState(() => _busy = false);
    }
  }

  /// 촬영 기록을 백그라운드로 저장한다. 판독 흐름을 막지 않는다.
  void _saveLog(
    String dir,
    Uint8List original,
    TableReadTrace trace,
    Game g,
    Map<String, Object?> setup, {
    TableMerge? merge,
    String? error,
    List<String> warnings = const [],
  }) {
    if (!_logEnabled) return;
    unawaited(
      CaptureLog.save(
        dir: dir,
        setup: setup,
        original: original,
        trace: trace,
        merge: merge,
        game: g,
        error: error,
        warnings: warnings,
        captureLongSide: _captureLongSide,
      ).then((dir) {
        if (dir == null) _toast('촬영 기록을 저장하지 못했습니다');
      }),
    );
  }

  /// [_pickWinners] 가 "트리플론 — 유국" 을 골랐을 때 돌려주는 표시.
  static const _tripleRonDraw = <Side>[];

  /// 눕힌 손패가 여럿일 때 누가 났는지. 한 명, 또는 규칙이 허락하면 동시 론으로 여럿([single] 이면 한 명만).
  /// 셋이 눕혔고 규칙이 트리플론 유국이면 [_tripleRonDraw]. 취소면 null.
  Future<List<Side>?> _pickWinners(List<Side> cands, Game g, SeatMap seats, {bool single = false}) {
    String names(Iterable<Side> ss) => ss.map((s) => g.names[seats.seatOf(s)]).join('·');
    final multi = !single && cands.length >= 2 && cands.length < 4;
    final rule = g.settings;
    final kiosk = isKioskLayout(context);
    final optionStyle = kiosk ? const TextStyle(fontSize: 20) : null;
    final optionPad = kiosk ? const EdgeInsets.symmetric(horizontal: 24, vertical: 14) : null;
    return showDialog<List<Side>>(
      context: context,
      builder: (ctx) => kioskWrap(ctx, SimpleDialog(
        title: const Text('눕힌 손패가 여럿입니다. 누가 났나요?'),
        children: [
          for (final s in cands)
            SimpleDialogOption(
              padding: optionPad,
              onPressed: () => Navigator.pop(ctx, [s]),
              child: Text('${s.label}: ${g.names[seats.seatOf(s)]}', style: optionStyle),
            ),
          if (multi && cands.length == 3 && rule.tripleRonDraws)
            SimpleDialogOption(
              key: const ValueKey('pick-triple-draw'),
              padding: optionPad,
              onPressed: () => Navigator.pop(ctx, _tripleRonDraw),
              child: Text('셋 다 론(${names(cands)}) — 트리플론 유국으로 기록', style: optionStyle),
            )
          else if (multi)
            SimpleDialogOption(
              key: const ValueKey('pick-multi-ron'),
              padding: optionPad,
              onPressed: () => Navigator.pop(ctx, cands),
              child: Text(
                rule.multiRon == GameSettings.multiRonHeadBump
                    ? '${cands.length == 2 ? '둘' : '셋'} 다 론(${names(cands)}) — 머리치기로 한 명만'
                    : '${cands.length == 2 ? '둘 다 론 (더블론)' : '셋 다 론 (트리플론)'}: ${names(cands)}',
                style: optionStyle,
              ),
            ),
          SimpleDialogOption(padding: optionPad, onPressed: () => Navigator.pop(ctx), child: Text('취소', style: optionStyle)),
        ],
      )),
    );
  }

  Future<void> _showProblem(String message, String notes) {
    return showDialog<void>(
      context: context,
      builder: (ctx) => kioskWrap(ctx, AlertDialog(
        title: const Text('읽지 못했습니다'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(message),
            if (notes.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('서버 설명: $notes', style: Theme.of(ctx).textTheme.bodySmall),
            ],
          ],
        ),
        actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('닫기'))],
      )),
    );
  }

  /// 토큰 거절 안내. 바로 QR 스캔으로 갈 수 있게 버튼을 단다.
  void _toastScan(String message) {
    if (!mounted) return;
    final m = ScaffoldMessenger.of(context)..hideCurrentSnackBar();
    m.showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 10),
        persist: false, // 액션이 있어도 duration 뒤 사라지게(Flutter 3.29+ 기본은 남음)
        action: SnackBarAction(label: 'QR 스캔', onPressed: _scanQr),
      ),
    );
  }

  void _toast(String message, {bool long = false}) {
    if (!mounted) return;
    final m = ScaffoldMessenger.of(context)..hideCurrentSnackBar();
    m.showSnackBar(
      SnackBar(
        content: Text(message),
        duration: Duration(seconds: long ? 10 : 3),
        persist: false,
        action: long ? SnackBarAction(label: '닫기', onPressed: m.hideCurrentSnackBar) : null,
      ),
    );
  }

  // ---------------- 화면 ----------------

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: gameStore,
      builder: (context, _) {
        final g = gameStore.current;
        if (g == null) {
          return Scaffold(
            appBar: AppBar(title: const Text('거치 촬영')),
            body: const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('대국 기록 중에만 쓸 수 있습니다.\n점수판에서 대국을 시작한 뒤 다시 여세요.', textAlign: TextAlign.center),
              ),
            ),
          );
        }
        final seats = SeatMap(g.settings.bottomSeat);
        _syncTrackerRound(g);
        final kiosk = isKioskLayout(context);
        final scaffold = Scaffold(
          appBar: AppBar(
            automaticallyImplyLeading: !widget.isHome,
            // 첫 화면(키오스크 테이블)이면 뒤로 갈 곳이 없어, 대국은 두고 로비로 가는 "홈".
            leading: widget.isHome
                ? IconButton(
                    key: const ValueKey('table-home'),
                    tooltip: '홈 (대국은 그대로)',
                    icon: const Icon(Icons.home_outlined),
                    onPressed: () => kioskLobbyFor.value = g.id,
                  )
                : null,
            title: Text(kiosk || widget.isHome ? '대국 ${g.roundLabel}' : '거치 촬영 ${g.roundLabel}'),
            actions: [
              // 폰은 제목(국·본장) 자리가 좁아 글자 없이 아이콘만.
              if (widget.isHome && !g.isOver && !kiosk)
                IconButton(
                  key: const ValueKey('table-end'),
                  tooltip: '대국 종료 (정산)',
                  icon: const Icon(Icons.stop_circle_outlined),
                  onPressed: () => Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
                )
              else if (widget.isHome && !g.isOver)
                TextButton.icon(
                  key: const ValueKey('table-end'),
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: const Text('대국 종료'),
                  // 중간 정산 화면 → "저장하고 종료".
                  onPressed: () => Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => SettlementScreen(game: g))),
                ),
              PopupMenuButton<int>(
                tooltip: '화면 아래쪽에 앉은 사람',
                icon: const Icon(Icons.person_pin_circle_outlined),
                onSelected: (s) => gameStore.mutate((g) => g.settings = g.settings.copyWith(bottomSeat: s)),
                itemBuilder: (_) => [
                  for (var s = 0; s < 4; s++)
                    CheckedPopupMenuItem(
                      value: s,
                      checked: s == g.settings.bottomSeat,
                      child: Text('아래쪽: ${g.names[s]}'),
                    ),
                ],
              ),
              PopupMenuButton<String>(
                tooltip: '더보기',
                onSelected: (v) async {
                  if (v == 'log') {
                    final next = !_logEnabled;
                    await CaptureLog.setEnabled(next);
                    if (mounted) setState(() => _logEnabled = next);
                  } else if (v == 'auto') {
                    setState(() => _autoRecord = !_autoRecord);
                    await AutoRecordStore.save(_autoRecord);
                  } else if (v == 'remote') {
                    await _askRemoteUrl();
                  } else if (v == 'scan') {
                    await _scanQr();
                  } else if (v == 'height') {
                    await _askHeight();
                  } else if (v == 'grid') {
                    setState(() => _useGrid = !_useGrid);
                    await _saveGrid();
                  } else if (v == 'wall') {
                    await _locateWall(g, manual: true);
                  } else if (v == 'fullscreen') {
                    await FullscreenMode.set(!FullscreenMode.enabled.value);
                  } else if (v == 'autoSetup') {
                    setState(() => _autoSetupOnStart = !_autoSetupOnStart);
                    try {
                      final p = await SharedPreferences.getInstance();
                      await p.setBool(autoSetupPref, _autoSetupOnStart);
                    } catch (_) {}
                    if (_autoSetupOnStart) _maybeAutoSetup();
                  } else if (v == 'gridEdit') {
                    setState(() {
                      _useGrid = true;
                      _gridBeforeEdit = _grid;
                    });
                  } else if (v == 'rectify') {
                    setState(() => _rectify = !_rectify);
                    try {
                      final p = await SharedPreferences.getInstance();
                      await p.setBool(rectifyPref, _rectify);
                    } catch (_) {}
                  } else if (v == 'tracking' || v == 'shadow') {
                    setState(() {
                      if (v == 'tracking') {
                        _trackingEnabled = !_trackingEnabled;
                        if (!_trackingEnabled) _shadow = false;
                      } else {
                        _shadow = !_shadow;
                      }
                    });
                    try {
                      final p = await SharedPreferences.getInstance();
                      await p.setBool(trackingPref, _trackingEnabled);
                      await p.setBool(shadowPref, _shadow);
                    } catch (_) {}
                  }
                },
                itemBuilder: (_) => [
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-grid-menu'),
                    value: 'grid',
                    checked: _useGrid,
                    child: const Text('격자 구역으로 읽기 (위치 찾기 생략)'),
                  ),
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-rectify-menu'),
                    value: 'rectify',
                    checked: _rectify,
                    enabled: _useGrid,
                    child: const Text('작탁만 남기고 펴서 읽기 (펠트를 못 찾으면 격자 그대로)'),
                  ),
                  PopupMenuItem(
                    key: const ValueKey('mount-wall-menu'),
                    value: 'wall',
                    enabled: !_wallBusy && (_cam != null || _remoteUrl != null),
                    child: Text(_wallBusy ? '도라 산 찾는 중…' : (_wall == null ? '도라 산 찾기 (이번 판)' : '도라 산 다시 찾기 (이번 판)')),
                  ),
                  const PopupMenuItem(
                    key: ValueKey('mount-grid-edit-menu'),
                    value: 'gridEdit',
                    child: Text('구역 격자 맞추기…'),
                  ),
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-fullscreen-menu'),
                    value: 'fullscreen',
                    checked: FullscreenMode.enabled.value,
                    child: const Text('전체 화면 (상태 표시줄·작업 표시줄 숨김)'),
                  ),
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-auto-setup-menu'),
                    value: 'autoSetup',
                    checked: _autoSetupOnStart,
                    enabled: _useGrid,
                    child: const Text('카메라가 바뀌면 격자 자동 맞추기 (카메라마다 한 번)'),
                  ),
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-tracking-menu'),
                    value: 'tracking',
                    checked: _trackingEnabled,
                    enabled: _useGrid && _remoteUrl != null,
                    child: const Text('판 상태 추적 (울기 미리 읽기, 격자 + 카메라 헤드)'),
                  ),
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-shadow-menu'),
                    value: 'shadow',
                    checked: _shadow,
                    enabled: _trackingEnabled,
                    child: const Text('그림자 모드 (두 방식 동시 기록, 실험용)'),
                  ),
                  CheckedPopupMenuItem(
                    key: const ValueKey('mount-auto-menu'),
                    value: 'auto',
                    checked: _autoRecord,
                    child: const Text('확실한 판독은 10초 뒤 자동 반영'),
                  ),
                  CheckedPopupMenuItem(
                    value: 'log',
                    checked: _logEnabled,
                    child: const Text('촬영 기록 저장 (Download/mahjong_calc)'),
                  ),
                  PopupMenuItem(
                    key: const ValueKey('mount-height-menu'),
                    value: 'height',
                    child: Text(_heightCm == null ? '거치 높이…' : '거치 높이: ${_heightCm}cm'),
                  ),
                  const PopupMenuItem(key: ValueKey('mount-scan-menu'), value: 'scan', child: Text('카메라 헤드 QR 스캔')),
                  PopupMenuItem(
                    key: const ValueKey('mount-remote-menu'),
                    value: 'remote',
                    child: Text(_remoteUrl == null ? '원격 카메라 주소…' : '원격 카메라: $_remoteUrl'),
                  ),
                ],
              ),
            ],
          ),
          body: kiosk
              // 태블릿 작업 표시줄(아래 48dp)이 버튼 칸 아래를 덮지 않게(2026-10-29 SM-X236N).
              ? SafeArea(top: false, child: _kioskBody(g, seats))
              : widget.isHome
                  ? _phoneBody(g, seats)
                  : SafeArea(
            top: false,
            child: Column(
              children: [
                Expanded(child: _preview(g, seats)),
                if (_gridBeforeEdit != null)
                  _gridEditPanel()
                else ...[
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
                    child: Row(
                      children: [
                        OutlinedButton.icon(
                          key: const ValueKey('mount-gallery'),
                          icon: const Icon(Icons.photo_library_outlined, size: 18),
                          label: const Text('갤러리'),
                          onPressed: _busy ? null : _pickFromGallery,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: FilledButton.icon(
                            key: const ValueKey('mount-shoot'),
                            icon: const Icon(Icons.camera_alt, size: 20),
                            label: const Text('촬영'),
                            onPressed: _busy || (_cam == null && _remoteUrl == null) ? null : _shoot,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _meldChips(g, seats),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
                    child: Text(
                      '아래쪽 ${g.names[g.settings.bottomSeat]} · 오른쪽 ${g.names[seats.seatOf(Side.right)]} · '
                      '위 ${g.names[seats.seatOf(Side.top)]} · 왼쪽 ${g.names[seats.seatOf(Side.left)]}\n'
                      '${_remoteUrl == null ? '볼륨키(리모컨)로도 찍힙니다. ' : '사진은 원격 카메라에서 받습니다. '}'
                      '${_heightCm == null ? '' : ' (높이 ${_heightCm}cm)'}'
                      '${_logEnabled ? '' : ' (기록 저장 꺼짐)'}$_wallStatus',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
        // 폰도 대국 중 첫 화면(테이블)이면 키오스크와 같은 어두운 테마.
        return kiosk || widget.isHome ? Theme(data: kioskDarkTheme(), child: scaffold) : scaffold;
      },
    );
  }

  Widget _gridEditPanel() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_galleryShot != null)
            Text(
              '갤러리 사진에 격자를 맞추세요. 사진 아래쪽은 ${_bottomName()} 자리입니다(위 사람 아이콘에서 바꿈).',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.bold),
            ),
          Text(
            '선 네 개를 끌어 각 자리(손패 + 오른쪽 모서리 울기)와 가운데(강·가운데 기기·도라)를 나누세요. '
            '선은 손패와 강 사이 가운데쯤에 둡니다. 주황 상자는 지금 선(친) 앞 왕패·도라 표시패 자리입니다 — 안을 끌어 옮기고 '
            '오른쪽 아래 모서리로 크기를 바꾸세요(선이 바뀌면 그 자리 쪽으로 돌아갑니다).',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 6),
          _gridEditBar(),
        ],
      ),
    );
  }

  String _bottomName() {
    final g = gameStore.current;
    return g == null ? '아래쪽 사람' : g.names[g.settings.bottomSeat];
  }

  void _openCalculator() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => InputScreen(editor: widget.editor, popAfterRecord: true)),
    );
  }

  /// 테이블 화면의 큰 버튼. [compact] = 폰(높이·글자를 줄임).
  Widget _bigButton(String label, IconData icon, VoidCallback? onPressed,
      {Key? key, bool primary = false, bool compact = false}) {
    final child = FittedBox(
      fit: BoxFit.scaleDown,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: compact ? 20 : 26),
          SizedBox(width: compact ? 6 : 10),
          Text(label, style: TextStyle(fontSize: compact ? (primary ? 18 : 15) : 20)),
        ],
      ),
    );
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(compact ? 12 : 14));
    final pad = compact ? const EdgeInsets.symmetric(horizontal: 6) : null;
    return SizedBox(
      height: compact ? (primary ? 60 : 48) : (primary ? 96 : 68),
      child: primary
          ? FilledButton(key: key, style: FilledButton.styleFrom(shape: shape, padding: pad), onPressed: onPressed, child: child)
          : OutlinedButton(
              key: key,
              style: OutlinedButton.styleFrom(shape: shape, padding: pad, foregroundColor: Colors.white),
              onPressed: onPressed,
              child: child,
            ),
    );
  }

  /// 대국이 끝났을 때(토비·아가리야메·종료) 버튼 칸 위의 안내.
  Widget _overBanner(Game g, {bool compact = false}) => Container(
        key: const ValueKey('table-over-banner'),
        padding: compact ? const EdgeInsets.fromLTRB(10, 6, 10, 6) : const EdgeInsets.fromLTRB(12, 10, 12, 10),
        margin: EdgeInsets.only(bottom: compact ? 8 : 12),
        decoration: BoxDecoration(
          color: g.anyBusted ? kioskRed.withValues(alpha: 0.25) : kioskGold.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: g.anyBusted ? kioskRed : kioskGold),
        ),
        child: Text(g.endNote, style: TextStyle(color: Colors.white, fontSize: compact ? 13 : 14, height: 1.4)),
      );

  /// 폰 테이블 화면(대국 중 첫 화면): 세로면 위 테이블 사진(가운데 점수판) + 아래 버튼 칸, 가로면 오른쪽 버튼 칸.
  /// 버튼·키는 키오스크 오른쪽 칸과 같고 크기만 줄였다. 기록은 최근 2개만 보이고 전부는 "기록".
  Widget _phoneBody(Game g, SeatMap seats) {
    if (_gridBeforeEdit != null) {
      return SafeArea(top: false, child: Column(children: [Expanded(child: _preview(g, seats)), _gridEditPanel()]));
    }
    final canShoot = !_busy && (_cam != null || _remoteUrl != null);
    void push(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
    Widget big(String label, IconData icon, VoidCallback? onPressed, {Key? key, bool primary = false}) =>
        _bigButton(label, icon, onPressed, key: key, primary: primary, compact: true);
    const gap = SizedBox(width: 8, height: 8);
    final panel = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (g.isOver) ...[
          _overBanner(g, compact: true),
          big('정산', Icons.calculate_outlined, () => push(SettlementScreen(game: g)),
              key: const ValueKey('table-settle'), primary: true),
        ] else
          big('화료 촬영', Icons.camera_alt, canShoot ? _shoot : null, key: const ValueKey('mount-shoot'), primary: true),
        gap,
        Row(
          children: [
            Expanded(
              child: big('직접 계산', Icons.calculate_outlined, _busy ? null : _openCalculator,
                  key: const ValueKey('table-calc')),
            ),
            gap,
            Expanded(child: big('리치', Icons.flag_outlined, _busy ? null : () => showRiichiPicker(context, g))),
            gap,
            Expanded(child: big('유국', Icons.block, _busy ? null : () => showDrawDialog(context, g))),
          ],
        ),
        gap,
        Row(
          children: [
            Expanded(child: big('천화', Icons.auto_awesome, _busy ? null : () => _firstTurnWin(g, dealer: true))),
            gap,
            Expanded(child: big('지화', Icons.auto_awesome_outlined, _busy ? null : () => _firstTurnWin(g, dealer: false))),
          ],
        ),
        gap,
        Row(
          children: [
            Expanded(
              child: big('갤러리', Icons.photo_library_outlined, _busy ? null : _pickFromGallery,
                  key: const ValueKey('mount-gallery')),
            ),
            gap,
            Expanded(child: big('기록', Icons.scoreboard_outlined, () => push(const GameScreen()))),
          ],
        ),
        _meldChips(g, seats),
        const SizedBox(height: 4),
        _eventsHeader(g),
        if (g.events.isEmpty)
          const Padding(
            padding: EdgeInsets.only(bottom: 6),
            child: Text('기록 없음', style: TextStyle(color: Colors.white38, fontSize: 13)),
          )
        else
          for (var idx = g.events.length - 1; idx >= 0 && idx >= g.events.length - 2; idx--) _eventTile(g, idx),
        Text(
          '아래 ${g.names[seats.seatOf(Side.bottom)]} · 오른쪽 ${g.names[seats.seatOf(Side.right)]} · '
          '위 ${g.names[seats.seatOf(Side.top)]} · 왼쪽 ${g.names[seats.seatOf(Side.left)]}\n'
          '${_remoteUrl == null ? '이 기기 카메라 · 볼륨키로도 찍힙니다' : '카메라 헤드 $_remoteUrl'}'
          '${_logEnabled ? '' : ' · 기록 저장 꺼짐'}$_wallStatus',
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 11, color: Colors.white60),
        ),
        Wrap(
          children: [
            TextButton(onPressed: () => push(ScoreTableScreen(rules: widget.editor.rules)), child: const Text('점수표')),
            TextButton(onPressed: () => push(SettingsScreen(editor: widget.editor)), child: const Text('룰 설정')),
            TextButton.icon(
              key: const ValueKey('table-grid-edit'),
              onPressed: _busy
                  ? null
                  : () => setState(() {
                        _useGrid = true;
                        _gridBeforeEdit = _grid;
                      }),
              icon: const Icon(Icons.grid_4x4, size: 16),
              label: const Text('격자 편집'),
            ),
            _wallButton(g),
            _headButton(),
          ],
        ),
      ],
    );
    return LayoutBuilder(builder: (context, box) {
      // 가로(폰을 눕힘): 사진이 넓게 오른쪽에 버튼 칸. 칸이 높이를 넘으면 스크롤.
      if (box.maxWidth > box.maxHeight) {
        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(child: _preview(g, seats)),
            Container(
              width: 300,
              color: kioskSurface,
              child: SafeArea(
                left: false,
                child: SingleChildScrollView(padding: const EdgeInsets.fromLTRB(12, 10, 12, 8), child: panel),
              ),
            ),
          ],
        );
      }
      // 세로: 버튼 칸은 화면의 60% 까지(작은 폰은 칸 안에서 스크롤), 나머지가 사진.
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(child: _preview(g, seats)),
          Container(
            constraints: BoxConstraints(maxHeight: box.maxHeight * 0.6),
            color: kioskSurface,
            child: SafeArea(
              top: false,
              child: SingleChildScrollView(padding: const EdgeInsets.fromLTRB(12, 10, 12, 4), child: panel),
            ),
          ),
        ],
      );
    });
  }

  /// 천화(친)·지화(자, 자리를 고름): 손패 없이 그 역만 하나로 결과 화면 → "대국에 반영"
  /// (2026-10-29 사용자: 천화·지화는 테이블 화면에서 바로). 다른 역만이 겹치면 "직접 계산" 에서 손패를 넣는다.
  Future<void> _firstTurnWin(Game g, {required bool dealer}) async {
    int? seat = g.dealer;
    if (!dealer) {
      seat = await showDialog<int>(
        context: context,
        builder: (ctx) => kioskWrap(
          ctx,
          SimpleDialog(
            title: const Text('지화 — 누가 났나요?'),
            children: [
              for (var s = 0; s < 4; s++)
                if (s != g.dealer)
                  SimpleDialogOption(
                    key: ValueKey('chiihou-seat-$s'),
                    onPressed: () => Navigator.pop(ctx, s),
                    child: Text('${engine.Tiles.name(g.seatWindOf(s))}  ${g.names[s]}', style: const TextStyle(fontSize: 18)),
                  ),
            ],
          ),
        ),
      );
      if (seat == null || !mounted) return;
    }
    final sit = engine.Situation(
      isTsumo: true,
      seatWind: g.seatWindOf(seat),
      roundWind: g.roundWindTile,
      honba: g.honba,
    );
    final result = engine.firstTurnWinOnly(sit);
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ResultScreen(
          result: result,
          isTsumo: true,
          seatWind: sit.seatWind,
          gameSeat: seat,
          onRecorded: widget.editor.clear,
          rules: widget.editor.rules,
        ),
      ),
    );
  }

  /// 키오스크: 왼쪽 테이블 사진(가운데 점수판), 오른쪽 큰 버튼(화료 촬영·직접 계산·리치·유국).
  Widget _kioskBody(Game g, SeatMap seats) {
    if (_gridBeforeEdit != null) {
      return Column(children: [Expanded(child: _preview(g, seats)), _gridEditPanel()]);
    }
    final canShoot = !_busy && (_cam != null || _remoteUrl != null);
    // 화면 높이가 900dp 미만(태블릿 가로 800dp, 노트북 창 720)이면 작은 버튼 — 큰 버튼이면 아래 기록 칸이 0 이 돼
    // "기록" 줄이 안내 글과 겹친다(2026-10-29 SM-X236N, 헤드 연결로 안내가 3줄이 됐을 때).
    final compact = MediaQuery.sizeOf(context).height < 900;
    Widget big(String label, IconData icon, VoidCallback? onPressed, {Key? key, bool primary = false}) =>
        _bigButton(label, icon, onPressed, key: key, primary: primary, compact: compact);

    void push(Widget screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(child: _preview(g, seats)),
        Container(
          width: 320,
          color: kioskSurface,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 대국이 끝났으면(토비·아가리야메·종료) 촬영 대신 정산이 큰 버튼.
              if (g.isOver) ...[
                _overBanner(g),
                big('정산', Icons.calculate_outlined, () => push(SettlementScreen(game: g)),
                    key: const ValueKey('table-settle'), primary: true),
              ] else
                big('화료 촬영', Icons.camera_alt, canShoot ? _shoot : null, key: const ValueKey('mount-shoot'), primary: true),
              const SizedBox(height: 12),
              big('직접 계산', Icons.calculate_outlined, _busy ? null : _openCalculator, key: const ValueKey('table-calc')),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: big('리치', Icons.flag_outlined, _busy ? null : () => showRiichiPicker(context, g))),
                  const SizedBox(width: 12),
                  Expanded(child: big('유국', Icons.block, _busy ? null : () => showDrawDialog(context, g))),
                ],
              ),
              const SizedBox(height: 12),
              // 천화·지화: 사진 없이 바로 역만 결과 화면(유국 텐파이는 "유국" 창에서 고른다).
              Row(
                children: [
                  Expanded(
                    child: big('천화', Icons.auto_awesome, _busy ? null : () => _firstTurnWin(g, dealer: true),
                        key: const ValueKey('table-tenhou')),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: big('지화', Icons.auto_awesome_outlined, _busy ? null : () => _firstTurnWin(g, dealer: false),
                        key: const ValueKey('table-chiihou')),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: big('갤러리', Icons.photo_library_outlined, _busy ? null : _pickFromGallery,
                        key: const ValueKey('mount-gallery')),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: big('기록', Icons.scoreboard_outlined, () => push(const GameScreen()))),
                ],
              ),
              const SizedBox(height: 12),
              // 최근 사건(점수판의 기록 줄). 최신이 위.
              Expanded(child: _kioskEvents(g)),
              _meldChips(g, seats),
              Text(
                '아래 ${g.names[seats.seatOf(Side.bottom)]} · 오른쪽 ${g.names[seats.seatOf(Side.right)]}\n'
                '위 ${g.names[seats.seatOf(Side.top)]} · 왼쪽 ${g.names[seats.seatOf(Side.left)]}\n'
                '${_remoteUrl == null ? '이 기기 카메라' : '카메라 헤드 $_remoteUrl${_bgTimer != null && !_bgStopped ? ' (배경은 헤드 미리보기${_previewFrameLongSide == null ? '' : ', 스트림 긴 변 $_previewFrameLongSide'})' : ''}'}'
                '${_logEnabled ? '' : ' · 기록 저장 꺼짐'}$_wallStatus',
                style: const TextStyle(fontSize: 12, color: Colors.white60),
              ),
              const SizedBox(height: 8),
              Wrap(
                children: [
                  TextButton(onPressed: () => push(ScoreTableScreen(rules: widget.editor.rules)), child: const Text('점수표')),
                  TextButton(onPressed: () => push(SettingsScreen(editor: widget.editor)), child: const Text('룰 설정')),
                  // 격자 편집 켬: 선·리치봉 상자를 끌 수 있고, 아래 "저장 (편집 끝)"/"취소" 로 끈다(평소엔 끌리지 않아 잘못 터치해도 안전).
                  TextButton.icon(
                    key: const ValueKey('table-grid-edit'),
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                              _useGrid = true;
                              _gridBeforeEdit = _grid;
                            }),
                    icon: const Icon(Icons.grid_4x4, size: 16),
                    label: const Text('격자 편집'),
                  ),
                  _wallButton(g),
                  _headButton(),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// 키오스크 오른쪽 칸의 최근 사건 목록(점수판 기록과 같은 내용, 최신이 위).
  /// 위 줄에 "마지막 취소"·"정정", 기록을 누르면 그 기록부터 되돌리기·점수 정정.
  Widget _kioskEvents(Game g) {
    final header = _eventsHeader(g);
    if (g.events.isEmpty) {
      return Column(children: [
        header,
        const Expanded(child: Center(child: Text('기록 없음', style: TextStyle(color: Colors.white38)))),
      ]);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        header,
        Expanded(
          child: ListView.builder(
            key: const ValueKey('table-events'),
            padding: EdgeInsets.zero,
            itemCount: g.events.length,
            itemBuilder: (_, i) => _eventTile(g, g.events.length - 1 - i),
          ),
        ),
      ],
    );
  }

  /// 기록 목록 위 줄: "마지막 취소"·"정정".
  Widget _eventsHeader(Game g) {
    return Row(
      children: [
        const Text('기록', style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w600)),
        const Spacer(),
        TextButton.icon(
          key: const ValueKey('table-undo'),
          style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
          icon: const Icon(Icons.undo, size: 18),
          label: const Text('마지막 취소'),
          onPressed: g.canUndo && !_busy ? () => confirmRewind(context) : null,
        ),
        TextButton.icon(
          key: const ValueKey('table-correct'),
          style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
          icon: const Icon(Icons.edit_outlined, size: 18),
          label: const Text('정정'),
          onPressed: _busy ? null : () => showScoreCorrection(context),
        ),
      ],
    );
  }

  /// 기록 한 줄(누르면 그 기록부터 되돌리기·점수 정정).
  Widget _eventTile(Game g, int idx) {
    final e = g.events[idx];
    final moves = List.generate(4, (s) => '${g.names[s]} ${e.delta[s] >= 0 ? '+' : ''}${e.delta[s]}')
        .where((t) => !t.endsWith(' +0'))
        .join('  ');
    return InkWell(
      key: ValueKey('table-event-$idx'),
      onTap: _busy ? null : () => showEventActions(context, idx),
      child: Padding(
        padding: const EdgeInsets.only(bottom: 8, top: 2),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${e.roundLabel}  ${e.description}',
                style: const TextStyle(color: Colors.white, fontSize: 13), maxLines: 2, overflow: TextOverflow.ellipsis),
            if (moves.isNotEmpty)
              Text(moves,
                  style: const TextStyle(color: Colors.white54, fontSize: 11), maxLines: 1, overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }

  Widget _preview(Game g, SeatMap seats) {
    final c = _cam;
    final editing = _gridBeforeEdit != null;
    final overlay = Stack(
      fit: StackFit.expand,
      children: [
        CustomPaint(
          painter: _LayoutPainter(editing ? null : _lastLayout, g, seats),
          child: const SizedBox.expand(),
        ),
        if (_useGrid)
          GridOverlay(
            grid: _grid,
            editing: editing,
            dealer: seats.sideOf(g.dealer),
            wallBox: _galleryShot == null ? _wall?.box : _galleryWall?.box,
            onChanged: (v) => setState(() => _grid = v),
            onWallChanged: (b) => setState(() {
              if (_galleryShot != null) {
                _galleryWall = (box: b, side: _galleryWall?.side ?? Side.bottom);
              } else {
                _wall = (box: b, side: _wall?.side ?? Side.bottom);
              }
            }),
          ),
        if (!editing)
          LayoutBuilder(
            builder: (context, c) => Center(
              child: TableScorePanel(
                game: g,
                seats: seats,
                // 가운데 강·기기를 덜 가리게 짧은 변의 34%(전엔 45%, 2026-10-29 사용자). 작은 폰은 칸의 85% 를 넘지 않게.
                size: (c.biggest.shortestSide * 0.34).clamp(150.0, 300.0).clamp(0.0, c.biggest.shortestSide * 0.85),
              ),
            ),
          ),
      ],
    );
    final gallery = _galleryShot;
    if (gallery != null) {
      // 갤러리 사진(읽기 전·읽는 중)은 카메라 미리보기 대신 사진 비율 그대로 띄우고 격자를 겹친다.
      return Container(
        color: Colors.black,
        alignment: Alignment.center,
        child: AspectRatio(
          aspectRatio: _galleryAspect ?? 4 / 3,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Image.memory(gallery, fit: BoxFit.fill, cacheWidth: 1200, gaplessPlayback: true),
              overlay,
            ],
          ),
        ),
      );
    }
    if (c != null && c.value.isInitialized) {
      return Center(child: CameraPreview(c, child: overlay));
    }
    final shot = _lastShot;
    if (_remoteUrl != null && shot != null && _captureW != null) {
      // 원격 사진은 촬영 비율 그대로 띄우고 그 위에 구역 상자를 겹친다(CameraPreview 와 같은 좌표계).
      // 배경이 미리보기(비율이 다를 수 있음)여도 촬영 비율을 알면 그 비율로 가운데를 잘라, 격자가 사진과 같은 자리에 온다.
      final aspect = _photoW != null && _photoH != null ? _photoW! / _photoH! : _captureW! / _captureH!;
      return Container(
        color: Colors.black,
        alignment: Alignment.center,
        child: AspectRatio(
          aspectRatio: aspect,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Image.memory(shot, fit: BoxFit.cover, cacheWidth: 1200, gaplessPlayback: true),
              overlay,
            ],
          ),
        ),
      );
    }
    // 사진이 아직 없으면 펠트색 테이블 위에 점수판만 띄운다.
    return Container(
      color: Colors.black87,
      alignment: Alignment.center,
      padding: EdgeInsets.all(isKioskLayout(context) ? 24 : 8),
      child: Container(
        decoration: BoxDecoration(
          color: kioskFelt,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFF3B2A1C), width: 10),
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            overlay,
            Align(
              alignment: const Alignment(0, 0.92),
              child: Text(
                _remoteUrl != null
                    ? '원격 카메라 $_remoteUrl\n촬영을 누르면 그 기기에서 찍어 옵니다. 첫 사진이 여기에 보입니다.'
                    : _camError ?? '카메라 준비 중…',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 직전 locate 결과를 미리보기 위에 겹쳐 그린다(손패 빨강, 강 노랑, 중앙 흰색).
/// 패 최소 크기 상자는 뺐다(거치가 고정이라 손으로 맞출 일이 없음, 2026-10-27 사용자).
class _LayoutPainter extends CustomPainter {
  final TableLayout? layout;
  final Game game;
  final SeatMap seats;
  _LayoutPainter(this.layout, this.game, this.seats);

  @override
  void paint(Canvas canvas, Size size) {
    final l = layout;
    if (l == null) return;
    Rect rect(NormBox b) => Rect.fromLTRB(
      b.xmin * size.width / 1000,
      b.ymin * size.height / 1000,
      b.xmax * size.width / 1000,
      b.ymax * size.height / 1000,
    );
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    // 격자 구역이면 칸 경계는 격자가 그린다. 손패 칸의 이름·★(앞면)만 그린다.
    final grid = l.model == 'grid';
    for (final r in grid ? const <SidedZone>[] : l.rivers) {
      canvas.drawRect(rect(r.box), stroke..color = Colors.yellow.withValues(alpha: 0.8));
    }
    final center = l.center;
    if (center != null && !grid) {
      canvas.drawRect(rect(center), stroke..color = Colors.white.withValues(alpha: 0.6));
    }
    final dora = l.deadWall?.box;
    if (dora != null && grid) {
      canvas.drawRect(rect(dora), stroke..color = Colors.lightGreenAccent.withValues(alpha: 0.8));
    }
    for (final h in l.hands) {
      final c = h.faceUp ? Colors.redAccent : Colors.red.withValues(alpha: 0.5);
      final rc = rect(h.box);
      if (!grid || h.faceUp) canvas.drawRect(rc, stroke..color = c);
      final tp = TextPainter(
        text: TextSpan(
          text: '${game.names[seats.seatOf(h.side)]}${h.faceUp ? ' ★' : ''}',
          style: TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.w600),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, rc.topLeft + const Offset(4, 2));
    }
  }

  @override
  bool shouldRepaint(_LayoutPainter old) =>
      old.layout != layout ||
      old.game != game ||
      old.seats.bottomSeat != seats.bottomSeat;
}

/// 단계와 경과 초를 보여주는 진행 다이얼로그. [done] 이 끝나면 스스로 닫힌다.
class _ProgressDialog extends StatefulWidget {
  final ValueNotifier<ReadStage> stage;
  final Future<void> done;
  const _ProgressDialog({required this.stage, required this.done});

  @override
  State<_ProgressDialog> createState() => _ProgressDialogState();
}

class _ProgressDialogState extends State<_ProgressDialog> {
  int _elapsed = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _elapsed++);
    });
    widget.done.whenComplete(() {
      debugPrint('[read] 진행 창 done mounted=$mounted');
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // 키오스크(테이블 화면 위)에서는 멀리서도 보이게 크게.
    final kiosk = isKioskLayout(context);
    return kioskWrap(
      context,
      AlertDialog(
        content: SizedBox(
          width: kiosk ? 520 : null,
          child: ValueListenableBuilder<ReadStage>(
            valueListenable: widget.stage,
            builder: (_, s, _) => Row(
              children: [
                SizedBox(
                  width: kiosk ? 48 : 28,
                  height: kiosk ? 48 : 28,
                  child: CircularProgressIndicator(strokeWidth: kiosk ? 4 : 3),
                ),
                SizedBox(width: kiosk ? 24 : 16),
                Expanded(
                  child: Text(
                    '${s.label} ($_elapsed초)\n보통 12~20초 걸립니다',
                    style: kiosk ? const TextStyle(fontSize: 20, height: 1.4) : null,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
