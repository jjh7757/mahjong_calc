/// Claude Messages API 를 부르는 얇은 클라이언트(`docs/paifu_hand_restore_api_1121.md` 3-3). Dart 공식 SDK 가 없어 HTTP 로 부른다.
///
/// 요청 꼴은 `experiments/paifu_frames/handtrack/claudeagent.py` `request_kw` · `call` 과 같게 쓴다(본문은 [TurnAgent] 가 만든다):
/// - `POST https://api.anthropic.com/v1/messages`, 헤더 `x-api-key` · `anthropic-version: 2023-06-01` · `content-type`.
/// - 스트리밍(SSE)으로 받아 최종 메시지로 모은다(claudeagent 의 `messages.stream(...).get_final_message()` — max_tokens 32000 이라
///   한 번에 받으면 연결이 오래 조용하다). thinking 블록의 서명(`signature_delta`)까지 그대로 모아 다음 요청에 되돌려 보낸다.
///   응답이 JSON(스트림이 아님)이면 그것을 그대로 쓴다.
/// - 재시도: 429 · 5xx(529 포함) · 연결 오류 · 스트림 중 overloaded/api 오류만, 3번 더(10 · 20 · 30초). 400 등은 바로 올린다.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class ClaudeApiException implements Exception {
  /// HTTP 상태(스트림 중 오류 · 연결 오류면 null).
  final int? status;

  /// API 오류 종류(`rate_limit_error` 등) 또는 `connection`.
  final String? type;
  final String message;
  final bool retryable;
  const ClaudeApiException(this.message, {this.status, this.type, this.retryable = false});

  @override
  String toString() => 'ClaudeApiException(${status ?? type ?? '-'}): $message';
}

/// 최종 메시지(JSON 그대로).
class ClaudeMessage {
  final Map<String, dynamic> raw;
  const ClaudeMessage(this.raw);

  List<Map<String, dynamic>> get content => [
        for (final b in (raw['content'] as List? ?? const []))
          if (b is Map) b.cast<String, dynamic>(),
      ];
  String? get stopReason => raw['stop_reason'] as String?;
  Map<String, dynamic> get stopDetails => (raw['stop_details'] as Map?)?.cast<String, dynamic>() ?? const {};
  Map<String, dynamic> get usage => (raw['usage'] as Map?)?.cast<String, dynamic>() ?? const {};
  int usageOf(String key) => (usage[key] as num?)?.toInt() ?? 0;
}

class ClaudeClient {
  static final Uri defaultEndpoint = Uri.parse('https://api.anthropic.com/v1/messages');
  static const apiVersion = '2023-06-01';

  /// 재시도 사이 쉬는 시간(claudeagent.call 의 10 · 20 · 30초).
  static const retryDelays = [Duration(seconds: 10), Duration(seconds: 20), Duration(seconds: 30)];

  final http.Client _http;
  final String apiKey;
  final Uri endpoint;
  final bool stream;
  final Future<void> Function(Duration) sleep;

  /// 스트림에 아무 줄도 안 오는 시간이 이만큼이면 끊긴 것으로 보고 다시(서버는 쉬는 동안 ping 을 보낸다).
  final Duration idleTimeout;

  ClaudeClient({
    required http.Client httpClient,
    required this.apiKey,
    Uri? endpoint,
    this.stream = true,
    Future<void> Function(Duration)? sleep,
    this.idleTimeout = const Duration(minutes: 5),
  })  : _http = httpClient,
        endpoint = endpoint ?? defaultEndpoint,
        sleep = sleep ?? Future<void>.delayed;

  /// [body] 그대로 보내고(스트리밍이면 `"stream": true` 를 더함) 최종 메시지.
  Future<ClaudeMessage> create(Map<String, dynamic> body) async {
    final payload = jsonEncode(stream ? {...body, 'stream': true} : body);
    ClaudeApiException? last;
    for (var attempt = 0; attempt <= retryDelays.length; attempt++) {
      if (attempt > 0) await sleep(retryDelays[attempt - 1]);
      try {
        return await _once(payload);
      } on ClaudeApiException catch (e) {
        if (!e.retryable) rethrow;
        last = e;
      } on http.ClientException catch (e) {
        last = ClaudeApiException(e.message, type: 'connection', retryable: true);
      } on TimeoutException catch (e) {
        last = ClaudeApiException('시간 초과: ${e.message ?? ''}', type: 'connection', retryable: true);
      }
    }
    throw last!;
  }

  Future<ClaudeMessage> _once(String payload) async {
    final req = http.Request('POST', endpoint)
      ..headers.addAll({
        'x-api-key': apiKey,
        'anthropic-version': apiVersion,
        'content-type': 'application/json',
        if (stream) 'accept': 'text/event-stream',
      })
      ..body = payload;
    final res = await _http.send(req);
    if (res.statusCode != 200) {
      final text = await res.stream.bytesToString();
      throw _statusError(res.statusCode, text);
    }
    final ct = res.headers['content-type'] ?? '';
    if (!ct.contains('event-stream')) {
      final j = jsonDecode(await res.stream.bytesToString());
      if (j is! Map) throw const ClaudeApiException('응답이 메시지가 아님');
      return ClaudeMessage(j.cast<String, dynamic>());
    }
    return readSse(res.stream.timeout(idleTimeout).transform(utf8.decoder).transform(const LineSplitter()));
  }

  static ClaudeApiException _statusError(int status, String text) {
    String? type;
    var message = text;
    try {
      final j = jsonDecode(text);
      if (j is Map && j['error'] is Map) {
        type = (j['error'] as Map)['type'] as String?;
        message = (j['error'] as Map)['message'] as String? ?? text;
      }
    } catch (_) {}
    return ClaudeApiException(message.length > 400 ? message.substring(0, 400) : message,
        status: status, type: type, retryable: status == 429 || status >= 500);
  }

  /// SSE 줄들 → 최종 메시지. 블록은 content_block_start 의 것을 그대로 두고 delta 를 이어 붙인다
  /// (text · thinking · signature · tool_use 입력 JSON · citations). 모르는 delta 는 무시한다.
  static Future<ClaudeMessage> readSse(Stream<String> lines) async {
    Map<String, dynamic>? msg;
    final blocks = <int, Map<String, dynamic>>{};
    final json = <int, StringBuffer>{};
    final data = StringBuffer();
    var stopped = false;

    void dispatch() {
      if (data.isEmpty) return;
      final s = data.toString();
      data.clear();
      final Object? ev;
      try {
        ev = jsonDecode(s);
      } catch (_) {
        return;
      }
      if (ev is! Map) return;
      switch (ev['type']) {
        case 'message_start':
          msg = (ev['message'] as Map).cast<String, dynamic>();
          msg!['content'] = <Map<String, dynamic>>[];
        case 'content_block_start':
          final i = (ev['index'] as num).toInt();
          blocks[i] = Map<String, dynamic>.from(ev['content_block'] as Map);
        case 'content_block_delta':
          final i = (ev['index'] as num).toInt();
          final b = blocks[i];
          final d = ev['delta'];
          if (b == null || d is! Map) return;
          switch (d['type']) {
            case 'text_delta':
              b['text'] = '${b['text'] ?? ''}${d['text'] ?? ''}';
            case 'thinking_delta':
              b['thinking'] = '${b['thinking'] ?? ''}${d['thinking'] ?? ''}';
            case 'signature_delta':
              b['signature'] = '${b['signature'] ?? ''}${d['signature'] ?? ''}';
            case 'input_json_delta':
              (json[i] ??= StringBuffer()).write(d['partial_json'] ?? '');
            case 'citations_delta':
              b['citations'] = [...(b['citations'] as List? ?? const []), d['citation']];
          }
        case 'content_block_stop':
          final i = (ev['index'] as num).toInt();
          final b = blocks[i];
          if (b != null && json[i] != null) {
            final t = json[i].toString();
            b['input'] = t.trim().isEmpty ? <String, dynamic>{} : jsonDecode(t);
          }
        case 'message_delta':
          final d = ev['delta'];
          if (msg != null && d is Map) {
            for (final e in d.entries) {
              msg![e.key as String] = e.value;
            }
          }
          final u = ev['usage'];
          if (msg != null && u is Map) {
            final mu = Map<String, dynamic>.from((msg!['usage'] as Map?) ?? const {});
            for (final e in u.entries) {
              if (e.value != null) mu[e.key as String] = e.value;
            }
            msg!['usage'] = mu;
          }
        case 'message_stop':
          stopped = true;
        case 'error':
          final err = ev['error'] is Map ? ev['error'] as Map : const {};
          final type = err['type'] as String?;
          throw ClaudeApiException(err['message'] as String? ?? '스트림 오류',
              type: type, retryable: type == 'overloaded_error' || type == 'api_error' || type == 'rate_limit_error');
      }
    }

    await for (final line in lines) {
      if (line.isEmpty) {
        dispatch();
      } else if (line.startsWith('data:')) {
        if (data.isNotEmpty) data.write('\n');
        data.write(line.substring(5).trimLeft());
      }
      // event: · 주석(:) 줄은 data 의 type 으로 충분해서 버린다.
    }
    dispatch();
    final m = msg;
    if (m == null) throw const ClaudeApiException('스트림에 message_start 가 없음', type: 'connection', retryable: true);
    if (!stopped) throw const ClaudeApiException('스트림이 끝나기 전에 끊김', type: 'connection', retryable: true);
    final keys = blocks.keys.toList()..sort();
    m['content'] = [for (final k in keys) blocks[k]!];
    return ClaudeMessage(m);
  }
}
