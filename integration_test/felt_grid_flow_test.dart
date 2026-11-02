// 펠트 격자 자동 맞추기를 실제 거치 화면으로 본다(2026-11-02). 카메라 헤드와 인식 서버는 이 테스트 안의 작은 HTTP 서버가 대신한다.
//   flutter drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/felt_grid_flow_test.dart \
//     --dart-define=RECOGNIZER_URL=http://127.0.0.1:8799 --dart-define=RECOGNIZER_API_KEY=local
// 사진은 experiments/visit_20261031/captures(커밋 안 함), 결과는 콘솔 [felt_flow] 줄. 같은 폴더에서 다른 flutter drive 와 겹치면
// build/windows 를 함께 써 엉뚱한 테스트가 뜬다(2026-11-02 실제로 겪음): "[felt_flow]" 줄이 있는지 꼭 볼 것.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/table/felt_grid.dart';
import 'package:mahjong_calc/table/grid_zones.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _captures = String.fromEnvironment('CAPTURES', defaultValue: r'C:\Users\jjh7757\dev\mahjong_calc\experiments\visit_20261031\captures');
const _port = 8799; // RECOGNIZER_URL 과 같게

/// 헤드(/status·/preview·/capture)와 서버(/v2/setup)를 한 포트에서. [setupCalls] = 서버 자동 맞추기를 부른 수.
class _Fake {
  HttpServer? _server;
  Uint8List frame = Uint8List(0);
  String size = '1020x765';
  int setupCalls = 0;

  Future<void> start() async {
    final s = await HttpServer.bind(InternetAddress.loopbackIPv4, _port);
    _server = s;
    s.listen((req) async {
      final path = req.uri.path;
      final res = req.response;
      res.headers.set('Cache-Control', 'no-store');
      if (path == '/' || path == '/status') {
        res.headers.contentType = ContentType.json;
        res.write(jsonEncode({'ok': true, 'auth': true, 'captures': 0}));
      } else if (path == '/preview' || path == '/capture') {
        res.headers.contentType = ContentType('image', 'jpeg');
        res.headers.set('X-Frame-Size', size);
        res.headers.set('X-Zoom', '1.00');
        res.add(frame);
      } else {
        await req.drain<void>();
        if (path.contains('setup')) setupCalls++;
        res.headers.contentType = ContentType.json;
        res.write(jsonEncode({'seats': {}, 'device': null}));
      }
      await res.close();
    });
  }

  Future<void> stop() async => _server?.close(force: true);
}

img.Image _small(String photo) {
  final im = img.decodeJpg(File('$_captures/20261031_$photo/original.jpg').readAsBytesSync())!;
  return img.copyResize(im, width: 1020, height: 765, interpolation: img.Interpolation.linear);
}

Uint8List _jpg(img.Image im) => img.encodeJpg(im, quality: 88);

/// 초록을 파랑으로 바꾼 사진(다른 색 펠트 흉내).
img.Image _blueFelt(img.Image src) {
  final o = img.Image.from(src);
  for (final p in o) {
    final g = p.g, b = p.b;
    p.g = b;
    p.b = g;
  }
  return o;
}

Future<GridZones?> _savedGrid() async {
  final p = await SharedPreferences.getInstance();
  await p.reload();
  final s = p.getString('mount.grid');
  return s == null ? null : GridZones.fromJson(jsonDecode(s) as Map<String, dynamic>);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('펠트 격자: 처음 카메라, 카메라 이동, 탁자 없음, 손으로 맞춘 격자, 다른 색 펠트, 서버로 넘어감', (tester) async {
    tester.view.physicalSize = const Size(2560, 1600);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    final fake = _Fake();
    await fake.start();
    addTearDown(fake.stop);
    const head = 'http://127.0.0.1:$_port';

    final a = _small('131411'), b = _small('130743');
    final floor = img.Image(width: 1020, height: 765);
    img.fill(floor, color: img.ColorRgb8(120, 110, 100));
    final gridA = gridFromFelt(feltQuadOfJpeg(_jpg(a))!)!, gridB = gridFromFelt(feltQuadOfJpeg(_jpg(b))!)!;
    // ignore: avoid_print
    print('[felt_flow] 기대 격자 A ${gridA.toJson()} / B ${gridB.toJson()}');

    Future<void> run(bool Function() done, String what, {int seconds = 60}) async {
      final sw = Stopwatch()..start();
      while (sw.elapsed < Duration(seconds: seconds)) {
        await tester.pump(const Duration(milliseconds: 300));
        await Future<void>.delayed(const Duration(milliseconds: 300));
        if (done()) return;
      }
      fail('$what 을(를) $seconds초 안에 못 봄');
    }

    Future<void> open(Map<String, Object> prefs) async {
      SharedPreferences.setMockInitialValues({
        'mount.remoteUrl': head,
        'mount.remoteToken': 'local',
        'mount.useGrid': true,
        'mount.tracking': false,
        ...prefs,
      });
      gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
      await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
      await run(() => find.byKey(const ValueKey('table-calc')).evaluate().isNotEmpty, '테이블 화면', seconds: 30);
    }

    Future<void> close() async {
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 1));
      gameStore.discardCurrent();
    }

    void sameGrid(GridZones? got, GridZones want, String what) {
      expect(got, isNotNull, reason: what);
      for (final (g, w) in [(got!.x1, want.x1), (got.x2, want.x2), (got.y1, want.y1), (got.y2, want.y2)]) {
        expect((g - w).abs(), lessThanOrEqualTo(3), reason: '$what: ${got.toJson()} vs ${want.toJson()}');
      }
    }

    // 1) 처음 보는 카메라: 서버 없이 펠트로 격자를 맞추고 저장한다.
    fake.frame = _jpg(a);
    var sw = Stopwatch()..start();
    await open({});
    await run(() => find.textContaining('펠트로 맞췄습니다').evaluate().isNotEmpty, '펠트 자동 맞추기 토스트');
    await tester.pump(const Duration(seconds: 1));
    sameGrid(await _savedGrid(), gridA, '처음 카메라');
    expect(fake.setupCalls, 0, reason: '펠트를 찾으면 서버를 안 부른다');
    // ignore: avoid_print
    print('[felt_flow] 1 처음 카메라 ${sw.elapsedMilliseconds}ms, 서버 호출 ${fake.setupCalls}');

    // 2) 같은 자리면 격자가 그대로다(몇 번 읽는 동안).
    await Future<void>.delayed(const Duration(seconds: 12));
    await tester.pump(const Duration(seconds: 1));
    sameGrid(await _savedGrid(), gridA, '같은 자리');

    // 3) 탁자가 안 보이면(바닥) 격자를 건드리지 않는다.
    fake.frame = _jpg(floor);
    final stop = DateTime.now().add(const Duration(seconds: 20));
    while (DateTime.now().isBefore(stop)) {
      await tester.pump(const Duration(milliseconds: 500));
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
    sameGrid(await _savedGrid(), gridA, '탁자 안 보임');
    expect(find.textContaining('카메라가 움직여'), findsNothing);
    // ignore: avoid_print
    print('[felt_flow] 3 탁자 안 보임: 격자 그대로');

    // 4) 카메라가 옮겨져 멈추면 다시 맞춘다.
    fake.frame = _jpg(b);
    sw = Stopwatch()..start();
    await run(() => find.textContaining('카메라가 움직여').evaluate().isNotEmpty, '이동 토스트', seconds: 90);
    await tester.pump(const Duration(seconds: 1));
    sameGrid(await _savedGrid(), gridB, '카메라 이동');
    // ignore: avoid_print
    print('[felt_flow] 4 카메라 이동 뒤 ${sw.elapsedMilliseconds}ms 에 다시 맞춤');
    await close();

    // 5) 손으로 맞춘 격자: 같은 자리면 덮어쓰지 않고, 카메라가 옮겨지면 그때 맞춘다.
    const hand = GridZones(x1: 300, x2: 700, y1: 200, y2: 800);
    fake.frame = _jpg(b);
    await open({'mount.grid': jsonEncode(hand.toJson()), 'mount.gridSource': head});
    final stop2 = DateTime.now().add(const Duration(seconds: 30));
    while (DateTime.now().isBefore(stop2)) {
      await tester.pump(const Duration(milliseconds: 500));
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
    sameGrid(await _savedGrid(), hand, '손으로 맞춘 격자');
    expect(find.textContaining('펠트로 맞췄습니다'), findsNothing);
    fake.frame = _jpg(a);
    await run(() => find.textContaining('카메라가 움직여').evaluate().isNotEmpty, '손 격자 뒤 이동 토스트', seconds: 90);
    await tester.pump(const Duration(seconds: 1));
    sameGrid(await _savedGrid(), gridA, '손 격자 뒤 이동');
    // ignore: avoid_print
    print('[felt_flow] 5 손 격자 유지, 이동하면 다시 맞춤');
    await close();

    // 6) 펠트 색이 달라도 그 사진의 색을 재서 맞춘다. 앱이 켜져 있는 동안 카메라당 한 번이라 다른 주소로 연다.
    final blue = _blueFelt(a);
    final gridBlue = gridFromFelt(feltQuadOfJpeg(_jpg(blue))!)!;
    fake.frame = _jpg(blue);
    await open({'mount.remoteUrl': 'http://localhost:$_port'});
    await run(() => find.textContaining('펠트로 맞췄습니다').evaluate().isNotEmpty, '다른 색 펠트 토스트');
    await tester.pump(const Duration(seconds: 1));
    sameGrid(await _savedGrid(), gridBlue, '다른 색 펠트');
    sameGrid(gridBlue, gridA, '다른 색 펠트도 같은 자리');
    expect(fake.setupCalls, 0);
    // ignore: avoid_print
    print('[felt_flow] 6 파란 펠트: 펠트로 맞춤, 서버 호출 0');
    await close();

    // 7) 탁자가 안 보이면(펠트를 못 믿으면) 서버 자동 맞추기로 넘어간다.
    fake.frame = _jpg(floor);
    await open({}); // 마지막으로 자동 맞추기를 돈 카메라는 6) 의 주소라 이 주소로 다시 돈다.
    await run(() => fake.setupCalls > 0, '서버 자동 맞추기 호출');
    expect(find.textContaining('펠트로 맞췄습니다'), findsNothing);
    // ignore: avoid_print
    print('[felt_flow] 7 탁자 없음: 서버 호출 ${fake.setupCalls}');
    await close();
  }, timeout: const Timeout(Duration(minutes: 12)));
}
