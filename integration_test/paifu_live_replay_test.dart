// 저장된 판 중 프레임을 실제 시각 간격대로 내주는 가짜 헤드(experiments/paifu_frames/replay_head.py)에 거치 화면을 붙여,
// 3초 미리보기 → 추적 → 겹쳐 보기(기기 판독) → 버림 기록기까지 앱이 도는 그대로 돌리고 판이 끝났을 때의 기록기 상태를 내보낸다.
// 화료 촬영 · 패보 저장은 누르지 않는다(기록기 상태만 본다).
//
// PC:    python -X utf8 experiments/paifu_frames/replay_head.py 8777   +   adb reverse tcp:8777 tcp:8777
// 태블릿: flutter drive --profile -d <기기> --driver=test_driver/integration_test.dart \
//           --target=integration_test/paifu_live_replay_test.dart --dart-define=UNITS=h20_143236,h14full_133610
// 결과는 가짜 헤드가 받아 experiments/paifu_frames/results/device_1117/live/<묶음>.json (replay_recorder.dart 와 같은 꼴) 로 쓴다.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';
import 'package:mahjong_calc/game/game.dart';
import 'package:mahjong_calc/game/game_store.dart';
import 'package:mahjong_calc/main.dart';
import 'package:mahjong_calc/table/table_layout.dart';
import 'package:mahjong_calc/ui/mount/mount_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _head = String.fromEnvironment('HEAD_URL', defaultValue: 'http://127.0.0.1:8777');
const _units = String.fromEnvironment('UNITS', defaultValue: 'h20_143236');

String _hms(DateTime t) => t.toIso8601String().substring(11, 19);

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('저장 프레임 실시간 재생 → 거치 화면 버림 기록기', (tester) async {
    tester.view.physicalSize = const Size(2560, 1600);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    for (final unit in _units.split(',')) {
      final info = jsonDecode(utf8.decode((await http.get(Uri.parse('$_head/ctl?unit=$unit'))).bodyBytes)) as Map<String, dynamic>;
      SharedPreferences.setMockInitialValues({
        'mount.remoteUrl': _head,
        'mount.gridSource': _head, // 이 카메라로 격자를 잡았다 → 판 상태 추적이 돈다
        'mount.remoteToken': 'local',
        'mount.tracking': true,
        'mount.useGrid': true,
        'mount.autoSetupOnStart': false, // 격자는 펠트로 고친 값(C)을 그대로 준다
        'mount.grid': jsonEncode(info['grid']),
        'mount.paifuRecord': true,
        'mount.onDeviceRead': true,
      });
      gameStore.resume(
        const ['A', 'B', 'C', 'D'],
        GameSettings(bottomSeat: info['bottom'] as int),
        scores: const [25000, 25000, 25000, 25000],
        roundWind: info['round_wind'] as int,
        roundNumber: info['round_number'] as int,
      );
      expect(gameStore.current!.dealer, info['dealer'], reason: '선 자리');
      MountScreen.debugDiscardRecorder = null;
      final sw = Stopwatch()..start();
      await tester.pumpWidget(MahjongApp(key: ValueKey(unit), loadSavedRules: false));
      final limit = Duration(seconds: ((info['duration'] as num) + (info['tail'] as num) + 120).round());
      var lastAsk = Duration.zero;
      var done = false;
      while (!done && sw.elapsed < limit) {
        await tester.pump(const Duration(milliseconds: 500));
        await Future<void>.delayed(const Duration(milliseconds: 500));
        if (sw.elapsed - lastAsk >= const Duration(seconds: 5)) {
          lastAsk = sw.elapsed;
          final st = jsonDecode((await http.get(Uri.parse('$_head/state'))).body) as Map<String, dynamic>;
          done = st['done'] == true;
        }
      }
      expect(done, isTrue, reason: '$unit: 가짜 헤드가 끝까지 안 감');
      final rec = MountScreen.debugDiscardRecorder;
      expect(rec, isNotNull, reason: '$unit: 기록기가 한 번도 안 돎(겹쳐 보기 안 됨)');
      final rivers = rec!.rivers();
      final out = {
        for (final s in Side.values)
          s.name: {
            'slots': [
              for (final d in rivers[s]!)
                {
                  'i': d.index + 1,
                  'tile': d.tile,
                  'share': double.parse(d.share.toStringAsFixed(2)),
                  'n': d.seen,
                  'first_at': _hms(d.firstAt),
                  'taken_at': d.takenAt == null ? null : _hms(d.takenAt!),
                  'sideways': d.sideways,
                  if (d.calledBy != null) 'called_by': d.calledBy!.name,
                  if (d.meldKind != null) 'meld': {'kind': d.meldKind, 'tiles': d.meldTiles},
                },
            ],
          },
        '_live': {
          'unit': unit,
          'dealer_side': rec.dealer?.name,
          'resets': rec.resets,
          'reset_at': rec.resetAt == null ? null : _hms(rec.resetAt!),
          'secs': sw.elapsed.inSeconds,
          'timeline': [for (final d in rec.timeline()) '${d.side.name} ${d.tile}${d.taken ? '*' : ''}${d.sideways ? '=' : ''}'],
        },
      };
      final r = await http.post(Uri.parse('$_head/result?name=$unit'), body: jsonEncode(out));
      expect(r.statusCode, 200);
      // ignore: avoid_print
      print('[paifu-live] $unit ${sw.elapsed.inSeconds}초 · 선 ${rec.dealer?.name} · 새로 시작 ${rec.resets}번 · ${[for (final s in Side.values) '${s.name} ${rivers[s]!.length}'].join(' ')}');
      // 거치 화면을 내려 배경 타이머를 멈추고 다음 묶음으로.
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 1));
      gameStore.discardCurrent();
    }
  }, timeout: const Timeout(Duration(hours: 3)));
}
