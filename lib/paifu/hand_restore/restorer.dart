/// 손패 복원 실행기(`docs/paifu_hand_restore_api_1121.md` 3-6): 차례를 하나씩(동시 1) 읽고 거꾸로 복원해 저장한다.
///
/// - 읽는 순서는 **뒤 차례부터**: 복원이 끝 손패에서 거꾸로 가므로, 한도 · 취소 · 실패로 멈춰도 그때까지 읽은 뒤쪽 차례는 손패가
///   채워진다. 한 차례가 답을 못 내거나 모순이면 그 앞 차례는 읽지 않는다(어차피 복원이 거기서 멈춤 — 돈을 안 씀).
/// - 판 전체 한도(기본 10달러): 차례를 시작하기 전에 남은 돈이 없으면 멈추고, 차례 한도는 min(차례 5달러, 남은 돈).
/// - 저장: 복원한 패보를 [PaifuStore.put](같은 id 바꿔 끼움), 원본은 `paifu.orig.<gameId>.<id>` 에 남겨 [RestoreStore.revert] 로 되돌림.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../paifu.dart';
import '../paifu_store.dart';
import 'frames.dart';
import 'rebuild.dart';
import 'turn_agent.dart';
import 'turns.dart';

class RestoreProgress {
  /// 끝낸 API 차례 수 / 읽을 API 차례 수.
  final int done, total;
  final double usd;

  /// 지금 읽는 차례(hero 버림 번호, 1부터). 없으면 null.
  final int? turn;
  final String message;
  const RestoreProgress({required this.done, required this.total, required this.usd, this.turn, this.message = ''});
}

class RestoreOutcome {
  /// 저장할 패보(손패를 한 차례도 못 채웠거나 API 차례를 하나도 못 읽었으면 null).
  final Paifu? paifu;
  final RebuildResult rebuild;
  final double usd;
  final int apiTurns, ruleTurns, guessTurns;

  /// 확신 낮은 차례(hero 버림 번호, 1부터).
  final List<int> unsureTurns;

  /// 읽기를 멈춘 까닭(한도 · 취소 · 실패). 끝까지 읽었으면 null.
  final String? stopReason;
  final bool cancelled;

  const RestoreOutcome({
    required this.paifu,
    required this.rebuild,
    required this.usd,
    required this.apiTurns,
    required this.ruleTurns,
    required this.guessTurns,
    this.unsureTurns = const [],
    this.stopReason,
    this.cancelled = false,
  });
}

/// 실행기 꼴(화면이 쓰는 것 — 시험은 가짜로).
abstract class HandRestoreRunner {
  Future<RestoreOutcome> run(Paifu p, {void Function(RestoreProgress)? onProgress, bool Function()? cancelled});
}

class HandRestorer implements HandRestoreRunner {
  final TurnReader reader;
  final HandFrameSource Function(String dir) sourceOf;
  final ImageRunner runner;
  final double gameLimitUsd;
  final double turnLimitUsd;

  HandRestorer({
    required this.reader,
    HandFrameSource Function(String dir)? sourceOf,
    this.runner = computeRunner,
    this.gameLimitUsd = 10,
    this.turnLimitUsd = 5,
  }) : sourceOf = sourceOf ?? DirFrameSource.new;

  @override
  Future<RestoreOutcome> run(Paifu p, {void Function(RestoreProgress)? onProgress, bool Function()? cancelled}) async {
    final turns = planTurns(p);
    final api = [
      for (final t in turns.reversed)
        if (t.usesApi) t,
    ];
    final frames = p.frames;
    final readings = <int, TurnReading>{};
    var usd = 0.0, done = 0;
    String? stop;
    var wasCancelled = false;
    void tell(String msg, {int? turn}) =>
        onProgress?.call(RestoreProgress(done: done, total: api.length, usd: usd, turn: turn, message: msg));

    if (frames == null) {
      stop = '녹화 정보가 없는 패보';
    } else {
      final source = sourceOf(frames.dir);
      List<int> all = const [];
      try {
        all = await source.list();
      } catch (e) {
        stop = '녹화 폴더를 읽지 못함: $e';
      }
      if (stop == null && all.isEmpty && api.isNotEmpty) stop = '녹화 폴더에 프레임이 없음';
      // 뒤 차례부터. 규칙 · 짐작 차례는 읽지 않고, 복원이 막히는 차례(unsupported)를 만나면 그 앞은 읽지 않는다.
      for (final t in turns.reversed) {
        if (stop != null) break;
        if (t.kind == RestoreTurnKind.unsupported) {
          stop = '${t.index + 1}번째 버림: ${t.reason}';
          break;
        }
        if (!t.usesApi) continue;
        if (cancelled?.call() == true) {
          stop = '취소';
          wasCancelled = true;
          break;
        }
        final left = gameLimitUsd - usd;
        if (left <= 0) {
          stop = '판 한도 ${gameLimitUsd.toStringAsFixed(0)}달러';
          break;
        }
        tell('${t.index + 1}번째 버림 프레임 준비', turn: t.index + 1);
        TurnFrames? tf;
        try {
          tf = await loadTurnFrames(source,
              startMs: t.startMs!, endMs: t.endMs!, box: frames.box, side: frames.side, runner: runner, all: all);
        } catch (e) {
          stop = '${t.index + 1}번째 버림 프레임을 읽지 못함: $e';
          break;
        }
        if (tf == null) {
          readings[t.index] = const TurnReading(error: '창 안에 프레임이 없음');
          stop = '${t.index + 1}번째 버림: 창 안에 프레임이 없음';
          break;
        }
        tell('${t.index + 1}번째 버림 읽는 중', turn: t.index + 1);
        final r = await reader.read(tf, t.n, maxUsd: left < turnLimitUsd ? left : turnLimitUsd, cancelled: cancelled);
        readings[t.index] = r;
        usd += r.usd;
        done++;
        tell('${t.index + 1}번째 버림 읽음', turn: t.index + 1);
        if (r.error == '취소') {
          stop = '취소';
          wasCancelled = true;
          break;
        }
        // 이 차례에서 복원이 막히면 앞 차례는 읽지 않는다.
        final probe = rebuildHands(p, turns, readings);
        if (probe.failedTurn == t.index) {
          stop = '${t.index + 1}번째 버림: ${probe.failReason}';
          break;
        }
      }
    }
    final rb = rebuildHands(p, turns, readings);
    return RestoreOutcome(
      // API 차례를 하나도 못 읽었으면(녹화 없음 · 첫 차례부터 실패) 리치 뒤 규칙 차례만 채운 패보는 저장하지 않는다 — 단추가 사라져
      // 다시 해 볼 수 없게 되므로.
      paifu: rb.restored > 0 && (api.isEmpty || readings.values.any((r) => r.answered)) ? rb.paifu : null,
      rebuild: rb,
      usd: usd,
      apiTurns: api.length,
      ruleTurns: turns.where((t) => t.kind == RestoreTurnKind.rule).length,
      guessTurns: turns.where((t) => t.kind == RestoreTurnKind.afterCall).length,
      unsureTurns: [
        for (final t in turns)
          if (readings[t.index]?.unsure == true) t.index + 1,
      ],
      stopReason: stop,
      cancelled: wasCancelled,
    );
  }
}

/// 복원 저장 · 되돌리기.
class RestoreStore {
  static String origKey(String gameId, String id) => 'paifu.orig.$gameId.$id';

  /// 원본을 남기고(이미 있으면 그대로 — 처음 것) 복원한 패보로 바꿔 끼운다.
  static Future<void> save(String gameId, Paifu original, Paifu restored) async {
    final prefs = await SharedPreferences.getInstance();
    final k = origKey(gameId, original.id);
    if (!prefs.containsKey(k)) await prefs.setString(k, jsonEncode(original.toJson()));
    await PaifuStore.put(gameId, restored);
  }

  static Future<bool> hasOriginal(String gameId, String id) async =>
      (await SharedPreferences.getInstance()).containsKey(origKey(gameId, id));

  /// 남겨 둔 원본으로 되돌린다. 원본이 없으면 null.
  static Future<Paifu?> revert(String gameId, String id) async {
    final prefs = await SharedPreferences.getInstance();
    final s = prefs.getString(origKey(gameId, id));
    if (s == null) return null;
    final p = Paifu.fromJson(jsonDecode(s) as Map<String, dynamic>);
    await PaifuStore.put(gameId, p);
    await prefs.remove(origKey(gameId, id));
    return p;
  }
}

/// Claude API 키(사용자가 앱 안에서 넣음). APK 에 넣지 않는다.
class ClaudeKeyStore {
  static const prefKey = 'claude.apiKey';

  static Future<String?> load() async {
    final v = (await SharedPreferences.getInstance()).getString(prefKey);
    return v == null || v.trim().isEmpty ? null : v.trim();
  }

  static Future<void> save(String key) async => (await SharedPreferences.getInstance()).setString(prefKey, key.trim());

  static Future<void> clear() async => (await SharedPreferences.getInstance()).remove(prefKey);
}
