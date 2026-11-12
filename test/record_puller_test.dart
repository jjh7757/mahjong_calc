import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mahjong_calc/services/camera_head.dart';
import 'package:mahjong_calc/services/record_puller.dart';

const String _tok = 'test-token-rec';

Uint8List _jpg(int n) => Uint8List.fromList([0xFF, 0xD8, n & 0xFF, (n >> 8) & 0xFF, 0xFF, 0xD9]);

/// 헤드 녹화를 흉내: 다 쓴 프레임 ms 목록과 그 내용.
class _FakeHead {
  String? dir = 'rec_20261112_120000';
  bool recording = true;
  final List<int> ms = [];
  int calls = 0;
  void add(int n, {int start = 1000}) {
    for (var i = 0; i < n; i++) {
      ms.add(start + ms.length * 100);
    }
  }

  Future<RecordBatch> frames(int after, int max, [bool newest = false]) async {
    calls++;
    final d = dir;
    if (d == null) return RecordBatch(recording: recording);
    final next = ms.where((m) => m > after).toList();
    final take = newest ? (next.isEmpty || max == 0 ? <int>[] : [next.last]) : next.take(max).toList();
    return RecordBatch(
      dir: d,
      recording: recording,
      latest: ms.isEmpty ? null : ms.last,
      remaining: next.length - take.length,
      frames: [for (final m in take) RecordFrame(m, _jpg(m))],
    );
  }
}

Future<void> _until(bool Function() cond, {Duration limit = const Duration(seconds: 5)}) async {
  final end = DateTime.now().add(limit);
  while (!cond()) {
    if (DateTime.now().isAfter(end)) fail('시간 안에 조건이 안 됨');
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}

void main() {
  group('RecordBatch', () {
    test('본문·헤더 왕복', () {
      final b = RecordBatch(
        dir: 'rec_x',
        recording: true,
        latest: 1700000000123,
        remaining: 4,
        frames: [RecordFrame(1700000000000, _jpg(1)), RecordFrame(1700000000100, _jpg(2))],
      );
      final h = {for (final e in b.headers().entries) e.key.toLowerCase(): e.value};
      final d = RecordBatch.decode(h, b.encodeBody());
      expect(d.dir, 'rec_x');
      expect(d.recording, isTrue);
      expect(d.latest, 1700000000123);
      expect(d.remaining, 4);
      expect([for (final f in d.frames) f.ms], [1700000000000, 1700000000100]);
      expect(d.frames[1].jpeg, _jpg(2));
    });

    test('빈 묶음·녹화한 적 없음', () {
      final d = RecordBatch.decode({'x-rec-recording': '0'}, Uint8List(0));
      expect(d.dir, isNull);
      expect(d.frames, isEmpty);
    });

    test('잘린 본문은 FormatException', () {
      final body = RecordBatch(frames: [RecordFrame(1, _jpg(1))]).encodeBody();
      expect(() => RecordBatch.decode({}, Uint8List.sublistView(body, 0, body.length - 1)), throwsFormatException);
    });
  });

  group('/rec/frames', () {
    late CameraHeadServer server;
    late _FakeHead head;
    setUp(() async {
      head = _FakeHead()..add(25);
      server = CameraHeadServer(
        capture: () async => _jpg(0),
        token: _tok,
        recordFrames: head.frames,
      );
      await server.start(port: 0, address: InternetAddress.loopbackIPv4);
    });
    tearDown(() => server.stop());

    test('after 뒤를 max 장까지, 남은 장수와 함께', () async {
      final cam = RemoteCamera('http://127.0.0.1:${server.port}', token: _tok);
      final b = await cam.recordFrames(after: head.ms[2], max: 5);
      cam.close();
      expect([for (final f in b.frames) f.ms], head.ms.sublist(3, 8));
      expect(b.remaining, 25 - 8);
      expect(b.dir, 'rec_20261112_120000');
      expect(b.latest, head.ms.last);
      expect(b.frames.first.jpeg, _jpg(head.ms[3]));
    });

    test('newest=1 은 밀린 것을 건너뛰고 가장 최근 한 장만', () async {
      final cam = RemoteCamera('http://127.0.0.1:${server.port}', token: _tok);
      final b = await cam.recordFrames(after: head.ms[2], max: 1, newest: true);
      final none = await cam.recordFrames(after: head.ms.last, max: 1, newest: true);
      cam.close();
      expect([for (final f in b.frames) f.ms], [head.ms.last]);
      expect(b.latest, head.ms.last);
      expect(none.frames, isEmpty);
    });

    test('max 는 30 장으로 자른다', () async {
      head.add(40);
      final cam = RemoteCamera('http://127.0.0.1:${server.port}', token: _tok);
      final b = await cam.recordFrames(after: 0, max: 999);
      cam.close();
      expect(b.frames.length, CameraHeadServer.maxRecordBatch);
    });

    test('토큰이 틀리면 unauthorized', () async {
      final cam = RemoteCamera('http://127.0.0.1:${server.port}', token: 'wrong');
      await expectLater(
        cam.recordFrames(after: 0),
        throwsA(isA<RemoteCameraException>().having((e) => e.unauthorized, 'unauthorized', isTrue)),
      );
      cam.close();
    });

    test('녹화를 못 하는 헤드는 unsupported', () async {
      final old = CameraHeadServer(capture: () async => _jpg(0), token: _tok);
      await old.start(port: 0, address: InternetAddress.loopbackIPv4);
      final cam = RemoteCamera('http://127.0.0.1:${old.port}', token: _tok);
      await expectLater(
        cam.recordFrames(after: 0),
        throwsA(isA<RemoteCameraException>().having((e) => e.unsupported, 'unsupported', isTrue)),
      );
      cam.close();
      await old.stop();
    });
  });

  group('RecordPuller', () {
    late Directory tmp;
    setUp(() async => tmp = await Directory.systemTemp.createTemp('recpull'));
    tearDown(() async {
      if (await tmp.exists()) await tmp.delete(recursive: true);
    });

    RecordPuller make(_FakeHead head, {bool Function()? paused, int free = 100 << 30}) => RecordPuller(
          fetch: (a, m, n) => head.frames(a, m, n),
          storage: () async => (path: tmp.path, freeBytes: free),
          paused: paused ?? () => false,
          batch: 4,
          idle: const Duration(milliseconds: 1),
          retry: const Duration(milliseconds: 1),
        );

    List<int> saved(String dir) {
      final d = Directory('${tmp.path}/rec_pull/$dir');
      if (!d.existsSync()) return [];
      final out = <int>[];
      for (final e in d.listSync()) {
        final m = RegExp(r'f_(\d+)\.jpg$').firstMatch(e.path);
        if (m != null) out.add(int.parse(m.group(1)!));
        expect(e.path.endsWith('.part'), isFalse);
      }
      return out..sort();
    }

    test('헤드에 쌓인 프레임을 이어 받아 같은 이름으로 쓴다, 새로 쌓이면 또 받는다', () async {
      final head = _FakeHead()..add(10);
      final p = make(head);
      p.start();
      await _until(() => p.received == 10);
      head.add(3);
      await _until(() => p.received == 13);
      await p.stop();
      expect(saved(head.dir!), head.ms);
      expect(File('${tmp.path}/rec_pull/${head.dir}/f_${head.ms[4]}.jpg').readAsBytesSync(), _jpg(head.ms[4]));
      expect(p.lagMs, 0);
    });

    test('밀린 것을 받는 동안은 화면용 프레임을 안 주고, 따라잡은 뒤엔 최신 프레임을 준다', () async {
      final head = _FakeHead()..add(10);
      final shown = <int>[];
      final p = RecordPuller(
        fetch: (a, m, n) => head.frames(a, m, n),
        storage: () async => (path: tmp.path, freeBytes: 100 << 30),
        paused: () => false,
        onFrame: (f) => shown.add(f.ms),
        batch: 4,
        idle: const Duration(milliseconds: 1),
        retry: const Duration(milliseconds: 1),
      );
      p.start();
      await _until(() => p.received == 10);
      // 4·4 는 밀린 묶음(남은 장수 > 0), 마지막 2장 묶음에서 처음 준다.
      expect(shown, [head.ms[9]]);
      head.add(1);
      await _until(() => p.received == 11);
      await p.stop();
      expect(shown, [head.ms[9], head.ms[10]]);
    });

    test('다시 켜면 폴더에 이미 받은 데 뒤부터(겹쳐 받지 않음)', () async {
      final head = _FakeHead()..add(6);
      final p1 = make(head);
      p1.start();
      await _until(() => p1.received == 6);
      await p1.stop();
      head.add(4);
      final p2 = make(head);
      p2.start();
      await _until(() => p2.received == 4);
      await p2.stop();
      expect(saved(head.dir!), head.ms);
    });

    test('헤드가 새 녹화를 시작하면 새 폴더로', () async {
      final head = _FakeHead()..add(3);
      final p = make(head);
      p.start();
      await _until(() => p.received == 3);
      final first = head.dir!;
      head
        ..dir = 'rec_20261112_130000'
        ..ms.clear()
        ..add(2, start: 5000);
      await _until(() => p.received == 5);
      await p.stop();
      expect(saved(first).length, 3);
      expect(saved('rec_20261112_130000'), head.ms);
    });

    test('쉬는 동안(paused)은 묻지 않는다', () async {
      final head = _FakeHead()..add(5);
      var pause = true;
      final p = make(head, paused: () => pause);
      p.start();
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(head.calls, 0);
      pause = false;
      await _until(() => p.received == 5);
      await p.stop();
    });

    test('연결 오류는 다시 시도하고, 녹화 못 하는 헤드면 멈춘다', () async {
      var fails = 2;
      final head = _FakeHead()..add(2);
      final p = RecordPuller(
        fetch: (a, m, n) async {
          if (fails-- > 0) throw const RemoteCameraException('안 닿음', unreachable: true);
          return head.frames(a, m, n);
        },
        storage: () async => (path: tmp.path, freeBytes: 100 << 30),
        paused: () => false,
        idle: const Duration(milliseconds: 1),
        retry: const Duration(milliseconds: 1),
      );
      p.start();
      await _until(() => p.received == 2);
      await p.stop();

      final q = RecordPuller(
        fetch: (a, m, n) async => throw const RemoteCameraException('없음', unsupported: true),
        storage: () async => (path: tmp.path, freeBytes: 100 << 30),
        paused: () => false,
        retry: const Duration(milliseconds: 1),
      );
      q.start();
      await _until(() => !q.running);
      expect(q.stopMessage, contains('헤드 앱'));
    });

    test('보기만: 최신 한 장씩 화면용으로 주고 파일은 쓰지 않는다', () async {
      final head = _FakeHead()..add(20);
      final shown = <int>[];
      final p = RecordPuller(
        fetch: (a, m, n) => head.frames(a, m, n),
        storage: () async => throw StateError('보기만은 저장소를 묻지 않는다'),
        paused: () => false,
        save: false,
        onFrame: (f) => shown.add(f.ms),
        idle: const Duration(milliseconds: 1),
        retry: const Duration(milliseconds: 1),
      );
      p.start();
      await _until(() => shown.isNotEmpty);
      expect(shown.first, head.ms.last); // 밀린 19장은 건너뜀
      head.add(1);
      await _until(() => shown.length == 2);
      await p.stop();
      expect(shown, [head.ms[19], head.ms[20]]);
      expect(Directory('${tmp.path}/rec_pull').existsSync(), isFalse);
    });

    test('남은 용량이 2GB 아래면 시작하지 않는다', () async {
      final head = _FakeHead()..add(2);
      final p = make(head, free: 1 << 30);
      p.start();
      await _until(() => !p.running);
      expect(p.stopMessage, contains('2GB'));
      expect(head.calls, 0);
    });
  });
}
