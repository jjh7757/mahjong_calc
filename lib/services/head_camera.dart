import 'package:flutter/services.dart';

/// 카메라 헤드 전용 카메라(Android, `HeadCamera.kt`). 셔터(ImageCapture) 없이 미리보기 + 최대 해상도 YUV 스트림만 묶어,
/// 미리보기(`/preview`)와 촬영(`/capture`)을 모두 스트림의 최신 프레임에서 JPEG 로 만든다 → 셔터음 없음, 12MP.
/// camera 플러그인은 셋(미리보기·촬영·스트림)을 늘 같이 묶어 스트림이 1440×1080 으로 제한됐다(NOTES 32).
///
/// Android 밖(테스트·데스크톱)에서는 [start] 가 [MissingPluginException] 을 던진다.
class HeadCamera {
  static const MethodChannel _channel = MethodChannel('dev.jjh.mahjong_calc/head_camera');

  int? textureId;
  int previewWidth = 0;
  int previewHeight = 0;
  int streamWidth = 0;
  int streamHeight = 0;

  /// 센서 방향(도). 세로로 든 폰의 뒤 카메라는 보통 90 — 미리보기 텍스처를 그만큼 돌려 보여 준다.
  int sensorOrientation = 90;
  double maxZoom = 1;

  bool get isRunning => textureId != null;

  Future<void> start({double zoom = 1}) async {
    final m = await _channel.invokeMapMethod<String, dynamic>('start', {'zoom': zoom});
    if (m == null) throw StateError('start 응답 없음');
    textureId = (m['textureId'] as num).toInt();
    previewWidth = (m['previewWidth'] as num?)?.toInt() ?? 0;
    previewHeight = (m['previewHeight'] as num?)?.toInt() ?? 0;
    streamWidth = (m['streamWidth'] as num?)?.toInt() ?? 0;
    streamHeight = (m['streamHeight'] as num?)?.toInt() ?? 0;
    sensorOrientation = (m['sensorOrientation'] as num?)?.toInt() ?? 90;
    maxZoom = (m['maxZoom'] as num?)?.toDouble() ?? 1;
  }

  Future<void> stop() async {
    textureId = null;
    try {
      await _channel.invokeMethod<void>('stop');
    } on MissingPluginException {
      // 무시
    }
  }

  /// 적용된 줌 배율(기기 상한으로 잘린 값).
  Future<double> setZoom(double zoom) async {
    final z = await _channel.invokeMethod<double>('setZoom', {'zoom': zoom});
    return z ?? zoom;
  }

  /// 최신 프레임의 JPEG. [longSide] 가 프레임보다 작으면 건너뛰어 줄인다. [fresh] 면 이 호출 뒤 들어온 프레임을 기다린다.
  Future<HeadJpeg> jpeg({int? longSide, int quality = 75, bool fresh = false}) async {
    final m = await _channel.invokeMapMethod<String, dynamic>('jpeg', {
      'longSide': longSide,
      'quality': quality,
      'fresh': fresh,
    });
    if (m == null) throw StateError('jpeg 응답 없음');
    return HeadJpeg(
      m['bytes'] as Uint8List,
      width: (m['width'] as num).toInt(),
      height: (m['height'] as num).toInt(),
      frameWidth: (m['frameWidth'] as num).toInt(),
      frameHeight: (m['frameHeight'] as num).toInt(),
    );
  }

  /// 녹화 모드(시험용, 기본 꺼짐) 시작: 스트림 프레임을 초당 [fps] 장까지 2×2 평균으로 줄인 JPEG 로 이 기기 저장소에 계속 쓴다.
  /// 판독(`jpeg`)은 그대로다. 카메라가 안 돌거나 남은 용량이 2GB 아래면 [PlatformException].
  /// Android 밖이면 [HeadRecordStatus.unsupported].
  Future<HeadRecordStatus> recordStart({int fps = 10, int quality = 85}) =>
      _record('recordStart', {'fps': fps, 'quality': quality});

  /// 녹화를 끝낸다(녹화 중이 아니면 아무것도 안 함). 결과는 끝난 뒤 상태.
  Future<HeadRecordStatus> recordStop() => _record('recordStop');

  /// 녹화 상태. 녹화 중이 아니어도 스트림 속도·남은 용량은 들어 있다.
  Future<HeadRecordStatus> recordStatus() => _record('recordStatus');

  /// 태블릿 이어 받기: 마지막(또는 지금) 녹화에서 [after] ms 보다 늦게 다 쓴 프레임 시각들(오름차순, [max] 개까지).
  /// 파일은 `<dir>/f_<ms>.jpg`. Android 밖이면 빈 결과.
  Future<HeadRecordFrames> recordFrames({required int after, int max = 10}) async {
    try {
      final m = await _channel.invokeMapMethod<String, dynamic>('recordFrames', {'after': after, 'max': max});
      return HeadRecordFrames.fromMap(m);
    } on MissingPluginException {
      return const HeadRecordFrames();
    }
  }

  /// 이 기기의 앱 전용 외부 저장소 경로와 남은 용량(태블릿이 받은 녹화를 둔다). Android 밖이면 null.
  static Future<({String path, int freeBytes})?> filesDir() async {
    try {
      final m = await _channel.invokeMapMethod<String, dynamic>('filesDir');
      final p = m?['path'] as String?;
      if (p == null) return null;
      return (path: p, freeBytes: (m?['freeBytes'] as num?)?.toInt() ?? -1);
    } on MissingPluginException {
      return null;
    }
  }

  Future<HeadRecordStatus> _record(String method, [Map<String, Object?>? args]) async {
    try {
      final m = await _channel.invokeMapMethod<String, dynamic>(method, args);
      return HeadRecordStatus.fromMap(m);
    } on MissingPluginException {
      return HeadRecordStatus.unsupported;
    }
  }
}

/// 녹화 모드 상태(`HeadCamera.kt recordStatus`). 숫자는 없으면 0, 남은 용량을 모르면 -1.
class HeadRecordStatus {
  /// 이 기기에서 녹화를 쓸 수 있나(Android 밖이면 false).
  final bool supported;
  final bool recording;

  /// 마지막(또는 지금) 녹화 폴더 전체 경로. 녹화한 적이 없으면 null.
  final String? dir;
  final int saved;
  final int dropped;
  final int bytes;

  /// 분석 콜백이 불린 속도(장/초). 최근 1초 창, 2초 넘게 프레임이 없으면 0.
  final double streamFps;

  /// 카메라를 연 뒤 전체 평균 스트림 속도(장/초).
  final double streamFpsAvg;

  /// 최근 5초 저장 속도(장/초).
  final double savedFps;
  final int freeBytes;

  /// 멈춘 까닭: user · camera_stop · low_storage · error. 녹화 중이거나 녹화한 적이 없으면 null.
  final String? stopReason;
  final String? stopDetail;

  const HeadRecordStatus({
    this.supported = true,
    this.recording = false,
    this.dir,
    this.saved = 0,
    this.dropped = 0,
    this.bytes = 0,
    this.streamFps = 0,
    this.streamFpsAvg = 0,
    this.savedFps = 0,
    this.freeBytes = -1,
    this.stopReason,
    this.stopDetail,
  });

  static const HeadRecordStatus unsupported = HeadRecordStatus(supported: false);

  factory HeadRecordStatus.fromMap(Map<String, dynamic>? m) {
    if (m == null) return const HeadRecordStatus();
    int i(String k, [int d = 0]) => (m[k] as num?)?.toInt() ?? d;
    double f(String k) => (m[k] as num?)?.toDouble() ?? 0;
    return HeadRecordStatus(
      recording: m['recording'] == true,
      dir: m['dir'] as String?,
      saved: i('saved'),
      dropped: i('dropped'),
      bytes: i('bytes'),
      streamFps: f('streamFps'),
      streamFpsAvg: f('streamFpsAvg'),
      savedFps: f('savedFps'),
      freeBytes: i('freeBytes', -1),
      stopReason: m['stopReason'] as String?,
      stopDetail: m['stopDetail'] as String?,
    );
  }

  /// 사용자가 끄지 않았는데 멈췄나(용량 부족·오류·카메라 정지).
  bool get stoppedBySelf => !recording && stopReason != null && stopReason != 'user';

  /// 멈춘 까닭을 화면에 보일 문장으로. 사용자가 끈 것·녹화 중이면 null.
  String? get stopMessage {
    if (!stoppedBySelf) return null;
    final why = switch (stopReason) {
      'low_storage' => '남은 용량이 2GB 아래라 스스로 멈췄습니다',
      'camera_stop' => '카메라가 꺼져 멈췄습니다',
      'error' => '저장 중 오류로 멈췄습니다',
      _ => '멈췄습니다($stopReason)',
    };
    final d = stopDetail;
    return d == null || d.isEmpty ? why : '$why: $d';
  }

  /// 바이트 → "12.3GB"(1024³ 기준, 네이티브의 2GB 기준과 같은 단위).
  static String gb(int bytes) => '${(bytes / (1 << 30)).toStringAsFixed(1)}GB';
}

/// [HeadCamera.recordFrames] 결과.
class HeadRecordFrames {
  /// 녹화 폴더 전체 경로. 녹화한 적이 없으면 null.
  final String? dir;
  final bool recording;
  final int? latest;
  final int remaining;
  final List<int> ms;
  const HeadRecordFrames({this.dir, this.recording = false, this.latest, this.remaining = 0, this.ms = const []});

  factory HeadRecordFrames.fromMap(Map<String, dynamic>? m) {
    if (m == null) return const HeadRecordFrames();
    return HeadRecordFrames(
      dir: m['dir'] as String?,
      recording: m['recording'] == true,
      latest: (m['latest'] as num?)?.toInt(),
      remaining: (m['remaining'] as num?)?.toInt() ?? 0,
      ms: [for (final x in (m['ms'] as List? ?? const [])) (x as num).toInt()],
    );
  }
}

class HeadJpeg {
  final Uint8List bytes;
  final int width;
  final int height;

  /// 스트림 프레임(줄이기 전) 크기.
  final int frameWidth;
  final int frameHeight;
  const HeadJpeg(this.bytes, {required this.width, required this.height, required this.frameWidth, required this.frameHeight});
}
