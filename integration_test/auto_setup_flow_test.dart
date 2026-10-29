// 대국 시작 직후 자동 맞추기 → 화료 촬영 → 결과까지, 노트북(Windows)에서 실제 앱 흐름으로 시간을 잰다.
// 카메라 헤드는 이 테스트 안의 작은 HTTP 서버가 대신한다(/status·/preview·/capture 가 장면 사진 한 장을 준다).
// 장면마다 새 대국을 시작해 테이블 화면이 뜬 때부터 "대국 시작 자동 맞추기" 토스트까지(자동 맞추기),
// "화료 촬영" 을 누른 때부터 결과 화면까지(앱 흐름) 재고, 결과 화면의 점수를 정답과 비교한다.
//
//   flutter drive --profile -d windows --driver=test_driver/integration_test.dart \
//     --target=integration_test/auto_setup_flow_test.dart --dart-define=RECOGNIZER_API_KEY=<키> \
//     [--dart-define=SCENES=k25,k28,k15,k26,k12,k16] [--dart-define=ROUNDS=1] [--dart-define=PHOTO_DIR=...]
// 결과는 콘솔 [auto_setup] 줄과 OUT(기본 %TEMP%/mahjong_auto_setup_itest)/result.json.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/services/capture_log.dart';
import 'package:mahjong_calc/ui/input_screen.dart';
import 'package:mahjong_calc/ui/result_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _photoDir = String.fromEnvironment(
  'PHOTO_DIR',
  defaultValue: r'C:\Users\jjh7757\dev\mahjong_calc\experiments\field_20261024\kakao_photos',
);
const _scenesEnv = String.fromEnvironment('SCENES', defaultValue: 'k25,k28,k15,k26,k12,k16');
const _rounds = int.fromEnvironment('ROUNDS', defaultValue: 1);
const _outEnv = String.fromEnvironment('OUT', defaultValue: '');
/// 장면 사이 쉬는 시간(초). 연달아 부르면 서버가 "요청이 너무 많습니다"(429) 로 거절한다(10-29 k26 에서 강 끝·리치봉·도라 모두).
const _sleepS = int.fromEnvironment('SLEEP_S', defaultValue: 30);

/// 정답(experiments/field_20261024/NOTES.md "촬영별"): B 오른쪽 12000, C 배만 16000, D 아래 하네만 18000.
const _answers = {'k25': 12000, 'k28': 12000, 'k15': 16000, 'k26': 16000, 'k12': 18000, 'k16': 18000};

/// 장면 사진 한 장을 카메라 헤드처럼 준다.
class _FakeHead {
  HttpServer? _server;
  Uint8List bytes = Uint8List(0);
  String frameSize = '0x0';
  int captures = 0;
  int previews = 0;

  Future<String> start() async {
    final s = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server = s;
    s.listen((req) async {
      final path = req.uri.path;
      final res = req.response;
      res.headers.set('Cache-Control', 'no-store');
      if (path == '/' || path == '/status') {
        res.headers.contentType = ContentType.json;
        res.write(jsonEncode({'ok': true, 'auth': true, 'captures': captures}));
      } else if (path == '/preview' || path == '/capture') {
        if (path == '/capture') {
          captures++;
        } else {
          previews++;
        }
        res.headers.contentType = ContentType('image', 'jpeg');
        res.headers.set('X-Frame-Size', frameSize);
        res.headers.set('X-Zoom', '1.00');
        res.add(bytes);
      } else {
        res.statusCode = 404;
      }
      await res.close();
    });
    return 'http://127.0.0.1:${s.port}';
  }

  Future<void> load(File f) async {
    bytes = await f.readAsBytes();
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    frameSize = '${frame.image.width}x${frame.image.height}';
    frame.image.dispose();
    codec.dispose();
  }

  Future<void> stop() async => _server?.close(force: true);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('대국 시작 → 자동 맞추기 → 화료 촬영 → 결과: 장면별 시간·점수', (tester) async {
    final out = _outEnv.isNotEmpty ? _outEnv : '${Directory.systemTemp.path}/mahjong_auto_setup_itest';
    CaptureLog.desktopRootOverride = out;
    tester.view.physicalSize = const Size(2560, 1600);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    final head = _FakeHead();
    final headUrl = await head.start();
    addTearDown(head.stop);

    final scenes = _scenesEnv.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();
    final results = <Map<String, dynamic>>[];

    // 지금 화면 요약(진단): 결과 화면·대화상자 수와 보이는 글자 일부.
    String snapshot() {
      final texts = <String>{};
      for (final e in find.byType(Text).evaluate()) {
        final d = (e.widget as Text).data;
        if (d != null && d.trim().isNotEmpty) texts.add(d.length > 40 ? d.substring(0, 40) : d);
      }
      for (final e in find.byType(RichText).evaluate()) {
        final d = (e.widget as RichText).text.toPlainText();
        if (d.trim().isNotEmpty) texts.add(d.length > 40 ? d.substring(0, 40) : d);
      }
      final dialogTexts = <String>[];
      for (final e in find.descendant(of: find.byType(AlertDialog), matching: find.byType(Text)).evaluate()) {
        final d = (e.widget as Text).data;
        if (d != null) dialogTexts.add(d);
      }
      return 'result=${find.byType(ResultScreen).evaluate().length} '
          'alert=${find.byType(AlertDialog).evaluate().length}[${dialogTexts.join(' / ')}] '
          'simple=${find.byType(SimpleDialog).evaluate().length} '
          'snack=${find.byType(SnackBar).evaluate().length} texts(${texts.length})=${texts.skip(20).take(40).join(' | ')}';
    }

    Future<void> waitFor(WidgetTester t, bool Function() done, String what, {int seconds = 120}) async {
      final sw = Stopwatch()..start();
      var nextReport = 20;
      while (sw.elapsed < Duration(seconds: seconds)) {
        await t.pump(const Duration(milliseconds: 500));
        await Future<void>.delayed(const Duration(milliseconds: 500));
        if (done()) return;
        if (sw.elapsed.inSeconds >= nextReport) {
          nextReport += 20;
          // ignore: avoid_print
          print('[auto_setup] …$what 기다리는 중 ${sw.elapsed.inSeconds}초: ${snapshot()}');
        }
      }
      fail('$what 을(를) $seconds초 안에 못 봄 — ${snapshot()}');
    }

    for (var round = 0; round < _rounds; round++) {
      for (final scene in scenes) {
        final file = File('$_photoDir${Platform.pathSeparator}$scene.jpg');
        if (!file.existsSync()) {
          // ignore: avoid_print
          print('[auto_setup] $scene: 사진 없음 ${file.path}');
          continue;
        }
        if (results.isNotEmpty && _sleepS > 0) await Future<void>.delayed(Duration(seconds: _sleepS));
        await head.load(file);
        final capturesBefore = head.captures;
        SharedPreferences.setMockInitialValues({
          'mount.remoteUrl': headUrl,
          'mount.remoteToken': 'local',
          'mount.useGrid': true,
          // 추적·자동 맞추기는 기본값(켬) 그대로 — 실제 태블릿과 같은 조건.
        });
        gameStore.start(const ['A', 'B', 'C', 'D'], const GameSettings());
        final row = <String, dynamic>{'scene': scene, 'round': round + 1, 'answer': _answers[scene]};

        await tester.pumpWidget(const MahjongApp(loadSavedRules: false));
        await waitFor(tester, () => find.byKey(const ValueKey('table-calc')).evaluate().isNotEmpty, '테이블 화면',
            seconds: 30);
        final tableAt = DateTime.now();

        // 1) 자동 맞추기: 토스트 "격자 자동 맞추기 (N.N초, 이 카메라로 처음): ..." 가 뜰 때까지(장면마다 설정을 비워 카메라를 새로 본 것과 같다).
        String? setupToast;
        await waitFor(tester, () {
          final f = find.textContaining('격자 자동 맞추기');
          if (f.evaluate().isEmpty) return false;
          setupToast = (f.evaluate().first.widget as Text).data;
          return true;
        }, '자동 맞추기 토스트', seconds: 180);
        final setupMs = DateTime.now().difference(tableAt).inMilliseconds;
        row['setup_from_table_ms'] = setupMs;
        row['setup_toast'] = setupToast;
        row['setup_grid'] = setupToast?.contains('맞췄습니다') ?? false;
        row['setup_wall'] = setupToast?.contains('도라 산을 찾았습니다') ?? false;
        final inner = RegExp(r'\(([\d.]+)초\)').firstMatch(setupToast ?? '');
        row['setup_call_s'] = inner == null ? null : double.tryParse(inner.group(1)!);
        // ignore: avoid_print
        print('[auto_setup] $scene r${round + 1}: 자동 맞추기 테이블 뜬 뒤 ${(setupMs / 1000).toStringAsFixed(1)}초 — $setupToast');

        // 토스트가 사라지고 배경 틱이 한 번 돌 때까지 잠깐.
        await tester.pump(const Duration(seconds: 1));
        await Future<void>.delayed(const Duration(seconds: 2));

        // 2) 화료 촬영 → 결과 화면(점수).
        final shoot = find.byKey(const ValueKey('mount-shoot'));
        await waitFor(tester, () {
          final e = shoot.evaluate();
          return e.isNotEmpty && (e.first.widget as FilledButton).onPressed != null;
        }, '화료 촬영 버튼 활성', seconds: 30);
        final shootAt = DateTime.now();
        await tester.tap(shoot);
        String? picked;
        String? lastSnack;
        await waitFor(tester, () {
          for (final e in find.descendant(of: find.byType(SnackBar), matching: find.byType(Text)).evaluate()) {
            final d = (e.widget as Text).data;
            if (d != null && d.length > 8) lastSnack = d;
          }
          // 눕힌 손패가 여럿이면 묻는 창: 첫 후보를 고른다(사진엔 화료자 하나).
          final ask = find.textContaining('누가 났나요');
          if (ask.evaluate().isNotEmpty && picked == null) {
            final opts = find.descendant(of: find.byType(SimpleDialogOption), matching: find.byType(Text));
            if (opts.evaluate().isNotEmpty) {
              picked = (opts.evaluate().first.widget as Text).data;
              unawaited(tester.tap(find.byType(SimpleDialogOption).first));
            }
            return false;
          }
          // 결과 화면, 또는 장수가 안 맞아 입력 화면으로 간 경우.
          return find.byType(ResultScreen).evaluate().isNotEmpty || find.byType(InputScreen).evaluate().isNotEmpty;
        }, '결과 화면', seconds: 180);
        final flowMs = DateTime.now().difference(shootAt).inMilliseconds;
        row['flow_ms'] = flowMs;
        row['picked_winner'] = picked;
        row['captures'] = head.captures - capturesBefore;
        final answer = _answers[scene];
        final gotResult = find.byType(ResultScreen).evaluate().isNotEmpty;
        row['outcome'] = gotResult ? 'result' : 'input';
        row['toast'] = lastSnack;

        if (gotResult) {
          // 결과 화면의 큰 점수(RichText) — 네 자리 이상 숫자 중 시작점 25000 이 아닌 것.
          final nums = <String>{};
          for (final e in find.byType(RichText).evaluate()) {
            final t = (e.widget as RichText).text.toPlainText();
            for (final m in RegExp(r'\d{4,6}').allMatches(t)) {
              if (m.group(0) != '25000') nums.add(m.group(0)!);
            }
          }
          for (final e in find.byType(Text).evaluate()) {
            final t = (e.widget as Text).data ?? '';
            for (final m in RegExp(r'\d{4,6}').allMatches(t)) {
              if (m.group(0) != '25000') nums.add(m.group(0)!);
            }
          }
          row['points_seen'] = nums.toList();
          row['correct'] = answer != null && nums.contains('$answer');
          row['auto_bar'] = find.byKey(const ValueKey('result-auto-bar')).evaluate().isNotEmpty;
          // ignore: avoid_print
          print('[auto_setup] $scene r${round + 1}: 화료 촬영 → 결과 ${(flowMs / 1000).toStringAsFixed(1)}초, '
              '점수 ${nums.join('/')} (정답 $answer, ${row['correct'] == true ? '맞음' : '틀림'}), '
              '자동 반영 줄 ${row['auto_bar']}, 헤드 촬영 ${row['captures']}회${picked == null ? '' : ', 화료자 물음 → $picked'}');
        } else {
          row['points_seen'] = const <String>[];
          row['correct'] = false;
          row['auto_bar'] = false;
          // ignore: avoid_print
          print('[auto_setup] $scene r${round + 1}: 화료 촬영 → 입력 화면(손패 불완전) ${(flowMs / 1000).toStringAsFixed(1)}초, '
              '정답 $answer 못 냄, 헤드 촬영 ${row['captures']}회 — $lastSnack');
        }
        results.add(row);

        // 정리: 결과 화면·거치 화면을 내려 타이머를 멈추고 대국을 버린다.
        await tester.pumpWidget(const SizedBox());
        await tester.pump(const Duration(seconds: 1));
        gameStore.discardCurrent();
        await Future<void>.delayed(const Duration(seconds: 2));
      }
    }

    final dir = Directory(out)..createSync(recursive: true);
    File('${dir.path}/result.json').writeAsStringSync(const JsonEncoder.withIndent(' ').convert({
      'at': DateTime.now().toIso8601String(),
      'photo_dir': _photoDir,
      'rows': results,
    }));
    // ignore: avoid_print
    print('[auto_setup] 결과 ${results.length}회 → ${dir.path}/result.json');
    expect(results, isNotEmpty);
  });
}
