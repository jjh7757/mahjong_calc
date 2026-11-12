import 'dart:async';
import 'dart:io';

import 'camera_head.dart';

/// 헤드 녹화 모드(시험용) 프레임을 태블릿으로 계속 받아 온다(`/rec/frames` 이어 받기).
///
/// - 헤드는 프레임을 자기 저장소에 먼저 쓰고, 이쪽은 "받은 마지막 ms 뒤" 를 묶음으로 당긴다 → 망이 끊겨도 다시 붙으면
///   빠진 구간부터 이어 받는다(헤드에 남아 있는 한).
/// - 받은 프레임은 `<baseDir>/rec_pull/<헤드 녹화 폴더 이름>/f_<ms>.jpg` 에 헤드와 같은 이름으로 쓴다(임시 파일 → 이름 바꾸기).
///   앱을 다시 켜도 그 폴더에 있는 마지막 ms 부터 잇는다.
/// - [paused] 가 참이면(화료 판독 중 등) 쉰다 — `/capture`·서버 전송과 대역폭을 다투지 않게.
/// - 이쪽 남은 용량이 [minFreeBytes] 아래면 스스로 멈춘다.
///
/// [save] 가 거짓이면 "보기만": 밀린 프레임은 건너뛰고 가장 최근 한 장만 받아([onFrame]) 저장하지 않는다(실험 자료는 헤드에 있음).
class RecordPuller {
  /// [newest] 면 after 뒤 가장 최근 한 장만(`/rec/frames?newest=1`).
  final Future<RecordBatch> Function(int after, int max, bool newest) fetch;

  /// 받은 프레임을 이 기기에 저장하나. 거짓이면 보기만(저장 공간·따라잡기 대역폭을 안 씀).
  final bool save;

  /// 받은 녹화를 둘 폴더(앱 전용 외부 저장소)와 남은 용량. null 이면 저장할 곳이 없어 시작하지 않는다.
  final Future<({String path, int freeBytes})?> Function() storage;
  final bool Function() paused;
  final void Function()? onChanged;

  /// 따라잡은 상태(헤드에 남은 장수 0)에서 받은 묶음의 마지막 프레임 — 화면에 실시간으로 띄우는 용. 밀린 것을 받는 중에는 부르지 않는다.
  final void Function(RecordFrame frame)? onFrame;
  final int batch;
  final Duration idle;
  final Duration retry;
  final Duration spaceCheck;
  final int minFreeBytes;
  final Future<void> Function(Duration) sleep;

  RecordPuller({
    required this.fetch,
    required this.storage,
    required this.paused,
    this.save = true,
    this.onChanged,
    this.onFrame,
    this.batch = 10,
    this.idle = const Duration(milliseconds: 300),
    this.retry = const Duration(seconds: 2),
    this.spaceCheck = const Duration(seconds: 30),
    this.minFreeBytes = 2 << 30,
    Future<void> Function(Duration)? sleep,
  }) : sleep = sleep ?? Future<void>.delayed;

  bool _running = false;
  bool get running => _running;

  /// 지금 받는 헤드 녹화 폴더 이름.
  String? dir;

  /// 이 폴더에서 받은 마지막 프레임 ms(이 폴더에 이미 있던 것 포함).
  int lastMs = 0;

  /// 이번에 켠 뒤 받은 장수·바이트.
  int received = 0;
  int bytes = 0;

  /// 헤드가 다 쓴 마지막 ms − 받은 마지막 ms. 헤드가 녹화 중일 때만 뜻이 있다.
  int lagMs = 0;
  bool headRecording = false;

  /// 헤드에 남은(아직 안 받은) 장수.
  int remaining = 0;

  /// 마지막 오류(다음에 받으면 지운다).
  String? error;

  /// 스스로 멈춘 까닭(용량 부족·헤드가 녹화를 못 함). 다시 켜면 지운다.
  String? stopMessage;

  /// 저장 폴더(받은 뒤 정해짐).
  String? localDir;

  Completer<void>? _done;
  DateTime? _notifiedAt;

  /// 켠다(이미 켜져 있으면 아무것도 안 함). 루프는 뒤에서 돈다 — [stop] 으로 끈다.
  void start() {
    if (_running) return;
    _running = true;
    stopMessage = null;
    error = null;
    received = 0;
    bytes = 0;
    _done = Completer<void>();
    unawaited(_loop().whenComplete(() => _done?.complete()));
    onChanged?.call();
  }

  /// 끈다. 돌던 묶음 하나는 마저 쓴다. 루프가 끝날 때까지 기다린다.
  Future<void> stop() async {
    if (!_running) return;
    _running = false;
    onChanged?.call();
    await _done?.future;
  }

  void _halt(String message) {
    _running = false;
    stopMessage = message;
    onChanged?.call();
  }

  Future<void> _loop() async {
    if (!save) return _viewLoop();
    var st = await storage();
    if (st == null) {
      _halt('받은 녹화를 둘 저장소가 없습니다(Android 전용)');
      return;
    }
    final base = st.path;
    var spaceAt = DateTime.now();
    if (st.freeBytes >= 0 && st.freeBytes < minFreeBytes) {
      _halt('이 기기 남은 용량이 2GB 아래라 받지 않습니다');
      return;
    }
    while (_running) {
      if (paused()) {
        await sleep(idle);
        continue;
      }
      if (DateTime.now().difference(spaceAt) >= spaceCheck) {
        spaceAt = DateTime.now();
        st = await storage();
        if (st != null && st.freeBytes >= 0 && st.freeBytes < minFreeBytes) {
          _halt('이 기기 남은 용량이 2GB 아래라 멈췄습니다');
          return;
        }
      }
      final RecordBatch b;
      try {
        // 폴더를 아직 모르면 머리만 받아(0장) 폴더를 정하고, 그 폴더에 이미 받은 데까지 건너뛴다.
        b = await fetch(dir == null ? 0 : lastMs, dir == null ? 0 : batch, false);
      } on RemoteCameraException catch (e) {
        if (e.unsupported) {
          _halt('헤드 앱이 녹화 이어 받기를 못 합니다(녹화 모드가 있는 헤드 앱 필요)');
          return;
        }
        error = e.message;
        onChanged?.call();
        await sleep(retry);
        continue;
      } catch (e) {
        error = '$e';
        onChanged?.call();
        await sleep(retry);
        continue;
      }
      error = null;
      headRecording = b.recording;
      remaining = b.remaining;
      final d = b.dir;
      if (d == null) {
        // 헤드가 아직 녹화한 적이 없다.
        dir = null;
        onChanged?.call();
        await sleep(retry);
        continue;
      }
      if (d != dir) {
        // 새 녹화(또는 처음): 이 폴더에 이미 받은 마지막 ms 부터.
        dir = d;
        localDir = '$base/rec_pull/$d';
        lastMs = await _lastLocalMs(localDir!);
        lagMs = 0;
        onChanged?.call();
        continue;
      }
      final out = localDir!;
      try {
        await Directory(out).create(recursive: true);
        for (final f in b.frames) {
          if (f.ms <= lastMs) continue;
          final tmp = File('$out/f_${f.ms}.jpg.part');
          await tmp.writeAsBytes(f.jpeg, flush: false);
          await tmp.rename('$out/f_${f.ms}.jpg');
          lastMs = f.ms;
          received++;
          bytes += f.jpeg.length;
        }
      } on FileSystemException catch (e) {
        _halt('받은 녹화를 쓸 수 없습니다: ${e.message}');
        return;
      }
      if (b.remaining == 0 && b.frames.isNotEmpty && b.frames.last.ms == lastMs) onFrame?.call(b.frames.last);
      final latest = b.latest;
      lagMs = latest == null || latest < lastMs ? 0 : latest - lastMs;
      onChanged?.call();
      if (b.frames.isEmpty || b.remaining == 0) await sleep(b.recording ? idle : retry);
    }
  }

  /// 보기만: [idle] 마다 가장 최근 한 장. 저장·따라잡기 없음. 새 녹화(폴더 바뀜)면 처음부터.
  Future<void> _viewLoop() async {
    while (_running) {
      if (paused()) {
        await sleep(idle);
        continue;
      }
      final RecordBatch b;
      try {
        b = await fetch(lastMs, 1, true);
      } on RemoteCameraException catch (e) {
        if (e.unsupported) {
          _halt('헤드 앱이 녹화 이어 받기를 못 합니다(녹화 모드가 있는 헤드 앱 필요)');
          return;
        }
        error = e.message;
        onChanged?.call();
        await sleep(retry);
        continue;
      } catch (e) {
        error = '$e';
        onChanged?.call();
        await sleep(retry);
        continue;
      }
      error = null;
      headRecording = b.recording;
      remaining = 0;
      if (b.dir != dir) {
        dir = b.dir;
        lastMs = 0;
      }
      if (b.frames.isNotEmpty && b.frames.last.ms > lastMs) {
        final f = b.frames.last;
        lastMs = f.ms;
        received++;
        bytes += f.jpeg.length;
        onFrame?.call(f);
      }
      final latest = b.latest;
      lagMs = latest == null || latest < lastMs ? 0 : latest - lastMs;
      // 화면 갱신 알림은 1초에 한 번만(프레임은 [onFrame] 으로 따로 간다 — 받을 때마다 화면 전체를 다시 그리지 않게).
      final now = DateTime.now();
      if (_notifiedAt == null || now.difference(_notifiedAt!) >= const Duration(seconds: 1)) {
        _notifiedAt = now;
        onChanged?.call();
      }
      await sleep(b.dir == null ? retry : idle);
    }
  }

  /// 폴더에 이미 있는 `f_<ms>.jpg` 중 가장 늦은 ms. 없으면 0.
  static Future<int> _lastLocalMs(String path) async {
    final d = Directory(path);
    if (!await d.exists()) return 0;
    var best = 0;
    await for (final e in d.list()) {
      final name = e.path.replaceAll('\\', '/').split('/').last;
      final m = RegExp(r'^f_(\d+)\.jpg$').firstMatch(name);
      if (m == null) continue;
      final v = int.parse(m.group(1)!);
      if (v > best) best = v;
    }
    return best;
  }
}
