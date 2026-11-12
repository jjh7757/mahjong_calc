import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../engine/calculator.dart' as engine;
import '../game/game.dart';
import '../table/auto_record.dart';
import '../table/cropper.dart';
import '../table/felt_grid.dart' show feltQuadOfJpeg;
import '../table/fixed_layout.dart';
import '../table/grid_zones.dart';
import '../table/hand_rules.dart';
import '../table/merge.dart';
import '../table/read_signals.dart';
import '../table/river_change.dart' show analyzeTableFrame;
import '../table/seat_map.dart';
import '../table/shot_image.dart';
import '../table/table_reader.dart';
import 'capture_log.dart';
import 'on_device_reader.dart';
import 'recognizer_client.dart';

/// 기기 판독 실험(exp/on-device-read) 앱 흐름 측정: adb 브로드캐스트(OnDeviceBenchReceiver, `--es flow manifest.json`) →
/// 네이티브가 이 채널로 부른다. 사진마다 `integration_test/read_grid_timing_test.dart` 의 measure 와 같은 일(readGrid(localOnly·useRoles·
/// gridSrc saved) → mergeReading → 점수 → 자동 반영 조건)을 모드별로(server = 스위치 끔·운영 서버, device = 스위치 켬) 번갈아 하고,
/// 한 줄 JSON 을 manifest 옆 `flow_<tag>.jsonl` 에 쓴다. 끝나면 스위치를 원래대로 돌린다. UI 는 건드리지 않는다.
class OnDeviceBench {
  static const MethodChannel _ch = MethodChannel('dev.jjh.mahjong_calc/ondevice_bench');
  static bool _busy = false;

  static void register() {
    _ch.setMethodCallHandler((call) async {
      if (call.method != 'flow' && call.method != 'track') return null;
      if (_busy) return 'busy';
      _busy = true;
      try {
        if (call.method == 'track') return await _track(call.arguments as String);
        return await _run(call.arguments as String);
      } finally {
        _busy = false;
      }
    });
  }

  static const ImageOps _ops = ImageOps(
    shrink: _shrink,
    cropMany: _crop,
    analyze: _analyze,
    analyzeGrid: _analyzeGrid,
    openShot: _openShot,
  );
  static Future<Uint8List> _shrink(Uint8List o) => compute(shrinkForLocate, o);
  static Future<List<Uint8List>> _crop(Uint8List o, List<CropSpec> s) => compute(cropMany, (o, s));
  static Future<ShotAnalysis> _analyze(Uint8List small, FixedTable f) => compute(analyzeShot, (small, f));
  static Future<ShotAnalysis> _analyzeGrid(Uint8List small, GridZones g) => compute(analyzeGridShot, (small, g));
  static Future<ShotImage> _openShot(Uint8List o) => IsolateShotImage.open(o);

  /// 추적 분석 시간: manifest `{"tag","repeat","items":[{"name","res","path","grid"}]}` → 사진마다 앱과 같이
  /// `compute(analyzeTableFrame, …)` 를 [repeat] 번(처음 한 번은 버림) 재서 `track_<tag>.jsonl` 에 한 줄씩.
  static Future<String> _track(String manifestPath) async {
    final man = jsonDecode(await File(manifestPath).readAsString()) as Map<String, dynamic>;
    final tag = man['tag'] as String? ?? 'x';
    final repeat = (man['repeat'] as num?)?.toInt() ?? 3;
    final sink = File('${File(manifestPath).parent.path}/track_$tag.jsonl').openWrite();
    var n = 0;
    try {
      for (final it in (man['items'] as List).cast<Map<String, dynamic>>()) {
        final bytes = await File(it['path'] as String).readAsBytes();
        final grid = GridZones.fromJson((it['grid'] as Map).cast<String, dynamic>())!;
        // fn: 'track'(기본, analyzeTableFrame) · 'felt'(feltQuadOfJpeg — 펠트 감시).
        final felt = it['fn'] == 'felt';
        Future<void> run() => felt ? compute(feltQuadOfJpeg, bytes) : compute(analyzeTableFrame, (bytes, grid));
        await run();
        final ms = <int>[];
        for (var i = 0; i < repeat; i++) {
          final sw = Stopwatch()..start();
          await run();
          ms.add(sw.elapsedMilliseconds);
        }
        sink.writeln(jsonEncode({'name': it['name'], 'res': it['res'], 'fn': it['fn'] ?? 'track', 'bytes': bytes.length, 'ms': ms}));
        await sink.flush();
        n++;
      }
    } finally {
      await sink.close();
    }
    return 'track $tag $n';
  }

  static Future<String> _run(String manifestPath) async {
    final man = jsonDecode(await File(manifestPath).readAsString()) as Map<String, dynamic>;
    final tag = man['tag'] as String? ?? 'x';
    final modes = [for (final m in (man['modes'] as List? ?? const ['server', 'device'])) m as String];
    final repeat = (man['repeat'] as num?)?.toInt() ?? 1;
    final out = File('${File(manifestPath).parent.path}/flow_$tag.jsonl');
    final sink = out.openWrite();
    final wasOn = OnDeviceReader.enabled;
    var n = 0;
    try {
      // 기기 쪽 첫 호출이 모델 올리기를 떠안지 않게(앱에서도 스위치를 켜면 미리 올린다).
      if (modes.any((m) => m.startsWith('device'))) await OnDeviceReader.warmup();
      for (var run = 1; run <= repeat; run++) {
        for (final it in (man['items'] as List).cast<Map<String, dynamic>>()) {
          final bytes = await File(it['path'] as String).readAsBytes();
          final grid = GridZones.fromJson((it['grid'] as Map).cast<String, dynamic>())!;
          for (final mode in modes) {
            // server = 스위치 끔(운영 서버) · device = 켬(서버와 같은 바이트) · device_skip = 켬 + 재저장 생략
            OnDeviceReader.enabled = mode.startsWith('device');
            if (OnDeviceReader.enabled) await OnDeviceReader.setPrep(mode == 'device_skip' ? 'skip' : 'server');
            final row = await _measure(bytes, grid)
              ..['name'] = it['name']
              ..['mode'] = mode
              ..['run'] = run;
            sink.writeln(jsonEncode(row));
            await sink.flush();
            n++;
            debugPrint('[ondevice-flow] ${it['name']} $mode ${row['total_ms']}ms ${row['error'] ?? ''}');
          }
        }
      }
    } finally {
      OnDeviceReader.enabled = wasOn;
      // 앱 기본(재저장 생략, 2026-11-11 사용자 결정)으로 되돌린다.
      if (modes.any((m) => m.startsWith('device'))) await OnDeviceReader.setPrep('skip');
      await sink.close();
    }
    return jsonEncode({'path': out.path, 'rows': n});
  }

  static Future<Map<String, Object?>> _measure(Uint8List bytes, GridZones grid) async {
    final client = RecognizerClient();
    final trace = TableReadTrace();
    final game = Game(
      id: 'bench',
      startedAt: DateTime(2026, 11, 11),
      settings: const GameSettings(),
      names: const ['플레이어 1', '플레이어 2', '플레이어 3', '플레이어 4'],
      dealer: 0,
      roundNumber: 1,
      honba: 0,
    );
    final out = <String, Object?>{'bytes': bytes.length};
    final sw = Stopwatch()..start();
    try {
      final reading = await TableReader(client, ops: _ops)
          .readGrid(bytes, grid, trace: trace, localOnly: true, useRoles: true, gridSrc: GridSource.saved);
      final merge = mergeReading(
        hand: reading.hand!,
        center: reading.center,
        winnerSide: reading.winnerSide!,
        game: game,
        seats: SeatMap(game.settings.bottomSeat),
        trackedDora: reading.trackedDora,
      );
      final score = merge.hand == null ? null : engine.calculate(merge.hand!, merge.situation);
      out['winner'] = reading.winnerSide!.name;
      out['points'] = score == null ? null : RegExp(r' (\d{3,6}) \[').firstMatch('$score')?.group(1);
      out['merge'] = CaptureLog.mergeJson(merge);
      out['call_ms'] = trace.callMs;
      out['server_timing'] = trace.serverTiming;
      final rules = checkHandRules(handRuleInputOf(hand: reading.hand!, merge: merge, center: reading.center));
      final sig = checkReadSignals(reading.hand!.signals);
      out['auto_block'] = autoRecordBlocker(
        warnings: reading.warnings,
        issues: [for (final f in merge.flags) f.issue],
        otherWinners: reading.others.length,
        isTsumo: merge.isTsumo,
        loser: merge.loser,
        resultValid: score?.isValid ?? false,
        paoBase: score != null && score.isValid ? engine.paoBasePoints(score) : 0,
        gameOver: false,
        ruleBlocks: rules.blockers,
        signalBlocks: sig.blocks,
      );
    } catch (e) {
      out['error'] = '$e';
    } finally {
      client.close();
    }
    out['total_ms'] = sw.elapsedMilliseconds;
    out['stages_ms'] = trace.timingsMs;
    return out;
  }
}
