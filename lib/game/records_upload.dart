import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../paifu/paifu.dart';
import '../paifu/paifu_store.dart';
import '../services/server_backoff.dart';
import 'game.dart';
import 'game_store.dart';

// 우리 대국 기록 사이트(`/records`)에 끝난 대국을 올린다(docs/records_site_design_1125.md 4 · 6절).
//
// - 본문: [recordsBody] — `{game, settlement[4], paifu[], app_version}`. 서버와 약속한 꼴이라 바꾸지 않는다.
// - 대기열: SharedPreferences `records.queue`(대국 id 목록, 중복 없음). 대국이 끝나면 넣고 바로 비우기를 시도한다.
//   실패한 대국은 남겨 두었다가 앱 시작 · 지난 대국 화면 · "지금 올리기" 때 다시.
// - 서버는 `(매장, game.id)` 로 멱등 upsert 라 같은 대국을 여러 번 올려도 된다.
// - 꺼져 있으면([RecordsConfig.enabled]) 대기열에 넣지도, 올리지도 않는다.

/// 앱 버전(pubspec.yaml 의 version). 패키지 정보 플러그인을 들이지 않으려고 손으로 맞춘다 — 시험이 pubspec 과 같은지 본다.
const recordsAppVersion = '1.0.0+1';

/// 기록 사이트 기본 주소(경로 `/records` 까지).
const recordsDefaultBaseUrl = 'https://mahjong.ai-agent-develop.cloud/records';

/// 기록 사이트 설정(기기 저장).
class RecordsConfig {
  final bool enabled;
  final String baseUrl;
  final String storeKey;

  const RecordsConfig({this.enabled = false, this.baseUrl = recordsDefaultBaseUrl, this.storeKey = ''});

  /// `{base}/api/v1/games`. 주소가 http(s) 가 아니면 null.
  Uri? get uploadUri {
    var b = baseUrl.trim();
    while (b.endsWith('/')) {
      b = b.substring(0, b.length - 1);
    }
    final u = Uri.tryParse('$b/api/v1/games');
    if (u == null || !(u.scheme == 'http' || u.scheme == 'https') || u.host.isEmpty) return null;
    return u;
  }

  /// 올릴 수 없는 사유(켜져 있을 때). 올릴 수 있으면 null.
  String? get problem {
    if (storeKey.trim().isEmpty) return '매장 키가 비어 있습니다';
    if (uploadUri == null) return '주소가 올바르지 않습니다(https://… )';
    return null;
  }
}

class RecordsSettings {
  static const enabledKey = 'records.enabled';
  static const baseUrlKey = 'records.baseUrl';
  static const storeKeyKey = 'records.storeKey';

  static Future<RecordsConfig> load() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString(baseUrlKey);
    return RecordsConfig(
      enabled: p.getBool(enabledKey) ?? false,
      baseUrl: base == null || base.trim().isEmpty ? recordsDefaultBaseUrl : base,
      storeKey: p.getString(storeKeyKey) ?? '',
    );
  }

  static Future<void> setEnabled(bool on) async => (await SharedPreferences.getInstance()).setBool(enabledKey, on);
  static Future<void> setBaseUrl(String url) async => (await SharedPreferences.getInstance()).setString(baseUrlKey, url.trim());
  static Future<void> setStoreKey(String key) async =>
      (await SharedPreferences.getInstance()).setString(storeKeyKey, key.trim());
}

/// 대국 [g] 의 업로드 본문(JSON 으로 바꾸기 전의 맵). 순수 함수.
///
/// `game` 은 [Game.toJson] 그대로이되 이 앱만 쓰는 '기록 사이트에 올린 때'([Game.recordsUploadedAt])는 뺀다 —
/// 남기면 올릴 때마다 본문 해시가 바뀌어 서버가 `unchanged` 대신 `updated` 로 다시 쓴다.
Map<String, dynamic> recordsBody(Game g, List<Paifu> paifu, {String appVersion = recordsAppVersion}) {
  final game = g.toJson()..remove('recordsUploadedAt');
  return {
    'game': game,
    'settlement': [
      for (final s in g.settle())
        {
          'seat': s.seat,
          'name': s.name,
          'rank': s.rank,
          'points': s.points,
          'score': s.score,
          'stars': s.stars,
        },
    ],
    'paifu': [for (final p in paifu) p.toJson()],
    'app_version': appVersion,
  };
}

/// 대기열 · 마지막 결과(설정 화면 표시용).
@immutable
class RecordsStatus {
  final int pending;
  final bool running;
  final String? lastError;
  final DateTime? lastSuccessAt;

  const RecordsStatus({this.pending = 0, this.running = false, this.lastError, this.lastSuccessAt});

  RecordsStatus copyWith({int? pending, bool? running, String? lastError, bool clearError = false, DateTime? lastSuccessAt}) =>
      RecordsStatus(
        pending: pending ?? this.pending,
        running: running ?? this.running,
        lastError: clearError ? null : (lastError ?? this.lastError),
        lastSuccessAt: lastSuccessAt ?? this.lastSuccessAt,
      );
}

/// 한 번 비운 결과.
class RecordsFlushResult {
  /// 꺼져 있어 아무것도 안 함.
  final bool disabled;
  final int sent;
  final int failed;

  /// 남은 대기열 길이.
  final int pending;
  final String? error;

  const RecordsFlushResult({this.disabled = false, this.sent = 0, this.failed = 0, this.pending = 0, this.error});

  @override
  String toString() => 'RecordsFlushResult(disabled: $disabled, sent: $sent, failed: $failed, pending: $pending, error: $error)';
}

class RecordsUploader {
  static const queueKey = 'records.queue';
  static const lastErrorKey = 'records.lastError';
  static const lastSuccessKey = 'records.lastSuccessAt';

  /// 시험용 대국 저장소. null 이면 앱 전체의 [gameStore].
  final GameStore? store;
  final http.Client Function() _client;
  final Future<List<Paifu>> Function(String gameId) _paifuOf;
  final DateTime Function() _now;

  /// 앱에서 친 대국이 끝난 뒤 올리기까지 기다리는 시간. 마지막 국의 화료 패보 저장(`_savePaifu`)이
  /// 화면 흐름과 따로(최대 10초 판독 뒤) 끝나므로, 그 국 패보가 본문에 들어가게 잠깐 둔다. 직접 입력 대국은 바로.
  final Duration finishDelay;
  final Duration timeout;

  /// 설정 화면이 듣는 상태.
  final ValueNotifier<RecordsStatus> status = ValueNotifier(const RecordsStatus());

  RecordsUploader({
    this.store,
    http.Client Function()? client,
    Future<List<Paifu>> Function(String gameId)? paifuOf,
    DateTime Function()? now,
    this.finishDelay = const Duration(seconds: 20),
    this.timeout = const Duration(seconds: 20),
  })  : _client = client ?? http.Client.new,
        _paifuOf = paifuOf ?? PaifuStore.list,
        _now = now ?? DateTime.now;

  GameStore get _games => store ?? gameStore;

  Future<RecordsFlushResult>? _running;
  Timer? _delayed;

  // ---------- 대기열 ----------

  Future<List<String>> queue() async {
    final p = await SharedPreferences.getInstance();
    return List.of(p.getStringList(queueKey) ?? const <String>[]);
  }

  /// [ids] 를 대기열 끝에 넣는다(이미 있으면 그대로). 꺼져 있어도 넣는다 — 꺼짐 확인은 부르는 쪽([onFinished] 등).
  Future<void> enqueue(Iterable<String> ids) async {
    final p = await SharedPreferences.getInstance();
    // 읽고 쓰는 사이에 await 가 없어야 다른 넣기 · 빼기와 엇갈리지 않는다(setStringList 는 캐시를 바로 바꾼다).
    final q = p.getStringList(queueKey) ?? <String>[];
    final seen = q.toSet();
    final out = List.of(q);
    for (final id in ids) {
      if (seen.add(id)) out.add(id);
    }
    await p.setStringList(queueKey, out);
    _setStatus(status.value.copyWith(pending: out.length));
  }

  Future<void> _remove(String id) async {
    final p = await SharedPreferences.getInstance();
    final q = (p.getStringList(queueKey) ?? <String>[])..remove(id);
    await p.setStringList(queueKey, q);
  }

  /// 대기열 길이 · 저장된 마지막 오류를 다시 읽어 [status] 에 넣는다(설정 화면을 열 때).
  Future<void> refreshStatus() async {
    final p = await SharedPreferences.getInstance();
    final ok = p.getString(lastSuccessKey);
    _setStatus(status.value.copyWith(
      pending: (p.getStringList(queueKey) ?? const <String>[]).length,
      lastError: p.getString(lastErrorKey),
      clearError: p.getString(lastErrorKey) == null,
      lastSuccessAt: ok == null ? null : DateTime.tryParse(ok),
    ));
  }

  // ---------- 고리 ----------

  /// [GameStore.onFinished] 에 단다. 켜져 있으면 대기열에 넣고 올리기를 시도한다(앱 대국은 [finishDelay] 뒤).
  /// 기다리지 않고 실패해도 조용히 넘어간다.
  void onFinished(Game g) {
    unawaited(_onFinished(g));
  }

  Future<void> _onFinished(Game g) async {
    try {
      final cfg = await RecordsSettings.load();
      if (!cfg.enabled) return;
      await enqueue([g.id]);
      if (g.isManual || finishDelay == Duration.zero) {
        await flush();
      } else {
        _delayed?.cancel();
        _delayed = Timer(finishDelay, () => unawaited(flush()));
      }
    } catch (e) {
      debugPrint('[records] 대기열 넣기 실패: $e');
    }
  }

  /// 지난 대국 모두를 대기열에 넣는다(오래된 것부터). 넣은 개수.
  Future<int> enqueueAllHistory() async {
    final ids = [for (final g in _games.history.reversed) if (g.finished) g.id];
    await enqueue(ids);
    return ids.length;
  }

  // ---------- 비우기 ----------

  /// 대기열을 하나씩 올린다. 이미 돌고 있으면 그 결과를 같이 기다린다(동시에 두 번 돌지 않음).
  /// 꺼져 있으면 아무것도 안 한다. 던지지 않는다.
  Future<RecordsFlushResult> flush() {
    final r = _running;
    if (r != null) return r;
    final f = _flush().whenComplete(() => _running = null);
    _running = f;
    return f;
  }

  Future<RecordsFlushResult> _flush() async {
    RecordsConfig cfg;
    try {
      cfg = await RecordsSettings.load();
    } catch (e) {
      return RecordsFlushResult(error: '$e');
    }
    if (!cfg.enabled) return const RecordsFlushResult(disabled: true);
    final problem = cfg.problem;
    if (problem != null) {
      final n = (await queue()).length;
      await _finishRun(error: problem, pending: n, sent: 0);
      return RecordsFlushResult(pending: n, error: problem);
    }
    final uri = cfg.uploadUri!;
    final store = _games;
    if (!store.loaded) {
      // 지난 대국을 아직 못 읽었다 — 대기열의 대국을 "지워졌다" 고 버리면 안 된다.
      final n = (await queue()).length;
      return RecordsFlushResult(pending: n);
    }

    _setStatus(status.value.copyWith(running: true));
    final client = _client();
    final tried = <String>{};
    var sent = 0;
    var failed = 0;
    String? error;
    try {
      while (true) {
        final q = await queue();
        String? id;
        for (final x in q) {
          if (!tried.contains(x)) {
            id = x;
            break;
          }
        }
        if (id == null) break;
        tried.add(id);
        Game? g;
        for (final h in store.history) {
          if (h.id == id) {
            g = h;
            break;
          }
        }
        if (g == null || !g.finished) {
          // 지운 대국(또는 지난 대국 목록에 없는 id) — 올릴 것이 없다.
          await _remove(id);
          continue;
        }
        try {
          final paifu = await _paifuOf(id);
          final body = jsonEncode(recordsBody(g, paifu));
          final res = await client
              .post(uri,
                  headers: {
                    'Content-Type': 'application/json; charset=utf-8',
                    'X-Store-Key': cfg.storeKey.trim(),
                  },
                  body: utf8.encode(body))
              .timeout(timeout);
          if (res.statusCode == 200) {
            final st = _statusOf(res);
            store.markRecordsUploaded(id, at: _now(), save: false);
            await _remove(id);
            sent++;
            debugPrint('[records] 올림 $id → $st');
            if (sent % 20 == 0) await store.persist();
          } else if (res.statusCode == 401 || res.statusCode == 403) {
            failed++;
            error = '매장 키가 맞지 않습니다(${res.statusCode})';
            break; // 다른 대국도 같은 키라 더 보내지 않는다.
          } else {
            failed++;
            error = '서버 오류 ${res.statusCode}: ${_snippet(res)}';
          }
        } catch (e) {
          failed++;
          if (ServerBackoff.isNetworkError(e) || e is http.ClientException) {
            error = '연결 실패: ${_short(e)}';
            break; // 연결이 안 되면 나머지도 안 된다 — 다음 기회에.
          }
          error = '올리기 실패: ${_short(e)}';
        }
      }
    } finally {
      client.close();
      if (sent > 0) {
        try {
          await store.persist();
        } catch (_) {}
      }
    }
    final n = (await queue()).length;
    await _finishRun(error: error, pending: n, sent: sent);
    return RecordsFlushResult(sent: sent, failed: failed, pending: n, error: error);
  }

  Future<void> _finishRun({required String? error, required int pending, required int sent}) async {
    final p = await SharedPreferences.getInstance();
    final now = _now();
    if (error != null) {
      await p.setString(lastErrorKey, error);
    } else {
      await p.remove(lastErrorKey);
    }
    if (sent > 0) await p.setString(lastSuccessKey, now.toIso8601String());
    _setStatus(RecordsStatus(
      pending: pending,
      running: false,
      lastError: error,
      lastSuccessAt: sent > 0 ? now : status.value.lastSuccessAt,
    ));
  }

  void _setStatus(RecordsStatus s) => status.value = s;

  static String? _statusOf(http.Response res) {
    try {
      final j = jsonDecode(utf8.decode(res.bodyBytes));
      if (j is Map && j['status'] is String) return j['status'] as String;
    } catch (_) {}
    return null;
  }

  static String _snippet(http.Response res) {
    final s = utf8.decode(res.bodyBytes, allowMalformed: true).trim();
    return s.length > 120 ? '${s.substring(0, 120)}…' : s;
  }

  static String _short(Object e) {
    final s = e.toString();
    return s.length > 160 ? '${s.substring(0, 160)}…' : s;
  }
}

/// 앱 전체에서 하나만 쓴다.
final RecordsUploader recordsUploader = RecordsUploader();
